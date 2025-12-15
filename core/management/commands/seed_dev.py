import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from core.models import Organization, Membership, Ticket, TicketEvent


User = get_user_model()


SAMPLE_TICKETS = [
    (
        "Payment failed",
        "Customer says card charged but order not created. Please investigate invoice/charge.",
    ),
    (
        "Can't login",
        "User reports 401 on login and password reset fails. Possibly auth outage?",
    ),
    (
        "App crash on launch",
        "Mobile app crashes after update. Seeing exception on startup.",
    ),
    ("Refund request", "Need refund for invoice #1234. Charged twice."),
    ("Password reset not working", "Reset link returns 403. User is blocked."),
    (
        "Bug in dashboard",
        "Dashboard loads but charts show error and fail intermittently.",
    ),
    ("Urgent outage", "Service is down, customers impacted. ASAP fix required."),
    ("Feature question", "How do I export reports? Need help."),
    ("Billing invoice mismatch", "Invoice amount incorrect vs plan."),
    ("Account blocked", "Login failed; account locked; cannot proceed."),
]


class Command(BaseCommand):
    help = "Seed dev data: org + users + memberships + sample tickets (idempotent-ish)."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="Acme Inc", help="Organization name")
        parser.add_argument(
            "--tickets", type=int, default=20, help="Number of tickets to create"
        )
        parser.add_argument("--admin-user", default="admin", help="Admin username")
        parser.add_argument("--agent-user", default="agent", help="Agent username")
        parser.add_argument("--viewer-user", default="viewer", help="Viewer username")
        parser.add_argument(
            "--password", default="password123", help="Password for seeded users"
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        org_name = opts["org"]
        ticket_count = opts["tickets"]

        org, org_created = Organization.objects.get_or_create(name=org_name)

        def upsert_user(username: str, email: str):
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"email": email},
            )
            # Ensure password is set/reset for dev convenience
            user.set_password(opts["password"])
            user.email = email
            user.save(update_fields=["password", "email"])
            return user, created

        admin_u, _ = upsert_user(
            opts["admin_user"], f"{opts['admin_user']}@example.com"
        )
        agent_u, _ = upsert_user(
            opts["agent_user"], f"{opts['agent_user']}@example.com"
        )
        viewer_u, _ = upsert_user(
            opts["viewer_user"], f"{opts['viewer_user']}@example.com"
        )

        # Memberships (idempotent via unique constraint)
        Membership.objects.get_or_create(
            user=admin_u,
            organization=org,
            defaults={"role": Membership.RoleChoices.ADMIN},
        )
        Membership.objects.get_or_create(
            user=agent_u,
            organization=org,
            defaults={"role": Membership.RoleChoices.AGENT},
        )
        Membership.objects.get_or_create(
            user=viewer_u,
            organization=org,
            defaults={"role": Membership.RoleChoices.VIEWER},
        )

        # Create sample tickets (avoid duplicating too much by using a random suffix)
        created_tickets = 0
        for i in range(ticket_count):
            subject, body = random.choice(SAMPLE_TICKETS)
            requester_email = random.choice(
                [
                    "alice@example.com",
                    "bob@example.com",
                    "carol@example.com",
                    "dave@example.com",
                ]
            )

            t = Ticket.objects.create(
                organization=org,
                requester_email=requester_email,
                subject=f"{subject} #{random.randint(1000, 9999)}",
                body=body,
                status=Ticket.Status.OPEN,
                priority=random.choice(
                    [Ticket.Priority.LOW, Ticket.Priority.MEDIUM, Ticket.Priority.HIGH]
                ),
                assigned_team="",
            )

            TicketEvent.objects.create(
                organization=org,
                ticket=t,
                event_type=TicketEvent.EventType.CREATED,
                actor_type=TicketEvent.ActorType.SYSTEM,
                payload={"seeded": True, "at": timezone.now().isoformat()},
            )

            created_tickets += 1

        self.stdout.write(self.style.SUCCESS("Seed complete"))
        self.stdout.write(
            f"Organization: {org.id} ({org.name}){' [created]' if org_created else ''}"
        )
        self.stdout.write(
            f"Users: {admin_u.username}, {agent_u.username}, {viewer_u.username}"
        )
        self.stdout.write(f"Tickets created: {created_tickets}")
        self.stdout.write(f"Password for all seeded users: {opts['password']}")
