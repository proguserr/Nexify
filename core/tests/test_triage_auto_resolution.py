import pytest
from unittest.mock import patch
from django.contrib.auth.models import User

from core.models import (
    Organization,
    Membership,
    Ticket,
    JobRun,
    Suggestion,
    TicketEvent,
)
from core.tasks import run_ticket_triage


@pytest.mark.django_db
def test_triage_auto_resolve_updates_ticket_and_creates_event():
    org = Organization.objects.create(name="Org 1")
    user = User.objects.create_user(username="u1", password="pass")
    Membership.objects.create(user=user, organization=org, role="agent")

    ticket = Ticket.objects.create(
        organization=org,
        subject="Refund request",
        body="I want a refund for my last invoice.",
        priority=Ticket.Priority.MEDIUM,
        status=Ticket.Status.OPEN,
    )

    job = JobRun.objects.create(
        organization=org,
        ticket=ticket,
        status=JobRun.Status.QUEUED,
        idempotency_key="auto-resolve-test",
        triggered_by=user,
    )

    kb_stub = [
        {
            "document_id": 1,
            "document_title": "Refund Policy",
            "chunk_id": 42,
            "chunk_index": 0,
            "text": "Refunds allowed within 14 days.",
            "score": 0.01,
        }
    ]

    with patch("core.tasks.search_kb_chunks_for_query") as mock_search, patch(
        "core.tasks._triage_rules"
    ) as mock_rules:
        mock_search.return_value = kb_stub
        mock_rules.return_value = {
            "category": "billing",
            "team": "billing",
            "priority": "urgent",
            "draft_reply": "We processed your refund.",
            "classification": "billing_refund",
            "confidence": 0.9,
            "auto_resolve": True,
        }

        # Call task synchronously in tests
        run_ticket_triage(job.id)

    job.refresh_from_db()
    ticket.refresh_from_db()
    suggestion = Suggestion.objects.get(job_run=job)

    # Job succeeded
    assert job.status == JobRun.Status.SUCCEEDED
    assert job.error == ""

    # Ticket auto-resolved
    assert ticket.status == Ticket.Status.RESOLVED
    assert ticket.priority == Ticket.Priority.URGENT
    assert ticket.assigned_team == "billing"

    # Suggestion enriched
    assert suggestion.classification == "billing_refund"
    assert suggestion.confidence == pytest.approx(0.9)
    assert suggestion.status == Suggestion.Status.ACCEPTED
    assert suggestion.citations
    assert suggestion.citations[0]["chunk_id"] == 42

    # Event emitted
    events = TicketEvent.objects.filter(
        ticket=ticket,
        event_type=TicketEvent.EventType.AUTO_RESOLUTION_APPLIED,
    )
    assert events.count() == 1
    ev = events.first()
    assert ev.payload["suggestion_id"] == suggestion.id
    assert ev.payload["confidence"] == pytest.approx(0.9)
    assert ev.payload["citations"][0]["chunk_id"] == 42


@pytest.mark.django_db
def test_triage_low_confidence_does_not_auto_resolve():
    org = Organization.objects.create(name="Org 1")
    user = User.objects.create_user(username="u1", password="pass")
    Membership.objects.create(user=user, organization=org, role="agent")

    ticket = Ticket.objects.create(
        organization=org,
        subject="Refund request",
        body="I want a refund for my last invoice.",
        priority=Ticket.Priority.MEDIUM,
        status=Ticket.Status.OPEN,
    )

    job = JobRun.objects.create(
        organization=org,
        ticket=ticket,
        status=JobRun.Status.QUEUED,
        idempotency_key="auto-resolve-low-conf",
        triggered_by=user,
    )

    kb_stub = [
        {
            "document_id": 1,
            "document_title": "Refund Policy",
            "chunk_id": 42,
            "chunk_index": 0,
            "text": "Refunds allowed within 14 days.",
            "score": 0.01,
        }
    ]

    with patch("core.tasks.search_kb_chunks_for_query") as mock_search, patch(
        "core.tasks._triage_rules"
    ) as mock_rules:
        mock_search.return_value = kb_stub
        mock_rules.return_value = {
            "category": "billing",
            "team": "billing",
            "priority": "urgent",
            "draft_reply": "We will check your request.",
            "classification": "billing_refund",
            "confidence": 0.5,  # below threshold
            "auto_resolve": True,
        }

        run_ticket_triage(job.id)

    job.refresh_from_db()
    ticket.refresh_from_db()
    suggestion = Suggestion.objects.get(job_run=job)

    # Job succeeded, suggestion created
    assert job.status == JobRun.Status.SUCCEEDED
    assert suggestion.classification == "billing_refund"
    assert suggestion.confidence == pytest.approx(0.5)
    assert suggestion.status == Suggestion.Status.PENDING

    # Ticket NOT auto-resolved (abstain)
    assert ticket.status == Ticket.Status.OPEN
    assert ticket.priority == Ticket.Priority.MEDIUM

    # Citations still present for UI
    assert suggestion.citations
    assert suggestion.citations[0]["chunk_id"] == 42

    # No auto-resolution event
    events = TicketEvent.objects.filter(
        ticket=ticket,
        event_type=TicketEvent.EventType.AUTO_RESOLUTION_APPLIED,
    )
    assert events.count() == 0
