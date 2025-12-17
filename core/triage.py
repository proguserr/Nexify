# core/triage.py

from __future__ import annotations

from typing import Optional


from .models import Ticket, Suggestion, TicketEvent


def _basic_triage_rules(ticket: Ticket) -> dict:
    """
    Very simple rule-based triage so the UI always has something meaningful
    to show even without a real LLM.

    Returns a dict with keys:
      - resolution
      - summary
      - proposed_status
      - proposed_priority
      - proposed_team_name
      - confidence
    """
    text = f"{ticket.subject}\n\n{ticket.body or ''}".lower()

    proposed_status = "open"
    proposed_priority = ticket.priority or "medium"
    proposed_team_name = ticket.assigned_team_name or "support"
    confidence = 0.65
    resolution_lines: list[str] = []

    if any(k in text for k in ["password", "login", "sign in"]):
        proposed_priority = "low"
        proposed_team_name = "support"
        resolution_lines.append(
            "Confirm the user's identity, walk them through the password reset "
            "flow, and verify they can sign in successfully."
        )

    elif any(k in text for k in ["payment", "billing", "invoice", "refund"]):
        proposed_priority = "high"
        proposed_team_name = "billing"
        resolution_lines.append(
            "Review recent invoices and payment status, correct any billing "
            "discrepancies, and send the customer a confirmation of the "
            "updated balance."
        )

    elif any(k in text for k in ["error", "exception", "stack trace", "500", "crash"]):
        proposed_priority = "high"
        proposed_team_name = "backend"
        resolution_lines.append(
            "Reproduce the error, capture logs and request context, create a "
            "bug ticket for the backend team, and notify the user once a fix "
            "is deployed."
        )

    elif any(k in text for k in ["slow", "latency", "performance"]):
        proposed_priority = "medium"
        proposed_team_name = "platform"
        resolution_lines.append(
            "Gather response-time metrics for the affected endpoints, check "
            "recent deployments or incidents, and escalate to the platform "
            "team if regression is confirmed."
        )

    if not resolution_lines:
        resolution_lines.append(
            "Acknowledge the issue, collect any missing details (steps to "
            "reproduce, screenshots, expected vs actual behaviour), and route "
            "the ticket to the default support queue for deeper investigation."
        )

    # Short summary for the console
    if ticket.body:
        base_summary = ticket.body.strip().split("\n", 1)[0]
    else:
        base_summary = ticket.subject

    summary = base_summary
    if len(summary) > 160:
        summary = summary[:157] + "..."

    resolution = " ".join(resolution_lines)

    return {
        "resolution": resolution,
        "summary": summary,
        "proposed_status": proposed_status,
        "proposed_priority": proposed_priority,
        "proposed_team_name": proposed_team_name,
        "confidence": confidence,
    }


def generate_triage_suggestion(
    ticket: Ticket,
    *,
    idempotency_key: Optional[str] = None,
) -> Suggestion:
    """
    Synchronous triage helper used by the /trigger-triage/ endpoint.

    - Applies basic rules
    - Upserts a Suggestion for the ticket
    - Emits TicketEvents for audit
    """
    # Audit: triage was requested
    TicketEvent.objects.create(
        ticket=ticket,
        event_type="triage_requested",
        metadata={"idempotency_key": idempotency_key},
    )

    triage = _basic_triage_rules(ticket)

    suggestion, _created = Suggestion.objects.get_or_create(
        ticket=ticket,
        defaults={
            "status": "pending",
            "summary": triage["summary"],
            "resolution": triage["resolution"],
            "confidence": triage["confidence"],
        },
    )

    # Always update with latest triage info
    suggestion.summary = triage["summary"]
    suggestion.resolution = triage["resolution"]
    suggestion.confidence = triage["confidence"]
    suggestion.status = "pending"
    meta = suggestion.metadata or {}
    if idempotency_key:
        meta["idempotency_key"] = idempotency_key
    meta["proposed_status"] = triage["proposed_status"]
    meta["proposed_priority"] = triage["proposed_priority"]
    meta["proposed_team_name"] = triage["proposed_team_name"]
    suggestion.metadata = meta
    suggestion.save()

    # Audit: triage succeeded
    TicketEvent.objects.create(
        ticket=ticket,
        event_type="triage_succeeded",
        metadata={"suggestion_id": suggestion.id},
    )

    return suggestion
