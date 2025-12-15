from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Organization, Ticket


class TicketIngestAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/tickets/"
        self.org = Organization.objects.create(name="Test Org")

    def test_create_ticket_success_201(self):
        payload = {
            "organization_id": self.org.id,
            "requester_email": "sam@test.com",
            "subject": "Login failing",
            "body": "Cannot sign in",
            "priority": "high",
        }

        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, 201)

        data = resp.json()
        self.assertIn("id", data)
        self.assertEqual(data["organization"], self.org.id)
        self.assertEqual(data["requester_email"], "sam@test.com")
        self.assertEqual(data["subject"], "Login failing")
        self.assertEqual(data["priority"], "high")
        self.assertEqual(data["status"], "open")

        self.assertTrue(Ticket.objects.filter(id=data["id"]).exists())

    def test_create_ticket_invalid_priority_400(self):
        payload = {
            "organization_id": self.org.id,
            "requester_email": "sam@test.com",
            "subject": "BAD-PRIORITY",
            "body": "x",
            "priority": "p2",  # invalid
        }

        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, 400)

        data = resp.json()
        self.assertIn("priority", data)  # DRF default error shape

    def test_create_ticket_invalid_org_400(self):
        payload = {
            "organization_id": 99999,  # invalid
            "requester_email": "sam@test.com",
            "subject": "BAD-ORG",
            "body": "x",
            "priority": "high",
        }

        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, 400)

        data = resp.json()
        self.assertIn("organization_id", data)  # from validate_organization_id()
