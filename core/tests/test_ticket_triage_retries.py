from django.test import TestCase
from django.contrib.auth import get_user_model
from unittest.mock import patch
from celery.exceptions import Retry, MaxRetriesExceededError

from core.models import Organization, Membership, Ticket, JobRun
from core.tasks import run_ticket_triage


class TestRunTicketTriageRetries(TestCase):
    def setUp(self):
        User = get_user_model()
        self.org = Organization.objects.create(name="Org")
        self.user = User.objects.create_user(username="u", password="pw")
        Membership.objects.create(user=self.user, organization=self.org, role="admin")
        self.ticket = Ticket.objects.create(
            organization=self.org,
            requester_email="a@b.com",
            subject="Login broken",
            body="401 error",
        )
        self.job = JobRun.objects.create(
            organization=self.org,
            ticket=self.ticket,
            status=JobRun.Status.QUEUED,
            triggered_by=self.user,
            idempotency_key="k1",
        )

    @patch("core.tasks._triage_rules", side_effect=TimeoutError("temp fail"))
    @patch.object(run_ticket_triage, "retry", side_effect=Retry())
    def test_retryable_exception_requests_retry_and_not_failed(self, mock_retry, _):
        with self.assertRaises(Retry):
            run_ticket_triage.run(self.job.id)

        self.job.refresh_from_db()
        self.assertNotEqual(self.job.status, JobRun.Status.FAILED)
        self.assertIn("temp fail", self.job.error)
        self.assertTrue(mock_retry.called)

    @patch("core.tasks._triage_rules", side_effect=TimeoutError("temp fail"))
    @patch.object(run_ticket_triage, "retry", side_effect=MaxRetriesExceededError())
    def test_max_retries_marks_failed(self, mock_retry, _):
        with self.assertRaises(MaxRetriesExceededError):
            run_ticket_triage.run(self.job.id)

        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobRun.Status.FAILED)
        self.assertIn("temp fail", self.job.error)
