import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import Organization, Membership


@pytest.mark.django_db
def test_ticket_ingest_detail_and_org_list():
    client = APIClient()

    org = Organization.objects.create(name="Org 1")
    user = User.objects.create_user(username="u1", password="pass")
    Membership.objects.create(user=user, organization=org, role="agent")

    # Public ingest endpoint
    payload = {
        "organization_id": org.id,
        "subject": "Login not working",
        "body": "User cannot log in",
        "priority": "high",
    }
    resp = client.post("/api/tickets/", payload, format="json")
    assert resp.status_code == 201
    ticket_id = resp.data["id"]

    # Authenticated detail
    client.force_authenticate(user=user)
    resp = client.get(f"/api/tickets/{ticket_id}/")
    assert resp.status_code == 200
    assert resp.data["subject"] == "Login not working"

    # Org ticket list
    resp = client.get(f"/api/organizations/{org.id}/tickets/")
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.data["results"]]
    assert ticket_id in ids
