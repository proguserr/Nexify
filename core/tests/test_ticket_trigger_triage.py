from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Organization, Membership, Ticket, JobRun


User = get_user_model()


class TestTicketTriggerTriageView(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Org A")
        self.user = User.objects.create_user(username="u1", password="pass12345")
        Membership.objects.create(
            user=self.user, organization=self.org, role=Membership.RoleChoices.AGENT
        )

        self.ticket = Ticket.objects.create(
            organization=self.org,
            requester_email="test@example.com",
            subject="Login failing 401",
            body="Cannot sign in, getting 401",
            status=Ticket.Status.OPEN,
            priority=Ticket.Priority.MEDIUM,
            assigned_team="",
        )

        self.url = reverse("ticket-trigger-triage", kwargs={"pk": self.ticket.id})

    def test_requires_auth(self):
        resp = self.client.post(
            self.url,
            data={},
            format="json",
            HTTP_IDEMPOTENCY_KEY="test-triage-1",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_member_gets_404(self):
        u2 = User.objects.create_user(username="u2", password="pass12345")
        self.client.force_authenticate(user=u2)

        resp = self.client.post(
            self.url,
            data={},
            format="json",
            HTTP_IDEMPOTENCY_KEY="test-triage-1",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_no_cross_org_leak(self):
        org2 = Organization.objects.create(name="Org B")
        ticket2 = Ticket.objects.create(
            organization=org2,
            requester_email="x@example.com",
            subject="Payment refund",
            body="Refund not received",
        )

        self.client.force_authenticate(user=self.user)
        url2 = reverse("ticket-trigger-triage", kwargs={"pk": ticket2.id})

        resp = self.client.post(
            url2,
            data={},
            format="json",
            HTTP_IDEMPOTENCY_KEY="test-triage-1",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @patch("core.api.views.run_ticket_triage.delay")
    def test_creates_jobrun_and_enqueues_task(self, delay_mock):
        self.client.force_authenticate(user=self.user)

        resp = self.client.post(
            self.url, data={}, format="json", HTTP_IDEMPOTENCY_KEY="test-triage-1"
        )
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)

        job_id = resp.data["job_run_id"]
        job = JobRun.objects.get(id=job_id)

        self.assertEqual(job.organization_id, self.org.id)
        self.assertEqual(job.ticket_id, self.ticket.id)
        self.assertEqual(job.status, JobRun.Status.QUEUED)
        self.assertEqual(job.triggered_by_id, self.user.id)

        delay_mock.assert_called_once_with(job.id)


class TestTicketTriggerTriageIdempotency(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="sam", password="pw123")

        self.org = Organization.objects.create(name="Org1")
        Membership.objects.create(
            user=self.user, organization=self.org, role=Membership.RoleChoices.ADMIN
        )

        self.ticket = Ticket.objects.create(
            organization=self.org,
            requester_email="a@b.com",
            subject="payment failed",
            body="I got charged twice",
        )

        self.url = reverse("ticket-trigger-triage", kwargs={"pk": self.ticket.id})
        self.client.force_authenticate(user=self.user)

    def test_requires_idempotency_key_header(self):
        resp = self.client.post(self.url, data={}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Idempotency-Key", resp.data)

    def test_rejects_too_long_idempotency_key(self):
        resp = self.client.post(
            self.url,
            data={},
            format="json",
            HTTP_IDEMPOTENCY_KEY="x" * 81,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Idempotency-Key", resp.data)

    @patch("core.api.views.run_ticket_triage.delay")
    def test_first_call_creates_jobrun_and_enqueues(self, delay_mock):
        idem = "triage-1"
        resp = self.client.post(
            self.url, data={}, format="json", HTTP_IDEMPOTENCY_KEY=idem
        )

        self.assertEqual(resp.status_code, 202)
        self.assertTrue(resp.data["created"])
        self.assertEqual(resp.data["status"], JobRun.Status.QUEUED)

        job_id = resp.data["job_run_id"]
        job = JobRun.objects.get(id=job_id)

        self.assertEqual(job.ticket_id, self.ticket.id)
        self.assertEqual(job.organization_id, self.org.id)
        self.assertEqual(job.idempotency_key, idem)

        delay_mock.assert_called_once_with(job.id)

    @patch("core.api.views.run_ticket_triage.delay")
    def test_same_idempotency_key_returns_same_jobrun(self, delay_mock):
        idem = "triage-dup"

        r1 = self.client.post(
            self.url, data={}, format="json", HTTP_IDEMPOTENCY_KEY=idem
        )
        job_id_1 = r1.data["job_run_id"]

        # Make it look "already started" so your should_enqueue logic doesn't enqueue again.
        JobRun.objects.filter(id=job_id_1).update(
            status=JobRun.Status.RUNNING, started_at=timezone.now()
        )

        r2 = self.client.post(
            self.url, data={}, format="json", HTTP_IDEMPOTENCY_KEY=idem
        )

        self.assertEqual(r2.status_code, 200)
        self.assertFalse(r2.data["created"])
        self.assertEqual(r2.data["job_run_id"], job_id_1)

        # still only enqueued once (from first call)
        delay_mock.assert_called_once()

        self.assertEqual(
            JobRun.objects.filter(ticket=self.ticket, idempotency_key=idem).count(), 1
        )

    @patch("core.api.views.run_ticket_triage.delay")
    def test_different_idempotency_key_creates_new_jobrun(self, delay_mock):
        r1 = self.client.post(
            self.url, data={}, format="json", HTTP_IDEMPOTENCY_KEY="k1"
        )
        r2 = self.client.post(
            self.url, data={}, format="json", HTTP_IDEMPOTENCY_KEY="k2"
        )

        self.assertEqual(r1.status_code, 202)
        self.assertEqual(r2.status_code, 202)
        self.assertNotEqual(r1.data["job_run_id"], r2.data["job_run_id"])

        self.assertEqual(JobRun.objects.filter(ticket=self.ticket).count(), 2)
        self.assertEqual(delay_mock.call_count, 2)
