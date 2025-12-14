from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Q
from pgvector.django import VectorField


EMBED_DIM = 384 

# Create your models here.
class Organization(models.Model):
    """
    Represents an organization with a unique name and a creation timestamp.

    Fields:
        name (CharField): The unique name of the organization.
        created_at (DateTimeField): The timestamp when the organization was created.
    """
    name = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name
    
class Membership(models.Model):
    class RoleChoices(models.TextChoices):
        ADMIN = "admin", "Admin"
        AGENT = "agent", "Agent"
        VIEWER = "viewer", "Viewer"
    """
    Represents the membership of a user in an organization.

    Fields:
        user (ForeignKey): A reference to the User model.
        organization (ForeignKey): A reference to the Organization model.
        joined_at (DateTimeField): The timestamp when the user joined the organization.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships"
    )
    organization = models.ForeignKey(
        "Organization",
        on_delete=models.CASCADE,
        related_name="memberships"
    )
    role = models.CharField(
        max_length=20,
        choices=RoleChoices.choices,
        default=RoleChoices.VIEWER,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "organization"],
                name="uniq_membership_user_org"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.organization_id} ({self.role})"
    

class Ticket(models.Model):
    """
    Represents a support ticket within an organization.

    Fields:
        organization (ForeignKey): A reference to the Organization model.
        title (CharField): The title of the ticket.
        description (TextField): The detailed description of the ticket.
        created_at (DateTimeField): The timestamp when the ticket was created.
    """
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In Progress"
        RESOLVED = "resolved", "Resolved"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="tickets"
    )

    requester_email = models.EmailField()
    subject = models.CharField(max_length=250)
    body = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )

    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )
    assigned_team = models.CharField(max_length=100, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"[{self.organization_id}] {self.subject[:50]}"

class TicketEvent(models.Model):

    class EventType(models.TextChoices):
        CREATED = "created", "Created"
        STATUS_CHANGED = "status_changed", "Status Changed"
        PRIORITY_CHANGED = "priority_changed", "Priority Changed"
        ASSIGNED_TEAM_CHANGED = "assigned_team_changed", "Assigned Team Changed"
        COMMENT_ADDED = "comment_added", "Comment Added"
        AI_TRIAGE_RAN = "ai_triage_ran", "AI Triage Ran"
        AI_SUGGESTION_CREATED = "ai_suggestion_created", "AI Suggestion Created"
        AUTO_RESOLUTION_APPLIED = "auto_resolution_applied", "Auto Resolution Applied"
        SUGGESTION_APPROVED = "suggestion_approved", "Suggestion approved"
        SUGGESTION_REJECTED = "suggestion_rejected", "Suggestion rejected"


    class ActorType(models.TextChoices):
        USER = "user", "User"
        SYSTEM = "system", "System"
        AI = "ai", "AI"
        WEBHOOK = "webhook", "Webhook"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="ticket_events")
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="events")
    job_run = models.ForeignKey("JobRun", on_delete=models.SET_NULL,null=True,blank=True,related_name="events",)

    event_type = models.CharField(max_length=50, choices=EventType.choices)
    actor_type = models.CharField(max_length=20, choices=ActorType.choices, default=ActorType.SYSTEM)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ticket_events",
    )

    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "ticket", "created_at"]),
            models.Index(fields=["organization", "event_type", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["ticket", "event_type", "job_run"],
                condition=Q(job_run__isnull=False),
                name="uniq_ticketevent_ticket_type_jobrun",
            )
        ]

    def __str__(self) -> str:
        return f"TicketEvent({self.event_type}) ticket={self.ticket_id}" 
    

    
class JobRun(models.Model):

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"


    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="job_runs")

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="job_runs")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triggered_job_runs",
    )

    # TEMPORARILY nullable for migration safety
    idempotency_key = models.CharField(max_length=80)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "ticket", "created_at"]),
            models.Index(fields=["organization", "status", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["ticket", "idempotency_key"],
                name="uniq_jobrun_ticket_idempotency_key",
            )
        ]

    def mark_running(self):
        self.status = self.Status.RUNNING
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"]) 


    def mark_succeeded(self):
        self.status = self.Status.SUCCEEDED
        self.finished_at = timezone.now()
        self.save(update_fields=["status", "finished_at"])

    def mark_failed(self, msg: str):
        self.status = self.Status.FAILED
        self.error = msg
        self.finished_at = timezone.now()
        self.save(update_fields=["status", "error", "finished_at"])


class Suggestion(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="suggestions",
    )
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name="suggestions",
    )
    job_run = models.OneToOneField(
        JobRun,
        on_delete=models.CASCADE,
        related_name="suggestion",
    )

    # New status field with lowercase codes
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    suggested_priority = models.CharField(
        max_length=20,
        choices=Ticket.Priority.choices,
        null=True,
        blank=True,
    )
    suggested_team = models.CharField(max_length=100, blank=True, default="")
    draft_reply = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "ticket", "created_at"]),
        ]
    



class Document(models.Model):
    """
    Knowledge base document owned by an organization.
    V1 stores raw text; later versions can store file + extraction metadata.
    """
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    title = models.CharField(max_length=255)
    text = models.TextField(blank=True, default="")  # raw extracted text (v1)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_documents",
    )

    metadata = models.JSONField(default=dict, blank=True)  # optional (source, mime, etc.)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Document({self.id}) org={self.organization_id} {self.title[:40]}"


class DocumentChunk(models.Model):
    """
    A chunk (slice) of a Document. This becomes the unit of retrieval + embeddings later.
    """
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="document_chunks",
    )

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )

    chunk_index = models.PositiveIntegerField()
    text = models.TextField()

    # Vector embedding for this chunk (e.g. OpenAI text-embedding-3-small, 1536 dims)
    embedding = VectorField(dimensions=EMBED_DIM, null=True, blank=True)

    # optional but helpful for debugging / later mapping
    char_start = models.PositiveIntegerField(default=0)
    char_end = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["document", "chunk_index"]),
            # vector index (ivfflat/hnsw) will come later once we know query pattern
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "chunk_index"],
                name="uniq_document_chunk_index",
            )
        ]

    def __str__(self) -> str:
        return f"Chunk(doc={self.document_id}, idx={self.chunk_index})"
        


