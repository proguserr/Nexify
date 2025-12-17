# core/tasks.py
from __future__ import annotations

from celery import shared_task
from django.db import transaction

from core.models import JobRun, Ticket, Suggestion, TicketEvent


def _simple_classification_and_resolution(ticket: Ticket) -> dict:
    """
    Tiny heuristic "AI" so the UI looks alive.
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


@shared_task
def run_ticket_triage(job_run_id: int) -> int | None:
    """
    Core triage task.
    For demo/dev, we call this **synchronously** from the API view as a normal function.
    It:
      - marks JobRun running
      - generates a Suggestion
      - emits TicketEvent rows
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

            # If we've already succeeded, don't do work again.
            if job.status == JobRun.Status.SUCCEEDED and hasattr(job, "suggestion"):
                return job.suggestion.id

            ticket = job.ticket
            org = job.organization

            # Mark job as running
            job.mark_running()

            # --- very simple “AI” triage ---
            fields = _simple_classification_and_resolution(ticket)

            suggestion = Suggestion.objects.create(
                organization=org,
                ticket=ticket,
                job_run=job,
                status=Suggestion.Status.PENDING,
                suggested_priority=fields["suggested_priority"],
                suggested_team=fields["suggested_team"],
                draft_reply=fields["draft_reply"],
                classification=fields["classification"],
                confidence=fields["confidence"],
                citations=[],  # v1: empty, later we can plug in KB/RAG
                metadata={"summary": fields["summary"]},
            )

            # Emit TicketEvents so your “events” panel looks alive
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

            job.mark_succeeded()
            return suggestion.id

    except Exception as exc:
        # Best-effort failure update
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

    Keeping this so imports in the rest of the code don’t break.
    """
    # For demo purposes we do nothing here.
    return None
