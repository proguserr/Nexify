# core/tasks.py
from __future__ import annotations

import os

from celery import shared_task
from django.db import transaction

from core.kb import search_kb_chunks_for_query
from core.llm_client import classify_ticket_with_llm, LLMError
from core.models import JobRun, Ticket, Suggestion, TicketEvent

AUTO_RESOLVE_MIN_CONFIDENCE = 0.85


def _simple_classification_and_resolution(ticket: Ticket) -> dict:
    """
    Tiny heuristic "AI" so the UI looks alive when LLM is unavailable.
    Classifies the ticket and returns suggestion fields.
    """

    text = f"{ticket.subject}\n\n{ticket.body}".lower()

    if any(w in text for w in ["password", "login", "2fa", "mfa", "auth"]):
        classification = "login_issue"
        suggested_team = "Auth Support"
        suggested_priority = Ticket.Priority.HIGH
        draft_reply = (
            "Hi,\n\nIt looks like you're having trouble signing in. "
            "Please try resetting your password using the 'Forgot password' "
            "link. If 2FA is enabled, verify your authenticator app is in sync. "
            "If the issue persists, reply with the exact error message so we can investigate.\n\n"
            "Best,\nAuth Support"
        )
        confidence = 0.88

    elif any(w in text for w in ["billing", "invoice", "payment", "card", "charge"]):
        classification = "billing"
        suggested_team = "Billing Support"
        suggested_priority = Ticket.Priority.HIGH
        draft_reply = (
            "Hi,\n\nWe've received your request regarding billing. "
            "Please confirm the last 4 digits of the card used and the invoice ID in question. "
            "We'll review the recent transactions on your account and correct any discrepancies.\n\n"
            "Best,\nBilling Support"
        )
        confidence = 0.85

    elif any(w in text for w in ["latency", "slow", "timeout", "500", "503", "error"]):
        classification = "performance_incident"
        suggested_team = "Platform SRE"
        suggested_priority = Ticket.Priority.URGENT
        draft_reply = (
            "Hi,\n\nWe see you're experiencing performance issues. "
            "We're checking the service health and logs for elevated latency or errors. "
            "We'll update you with mitigation steps and an ETA as soon as we have more detail.\n\n"
            "Best,\nPlatform Team"
        )
        confidence = 0.9

    else:
        classification = "general_support"
        suggested_team = "General Support"
        suggested_priority = Ticket.Priority.MEDIUM
        draft_reply = (
            "Hi,\n\nThanks for reaching out. We've logged your request and "
            "assigned it to our support team for further investigation. "
            "We'll get back to you with a detailed update soon.\n\n"
            "Best,\nSupport Team"
        )
        confidence = 0.72

    summary = ticket.subject[:180]

    return {
        "classification": classification,
        "suggested_team": suggested_team,
        "suggested_priority": suggested_priority,
        "draft_reply": draft_reply,
        "confidence": confidence,
        "summary": summary,
    }


def _kb_results_to_citations(kb_results: list) -> list:
    citations = []
    for r in kb_results[:5]:
        citations.append(
            {
                "document_id": r.get("document_id"),
                "document_title": r.get("document_title"),
                "chunk_id": r.get("chunk_id"),
                "chunk_index": r.get("chunk_index"),
                "score": r.get("score"),
            }
        )
    return citations


def _build_suggestion_fields_from_llm(
    ticket: Ticket,
    llm_result: dict,
    kb_results: list,
) -> tuple[dict, list, dict]:
    """Returns (suggestion_field_kwargs subset, citations, metadata)."""
    metadata = {
        "summary": ticket.subject[:180],
        "category": llm_result.get("category") or llm_result.get("classification") or "general",
    }
    raw = llm_result.get("raw_output") or ""
    if raw:
        metadata["raw_output"] = raw[:2000]

    fields = {
        "classification": llm_result.get("classification")
        or llm_result.get("category")
        or "general",
        "suggested_team": llm_result.get("team") or "support",
        "suggested_priority": llm_result.get("priority") or "medium",
        "draft_reply": llm_result.get("draft_reply") or "",
        "confidence": llm_result.get("confidence"),
        "auto_resolve": bool(llm_result.get("auto_resolve")),
    }
    citations = _kb_results_to_citations(kb_results)
    return fields, citations, metadata


def _build_suggestion_fields_from_heuristic(
    ticket: Ticket,
    kb_results: list,
    *,
    llm_fallback: bool = False,
    llm_error: str = "",
) -> tuple[dict, list, dict]:
    h = _simple_classification_and_resolution(ticket)
    metadata = {
        "summary": h["summary"],
        "category": h["classification"],
    }
    if llm_fallback:
        metadata["llm_fallback"] = True
        metadata["llm_error"] = (llm_error or "")[:500]

    fields = {
        "classification": h["classification"],
        "suggested_team": h["suggested_team"],
        "suggested_priority": h["suggested_priority"],
        "draft_reply": h["draft_reply"],
        "confidence": h["confidence"],
        "auto_resolve": False,
    }
    citations = _kb_results_to_citations(kb_results)
    return fields, citations, metadata


@shared_task
def run_ticket_triage(job_run_id: int) -> int | None:
    """
    Core triage task.
    For demo/dev, the API view may call this **synchronously** as a normal function.

    Flow:
      - marks JobRun running
      - retrieves KB chunks (unless LLM_PROVIDER=heuristic)
      - classifies via Gemini/Ollama (or heuristic-only / LLM fallback)
      - creates Suggestion + TicketEvents
      - optional auto-resolve when model requests it and confidence is high enough
      - marks JobRun succeeded / failed
    Returns suggestion.id on success.
    """
    try:
        with transaction.atomic():
            job = (
                JobRun.objects.select_for_update()
                .select_related("ticket", "organization")
                .get(id=job_run_id)
            )

            if job.status == JobRun.Status.SUCCEEDED and hasattr(job, "suggestion"):
                return job.suggestion.id

            ticket = job.ticket
            org = job.organization

            job.mark_running()

            use_llm = (os.getenv("LLM_PROVIDER") or "").strip().lower() != "heuristic"
            query = f"{ticket.subject}\n\n{ticket.body or ''}"
            kb_results: list = []
            if use_llm:
                kb_results = search_kb_chunks_for_query(org.id, query, k=5)

            llm_error_msg = ""
            if use_llm:
                try:
                    llm_result = classify_ticket_with_llm(ticket, kb_results)
                    fields, citations, metadata = _build_suggestion_fields_from_llm(
                        ticket, llm_result, kb_results
                    )
                except LLMError as exc:
                    llm_error_msg = str(exc)
                    fields, citations, metadata = _build_suggestion_fields_from_heuristic(
                        ticket,
                        kb_results,
                        llm_fallback=True,
                        llm_error=llm_error_msg,
                    )
            else:
                fields, citations, metadata = _build_suggestion_fields_from_heuristic(
                    ticket, kb_results
                )

            do_auto = (
                fields["auto_resolve"]
                and fields["confidence"] is not None
                and fields["confidence"] >= AUTO_RESOLVE_MIN_CONFIDENCE
            )
            suggestion_status = (
                Suggestion.Status.ACCEPTED if do_auto else Suggestion.Status.PENDING
            )

            suggestion = Suggestion.objects.create(
                organization=org,
                ticket=ticket,
                job_run=job,
                status=suggestion_status,
                suggested_priority=fields["suggested_priority"],
                suggested_team=fields["suggested_team"],
                draft_reply=fields["draft_reply"],
                classification=fields["classification"],
                confidence=fields["confidence"],
                citations=citations,
                metadata=metadata,
            )

            TicketEvent.objects.create(
                organization=org,
                ticket=ticket,
                job_run=job,
                event_type=TicketEvent.EventType.AI_TRIAGE_RAN,
                actor_type=TicketEvent.ActorType.AI,
                payload={
                    "job_run_id": job.id,
                    "classification": fields["classification"],
                },
            )

            TicketEvent.objects.create(
                organization=org,
                ticket=ticket,
                job_run=job,
                event_type=TicketEvent.EventType.AI_SUGGESTION_CREATED,
                actor_type=TicketEvent.ActorType.AI,
                payload={
                    "job_run_id": job.id,
                    "suggestion_id": suggestion.id,
                    "suggested_team": suggestion.suggested_team,
                    "suggested_priority": suggestion.suggested_priority,
                },
            )

            if do_auto:
                ticket.priority = fields["suggested_priority"]
                ticket.assigned_team = fields["suggested_team"]
                ticket.status = Ticket.Status.RESOLVED
                ticket.save(update_fields=["priority", "assigned_team", "status"])

                TicketEvent.objects.create(
                    organization=org,
                    ticket=ticket,
                    job_run=job,
                    event_type=TicketEvent.EventType.AUTO_RESOLUTION_APPLIED,
                    actor_type=TicketEvent.ActorType.AI,
                    payload={
                        "suggestion_id": suggestion.id,
                        "confidence": fields["confidence"],
                        "citations": citations,
                    },
                )

            job.mark_succeeded()
            return suggestion.id

    except Exception as exc:
        try:
            job = JobRun.objects.get(id=job_run_id)
            job.mark_failed(str(exc))
        except Exception:
            pass
        return None


@shared_task
def embed_document_chunks(document_id: int) -> None:
    """
    Placeholder / stub for now.
    You can later plug in OpenAI embeddings + pgvector here.

    Keeping this so imports in the rest of the code don't break.
    """
    return None
