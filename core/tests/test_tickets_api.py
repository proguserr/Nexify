# core/tests/test_tickets_api.py
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import Organization, Membership, Ticket, TicketEvent


class TicketAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(name="Org 1")
        self.user = User.objects.create_user(username="u1", password="pass")
        Membership.objects.create(user=self.user, organization=self.org, role="agent")

    def test_ticket_ingest_creates_ticket_and_event(self):
        payload = {
            "organization_id": self.org.id,
            "requester_email": "alice@example.com",
            "subject": "Login issue",
            "body": "I cannot log in to my account.",
            "priority": "high",
        }

        resp = self.client.post("/api/tickets/", payload, format="json")
        self.assertEqual(resp.status_code, 201)

        # One ticket created
        self.assertEqual(Ticket.objects.count(), 1)
        ticket = Ticket.objects.first()
        self.assertEqual(ticket.subject, "Login issue")
        self.assertEqual(ticket.priority, "high")

        # A CREATED TicketEvent should be logged with actor_type=webhook
        events = TicketEvent.objects.filter(ticket=ticket)
        self.assertEqual(events.count(), 1)
        ev = events.first()
        self.assertEqual(ev.event_type, TicketEvent.EventType.CREATED)
        self.assertEqual(ev.actor_type, TicketEvent.ActorType.WEBHOOK)
        self.assertEqual(ev.payload.get("requester_email"), "alice@example.com")

    def test_org_ticket_list_filter_status_and_priority(self):
        # Three tickets with different statuses/priorities
        Ticket.objects.create(
            organization=self.org,
            requester_email="a@example.com",
            subject="A",
            body="Body A",
            status=Ticket.Status.OPEN,
            priority=Ticket.Priority.HIGH,
        )
        Ticket.objects.create(
            organization=self.org,
            requester_email="b@example.com",
            subject="B",
            body="Body B",
            status=Ticket.Status.RESOLVED,
            priority=Ticket.Priority.LOW,
        )
        Ticket.objects.create(
            organization=self.org,
            requester_email="c@example.com",
            subject="C",
            body="Body C",
            status=Ticket.Status.OPEN,
            priority=Ticket.Priority.MEDIUM,
        )

        self.client.force_authenticate(user=self.user)

        # Filter: status=open & priority=high → should return only the first ticket
        url = f"/api/organizations/{self.org.id}/tickets/?status=open&priority=high"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        self.assertIn("results", resp.data)
        results = resp.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["priority"], Ticket.Priority.HIGH)
        self.assertEqual(results[0]["status"], Ticket.Status.OPEN)

    def test_org_ticket_list_supports_ordering_by_id(self):
        # Create tickets in known order
        t1 = Ticket.objects.create(
            organization=self.org,
            requester_email="a@example.com",
            subject="A",
            body="Body A",
        )
        Ticket.objects.create(
            organization=self.org,
            requester_email="b@example.com",
            subject="B",
            body="Body B",
        )
        t3 = Ticket.objects.create(
            organization=self.org,
            requester_email="c@example.com",
            subject="C",
            body="Body C",
        )

        self.client.force_authenticate(user=self.user)

        # Default ordering on the view is ["-id"], but we explicitly test ?ordering here
        url = f"/api/organizations/{self.org.id}/tickets/?ordering=-id"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        ids = [row["id"] for row in resp.data["results"]]
        self.assertEqual(ids[0], t3.id)
        self.assertEqual(ids[-1], t1.id)

    def test_org_ticket_list_requires_membership(self):
        # Another org + ticket
        other_org = Organization.objects.create(name="Other Org")
        Ticket.objects.create(
            organization=other_org,
            requester_email="x@example.com",
            subject="X",
            body="Body X",
        )

        # Authenticated as self.user (only member of self.org)
        self.client.force_authenticate(user=self.user)

        url = f"/api/organizations/{other_org.id}/tickets/"
        resp = self.client.get(url)

        # Should be 404 because user has no membership in other_org
        self.assertEqual(resp.status_code, 404)
