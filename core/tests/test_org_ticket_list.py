from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model
from core.models import Organization, Membership, Ticket


class TestOrganizationTicketListView(APITestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.orgA = Organization.objects.create(name="OrgA")
        self.orgB = Organization.objects.create(name="OrgB")

        self.member = User.objects.create_user(username="member", password="x")
        self.stranger = User.objects.create_user(username="stranger", password="x")

        Membership.objects.create(
            user=self.member, organization=self.orgA, role="viewer"
        )

        now = timezone.now()

        # OrgA tickets
        self.t1 = Ticket.objects.create(
            organization=self.orgA,
            requester_email="a@a.com",
            subject="t1",
            body="x",
            status="open",
            priority="high",
            assigned_team="",
        )
        self.t2 = Ticket.objects.create(
            organization=self.orgA,
            requester_email="a@a.com",
            subject="t2",
            body="x",
            status="open",
            priority="urgent",
            assigned_team="",
        )
        self.t3 = Ticket.objects.create(
            organization=self.orgA,
            requester_email="a@a.com",
            subject="t3",
            body="x",
            status="resolved",
            priority="urgent",
            assigned_team="payments",
        )

        # OrgB ticket (should never leak into OrgA list)
        Ticket.objects.create(
            organization=self.orgB,
            requester_email="b@b.com",
            subject="leak",
            body="x",
            status="open",
            priority="urgent",
            assigned_team="",
        )

        # Fix created_at spread
        Ticket.objects.filter(pk=self.t1.pk).update(created_at=now - timedelta(days=2))
        Ticket.objects.filter(pk=self.t2.pk).update(created_at=now - timedelta(days=1))
        Ticket.objects.filter(pk=self.t3.pk).update(created_at=now)

    # Auth + tenancy safety
    def test_requires_auth(self):
        url = f"/api/organizations/{self.orgA.id}/tickets/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 401)

    def test_non_member_gets_404(self):
        self.client.force_authenticate(user=self.stranger)
        url = f"/api/organizations/{self.orgA.id}/tickets/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 404)

    # Filter: status

    def test_filter_status(self):
        self.client.force_authenticate(user=self.member)
        url = f"/api/organizations/{self.orgA.id}/tickets/?status=open"
        res = self.client.get(url)

        self.assertEqual(res.status_code, 200)
        ids = [r["id"] for r in res.data["results"]]
        self.assertTrue(self.t1.id in ids and self.t2.id in ids)
        self.assertFalse(self.t3.id in ids)

    # Filter: priority

    def test_filter_priority(self):
        self.client.force_authenticate(user=self.member)
        url = f"/api/organizations/{self.orgA.id}/tickets/?priority=urgent"
        res = self.client.get(url)

        self.assertEqual(res.status_code, 200)
        ids = [r["id"] for r in res.data["results"]]
        self.assertTrue(self.t2.id in ids and self.t3.id in ids)
        self.assertFalse(self.t1.id in ids)

    # Filter: created_from + created_to

    def test_filter_created_range(self):
        self.client.force_authenticate(user=self.member)

        from_ts = (
            (timezone.now() - timezone.timedelta(days=1, hours=12))
            .isoformat()
            .replace("+00:00", "Z")
        )
        to_ts = (
            (timezone.now() + timezone.timedelta(hours=1))
            .isoformat()
            .replace("+00:00", "Z")
        )

        url = f"/api/organizations/{self.orgA.id}/tickets/?created_from={from_ts}&created_to={to_ts}"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        ids = [r["id"] for r in res.data["results"]]
        # should include t2 (yesterday) and t3 (today), not t1 (2 days ago)
        self.assertTrue(self.t2.id in ids and self.t3.id in ids)
        self.assertFalse(self.t1.id in ids)

    # Ordering: ?ordering=created_at

    def test_ordering_created_at_asc(self):
        self.client.force_authenticate(user=self.member)
        url = f"/api/organizations/{self.orgA.id}/tickets/?ordering=created_at"
        res = self.client.get(url)

        self.assertEqual(res.status_code, 200)
        ids = [r["id"] for r in res.data["results"]]
        # oldest first => t1 then t2 then t3
        self.assertEqual(ids[:3], [self.t1.id, self.t2.id, self.t3.id])

    # Pagination: page_size + page

    def test_pagination_page_size(self):
        self.client.force_authenticate(user=self.member)
        url = f"/api/organizations/{self.orgA.id}/tickets/?page_size=2"
        res = self.client.get(url)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 3)
        self.assertEqual(len(res.data["results"]), 2)
        self.assertIsNotNone(res.data["next"])

    # No cross-org leakage

    def test_no_cross_org_leak(self):
        self.client.force_authenticate(user=self.member)
        url = f"/api/organizations/{self.orgA.id}/tickets/"
        res = self.client.get(url)

        subjects = [r["subject"] for r in res.data["results"]]
        self.assertFalse("leak" in subjects)
