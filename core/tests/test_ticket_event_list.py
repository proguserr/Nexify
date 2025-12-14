# core/tests/test_ticket_event_list.py

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from core.models import Organization, Membership, Ticket, TicketEvent


User = get_user_model()


class TestTicketEventListView(APITestCase):
    def setUp(self):
        # Orgs
        self.org1 = Organization.objects.create(name="Org 1")
        self.org2 = Organization.objects.create(name="Org 2")

        # Users
        self.member = User.objects.create_user(username="member", email="m@x.com", password="pass1234")
        self.outsider = User.objects.create_user(username="outsider", email="o@x.com", password="pass1234")

        # Membership: member belongs to org1 only
        Membership.objects.create(user=self.member, organization=self.org1, role=Membership.RoleChoices.ADMIN)

        # Tickets
        self.ticket1 = Ticket.objects.create(
            organization=self.org1,
            requester_email="req@x.com",
            subject="T1",
            body="Body",
            status=Ticket.Status.OPEN,
            priority=Ticket.Priority.HIGH,
            assigned_team="",
        )
        self.ticket2 = Ticket.objects.create(
            organization=self.org1,
            requester_email="req2@x.com",
            subject="T2",
            body="Body",
            status=Ticket.Status.OPEN,
            priority=Ticket.Priority.MEDIUM,
            assigned_team="",
        )
        self.ticket_other_org = Ticket.objects.create(
            organization=self.org2,
            requester_email="req3@x.com",
            subject="T3",
            body="Body",
            status=Ticket.Status.OPEN,
            priority=Ticket.Priority.LOW,
            assigned_team="",
        )

        # Events for ticket1 with controlled timestamps
        now = timezone.now()
        self.e1 = TicketEvent.objects.create(
            organization=self.org1,
            ticket=self.ticket1,
            event_type=TicketEvent.EventType.CREATED,
            actor_type=TicketEvent.ActorType.SYSTEM,
            payload={"x": 1},
        )
        self.e2 = TicketEvent.objects.create(
            organization=self.org1,
            ticket=self.ticket1,
            event_type=TicketEvent.EventType.STATUS_CHANGED,
            actor_type=TicketEvent.ActorType.WEBHOOK,
            payload={"from": "open", "to": "in_progress"},
        )
        self.e3 = TicketEvent.objects.create(
            organization=self.org1,
            ticket=self.ticket1,
            event_type=TicketEvent.EventType.STATUS_CHANGED,
            actor_type=TicketEvent.ActorType.SYSTEM,
            payload={"from": "in_progress", "to": "resolved"},
        )

        # Set created_at explicitly (auto_now_add prevents direct set on create)
        TicketEvent.objects.filter(id=self.e1.id).update(created_at=now - timedelta(days=5))
        TicketEvent.objects.filter(id=self.e2.id).update(created_at=now - timedelta(days=3))
        TicketEvent.objects.filter(id=self.e3.id).update(created_at=now - timedelta(days=1))

        # Event for another ticket in same org (must NOT leak into ticket1 events)
        self.other_ticket_event = TicketEvent.objects.create(
            organization=self.org1,
            ticket=self.ticket2,
            event_type=TicketEvent.EventType.CREATED,
            actor_type=TicketEvent.ActorType.SYSTEM,
            payload={"t": "other"},
        )

        # Event in another org (must NOT be accessible)
        self.other_org_event = TicketEvent.objects.create(
            organization=self.org2,
            ticket=self.ticket_other_org,
            event_type=TicketEvent.EventType.CREATED,
            actor_type=TicketEvent.ActorType.SYSTEM,
            payload={"t": "org2"},
        )

    def _url(self, ticket_id: int) -> str:
        return reverse("ticket-events", kwargs={"pk": ticket_id})

    def test_requires_auth(self):
        url = self._url(self.ticket1.id)
        res = self.client.get(url)
        self.assertIn(res.status_code, (401, 403))  # depends on auth config

    def test_non_member_gets_404(self):
        url = self._url(self.ticket1.id)
        self.client.force_authenticate(user=self.outsider)
        res = self.client.get(url)
        self.assertEqual(res.status_code, 404)

    def test_no_cross_org_leak(self):
        url = self._url(self.ticket_other_org.id)
        self.client.force_authenticate(user=self.member)
        res = self.client.get(url)
        self.assertEqual(res.status_code, 404)

    def test_list_is_paginated_shape(self):
        url = self._url(self.ticket1.id)
        self.client.force_authenticate(user=self.member)
        res = self.client.get(url)

        self.assertEqual(res.status_code, 200)
        self.assertIn("count", res.data)
        self.assertIn("next", res.data)
        self.assertIn("previous", res.data)
        self.assertIn("results", res.data)

        # Only ticket1 events should be present
        ticket_ids = {row["ticket"] for row in res.data["results"]}
        self.assertEqual(ticket_ids, {self.ticket1.id})

    def test_filter_event_type(self):
        url = self._url(self.ticket1.id)
        self.client.force_authenticate(user=self.member)
        res = self.client.get(url, {"event_type": "status_changed"})

        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.data["count"], 1)
        for row in res.data["results"]:
            self.assertEqual(row["event_type"], "status_changed")
            self.assertEqual(row["ticket"], self.ticket1.id)

    def test_filter_created_range(self):
        url = self._url(self.ticket1.id)
        self.client.force_authenticate(user=self.member)

        # Include only events from (now-4d) to (now-2d) => should match e2 only
        created_from = (timezone.now() - timedelta(days=4)).isoformat().replace("+00:00", "Z")
        created_to = (timezone.now() - timedelta(days=2)).isoformat().replace("+00:00", "Z")

        res = self.client.get(url, {"created_from": created_from, "created_to": created_to})
        self.assertEqual(res.status_code, 200)

        ids = [row["id"] for row in res.data["results"]]
        # Because filtering is by created_at, and we forced timestamps, only e2 should be in range.
        self.assertEqual(set(ids), {self.e2.id})

    def test_ordering_created_at_asc(self):
        url = self._url(self.ticket1.id)
        self.client.force_authenticate(user=self.member)

        res = self.client.get(url, {"ordering": "created_at"})
        self.assertEqual(res.status_code, 200)

        created_ats = [row["created_at"] for row in res.data["results"]]
        self.assertEqual(created_ats, sorted(created_ats))

        ids = [row["id"] for row in res.data["results"]]
        # Ascending should be e1 (oldest), e2, e3 (newest)
        self.assertEqual(ids[:3], [self.e1.id, self.e2.id, self.e3.id])

    def test_pagination_page_size(self):
        # Create many more events for ticket1 to force pagination
        now = timezone.now()
        extra_ids = []
        for i in range(25):
            ev = TicketEvent.objects.create(
                organization=self.org1,
                ticket=self.ticket1,
                event_type=TicketEvent.EventType.STATUS_CHANGED,
                actor_type=TicketEvent.ActorType.SYSTEM,
                payload={"i": i},
            )
            extra_ids.append(ev.id)

        # spread timestamps a bit (not strictly necessary for pagination)
        for idx, ev_id in enumerate(extra_ids):
            TicketEvent.objects.filter(id=ev_id).update(created_at=now - timedelta(minutes=idx))

        url = self._url(self.ticket1.id)
        self.client.force_authenticate(user=self.member)

        res = self.client.get(url, {"page_size": 10})
        self.assertEqual(res.status_code, 200)

        self.assertEqual(len(res.data["results"]), 10)
        self.assertIsNotNone(res.data["next"])
        self.assertEqual(res.data["previous"], None)
        self.assertGreaterEqual(res.data["count"], 28)  # 3 original + 25 extra