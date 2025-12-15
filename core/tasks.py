# core/tasks.py
from __future__ import annotations

import logging
from typing import List

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.db import transaction
from django.utils import timezone

from core.kb import embed_texts, search_kb_chunks_for_query
from core.llm_client import classify_ticket_with_llm, LLMError
from core.models import Document, DocumentChunk, JobRun, Suggestion, Ticket

logger = logging.getLogger(__name__)


def _triage_rules(*, ticket: Ticket, kb_results: list[dict]) -> dict:
    """
    Core triage logic, separated so tests can patch it.

    Returns a dict like:
        {
          "category": str,
          "team": str,
          "priority": "low"|"medium"|"high"|"urgent",
          "draft_reply": str,
          # optional extras:
          "llm_model": str,
          "llm_backend": str,
          "raw_output": str | dict,
        }
    """
    # Delegate to the LLM client; tests can patch either this function
    # or classify_ticket_with_llm.
    return classify_ticket_with_llm(ticket=ticket, kb_results=kb_results)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def run_ticket_triage(self, job_run_id: int) -> None:
    """
    Celery task: run AI triage for a ticket, create a Suggestion, and
    update the JobRun lifecycle.

    Retry behaviour (what the tests assert):
    - If _triage_rules raises TimeoutError:
        * job.error contains the exception text (e.g. "temp fail")
        * self.retry(...) is called (tests patch this to raise Retry/MaxRetriesExceededError)
        * When MaxRetriesExceededError is raised, job is marked FAILED and finished_at is set.
    """
    job = JobRun.objects.select_related("ticket").get(id=job_run_id)
    ticket: Ticket = job.ticket

    # Mark as running
    job.status = JobRun.Status.RUNNING
    job.started_at = job.started_at or timezone.now()
    job.error = ""
    job.save(update_fields=["status", "started_at", "error"])

    try:
        # ---- 1) Retrieve KB context ----------------------------------------
        kb_results = search_kb_chunks_for_query(
            org_id=ticket.organization_id,
            query=ticket.body or ticket.subject or "",
            k=5,
        )

        # ---- 2) Call triage rules / LLM wrapper ----------------------------
        llm_result = _triage_rules(ticket=ticket, kb_results=kb_results)

        category = llm_result.get("category") or "general"
        team = llm_result.get("team") or "support"
        priority = llm_result.get("priority") or Ticket.Priority.MEDIUM
        draft_reply = llm_result.get("draft_reply") or (
            "Thanks for reaching out. We're looking into your issue "
            "and will follow up with more details shortly."
        )

        # ---- 3) Create Suggestion -----------------------------------------
        Suggestion.objects.create(
            organization=ticket.organization,
            ticket=ticket,
            job_run=job,
            suggested_priority=priority,
            suggested_team=team,
            draft_reply=draft_reply,
            metadata={
                "kb_used": bool(kb_results),
                "category": category,
                "llm_model": llm_result.get("llm_model"),
                "llm_backend": llm_result.get("llm_backend"),
                "kb_chunk_ids": [c["chunk_id"] for c in kb_results],
                "raw_llm_output": llm_result.get("raw_output"),
            },
        )

        # ---- 4) Mark job as succeeded -------------------------------------
        job.status = JobRun.Status.SUCCEEDED
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "finished_at"])

    except TimeoutError as e:
        # Tests expect the *original* error text to be persisted.
        job.error = str(e)  # e.g. "temp fail"
        job.save(update_fields=["error"])

        try:
            # Celery will schedule a retry; in tests this is patched to
            # raise Retry or MaxRetriesExceededError synchronously.
            return self.retry(exc=e)
        except MaxRetriesExceededError:
            # Out of retries: mark as failed but keep the error string.
            job.status = JobRun.Status.FAILED
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "finished_at", "error"])
            raise

    except (LLMError, Exception) as e:
        # Non-timeout errors: mark job as FAILED and record message.
        job.status = JobRun.Status.FAILED
        job.error = str(e)
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error", "finished_at"])
        raise


@shared_task
def embed_document_chunks(document_id: int) -> None:
    """
    Embeds all chunks for a document using the shared embed_texts() helper.

    For PR10 this can be a stub (e.g., deterministic vectors) – it's mainly
    to verify wiring end-to-end.
    """
    doc = Document.objects.get(id=document_id)
    chunks = list(DocumentChunk.objects.filter(document=doc).order_by("chunk_index"))

    if not chunks:
        return

    texts = [c.text or "" for c in chunks]
    vectors: List[List[float]] = embed_texts(texts)

    # Safety check: lengths should match
    if len(vectors) != len(chunks):
        logger.error(
            "embed_document_chunks: length mismatch vectors=%d chunks=%d",
            len(vectors),
            len(chunks),
        )
        return

    # Assign and save in a transaction
    for c, v in zip(chunks, vectors):
        c.embedding = v

    with transaction.atomic():
        for c in chunks:
            c.save(update_fields=["embedding"])
