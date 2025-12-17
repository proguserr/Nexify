import pytest
from unittest.mock import patch
from django.contrib.auth.models import User

from core.models import Organization, Membership, Ticket, JobRun, Suggestion
from core.tasks import run_ticket_triage


@pytest.mark.django_db
def test_triage_happy_path_creates_suggestion_and_updates_job():
    org = Organization.objects.create(name="Org 1")
    user = User.objects.create_user(username="u1", password="pass")
    Membership.objects.create(user=user, organization=org, role="agent")

    ticket = Ticket.objects.create(
        organization=org,
        subject="Missing invoice",
        body="I did not receive my invoice for last month.",
        priority="high",
        status="open",
    )

    job = JobRun.objects.create(
        organization=org,
        ticket=ticket,
        status=JobRun.Status.QUEUED,
        idempotency_key="test-happy-path",
        triggered_by=user,
    )

    # Patch the LLM client so we don't hit Ollama in tests
    with patch("core.llm_client.classify_ticket_with_llm") as mock_llm:
        mock_llm.return_value = {
            "category": "billing",
            "team": "support",
            "priority": "medium",
            "draft_reply": "Mock reply from test",
        }

        run_ticket_triage(job.id)

    job.refresh_from_db()
    assert job.status == JobRun.Status.SUCCEEDED
    assert job.error == ""

    suggestion = Suggestion.objects.get(job_run=job)
    assert suggestion.ticket_id == ticket.id
    assert suggestion.organization_id == org.id
    assert suggestion.suggested_team == "support"
    assert suggestion.suggested_priority == "medium"
    assert suggestion.draft_reply == "Mock reply from test"
    assert suggestion.metadata.get("category") == "billing"
