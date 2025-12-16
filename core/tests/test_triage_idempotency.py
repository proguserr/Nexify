import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import Organization, Membership, Ticket, JobRun


@pytest.mark.django_db
def test_triage_trigger_idempotency_same_key_same_job():
    client = APIClient()

    org = Organization.objects.create(name="Org 1")
    user = User.objects.create_user(username="u1", password="pass")
    Membership.objects.create(user=user, organization=org, role="agent")

    ticket = Ticket.objects.create(
        organization=org,
        subject="Triage idempotency test",
        body="Something is broken",
        priority="high",
        status="open",
    )

    client.force_authenticate(user=user)

    # First call with key
    resp1 = client.post(
        f"/api/tickets/{ticket.id}/trigger-triage/",
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="test-key-123",
    )
    assert resp1.status_code in (200, 202)
    job_run_id_1 = resp1.data["job_run_id"]

    # Second call with same key
    resp2 = client.post(
        f"/api/tickets/{ticket.id}/trigger-triage/",
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="test-key-123",
    )
    assert resp2.status_code == 200
    job_run_id_2 = resp2.data["job_run_id"]

    assert job_run_id_1 == job_run_id_2
    assert JobRun.objects.filter(id=job_run_id_1).count() == 1
