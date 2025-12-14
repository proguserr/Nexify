import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import Organization, Membership, Ticket


@pytest.mark.django_db
def test_ticket_detail_respects_org_boundary():
    client = APIClient()

    org1 = Organization.objects.create(name="Org 1")
    org2 = Organization.objects.create(name="Org 2")

    user = User.objects.create_user(username="u1", password="pass")
    Membership.objects.create(user=user, organization=org1, role="agent")

    ticket_other_org = Ticket.objects.create(
        organization=org2,
        subject="Secret ticket",
        body="Should not be visible to org1 user",
        priority="medium",
        status="open",
    )

    client.force_authenticate(user=user)

    # User from org1 should NOT see ticket from org2
    resp = client.get(f"/api/tickets/{ticket_other_org.id}/")
    assert resp.status_code == 404