# core/api/serializers.py
from django.db import transaction, IntegrityError
from rest_framework import serializers

from core.models import (
    Organization,
    Ticket,
    TicketEvent,
    Suggestion,
    Document,
    DocumentChunk,
)


class TicketCreateSerializer(serializers.ModelSerializer):
    organization_id = serializers.IntegerField(write_only=True)
    priority = serializers.ChoiceField(choices=Ticket.Priority.choices, required=False)

    class Meta:
        model = Ticket
        fields = ["organization_id", "requester_email", "subject", "body", "priority"]

    def validate_organization_id(self, value: int) -> int:
        if not Organization.objects.filter(id=value).exists():
            raise serializers.ValidationError(
                "Organization with given ID does not exist."
            )
        return value

    def create(self, validated_data):
        org_id = validated_data.pop("organization_id")
        org = Organization.objects.get(id=org_id)

        validated_data.setdefault("priority", Ticket.Priority.MEDIUM)

        try:
            with transaction.atomic():
                ticket = Ticket(organization=org, **validated_data)
                ticket._skip_created_event = True  # skip system-created event
                ticket.save()

                TicketEvent.objects.create(
                    organization=org,
                    ticket=ticket,
                    event_type=TicketEvent.EventType.CREATED,
                    actor_type=TicketEvent.ActorType.WEBHOOK,
                    payload={
                        "source": "api",
                        "requester_email": ticket.requester_email,
                    },
                )
                return ticket
        except IntegrityError:
            raise serializers.ValidationError(
                {"detail": "Invalid data (constraint failed)."}
            )


class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = [
            "id",
            "organization",
            "requester_email",
            "subject",
            "body",
            "status",
            "priority",
            "assigned_team",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "assigned_team",
            "created_at",
            "updated_at",
        ]


class TicketUpdateSerializer(serializers.ModelSerializer):
    status = serializers.ChoiceField(choices=Ticket.Status.choices, required=False)
    priority = serializers.ChoiceField(choices=Ticket.Priority.choices, required=False)
    assigned_team = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Ticket
        fields = ["status", "priority", "assigned_team"]

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class TicketEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketEvent
        fields = [
            "id",
            "ticket",
            "event_type",
            "actor_type",
            "payload",
            "created_at",
        ]
        read_only_fields = fields


class SuggestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Suggestion
        fields = [
            "id",
            "organization",
            "ticket",
            "job_run",
            "status",
            "suggested_priority",
            "suggested_team",
            "draft_reply",
            "classification",
            "citations",
            "confidence",
            "metadata",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "ticket",
            "job_run",
            "created_at",
        ]


class SuggestionUpdateAgentSerializer(serializers.ModelSerializer):
    """Agents can only edit the draft reply."""

    class Meta:
        model = Suggestion
        fields = [
            "draft_reply",
            "metadata",
        ]


class SuggestionUpdateAdminSerializer(serializers.ModelSerializer):
    """Admins can override more fields (optional)."""

    suggested_priority = serializers.ChoiceField(
        choices=Ticket.Priority.choices, required=False
    )

    class Meta:
        model = Suggestion
        fields = [
            "status",
            "draft_reply",
            "suggested_team",
            "suggested_priority",
            "metadata",
        ]


class DocumentCreateSerializer(serializers.ModelSerializer):
    title = serializers.CharField(max_length=255)
    text = serializers.CharField(allow_blank=False)
    metadata = serializers.JSONField(required=False)

    class Meta:
        model = Document
        fields = ["title", "text", "metadata"]


class DocumentSerializer(serializers.ModelSerializer):
    chunk_count = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "organization",
            "title",
            "metadata",
            "uploaded_by",
            "created_at",
            "chunk_count",
        ]
        read_only_fields = [
            "id",
            "organization",
            "uploaded_by",
            "created_at",
            "chunk_count",
        ]

    def get_chunk_count(self, obj):
        # Supports either annotation (obj.chunk_count) or fallback to relation count.
        return getattr(obj, "chunk_count", None) or obj.chunks.count()


class DocumentDetailSerializer(serializers.ModelSerializer):
    chunks_preview = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "organization",
            "title",
            "text",
            "metadata",
            "uploaded_by",
            "created_at",
            "chunks_preview",
        ]
        read_only_fields = fields

    def get_chunks_preview(self, obj):
        qs = obj.chunks.order_by("chunk_index").values(
            "chunk_index", "char_start", "char_end"
        )
        return list(qs[:5])


class DocumentChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentChunk
        fields = [
            "id",
            "document",
            "chunk_index",
            "text",
            "char_start",
            "char_end",
            "created_at",
        ]
        read_only_fields = fields


class KnowledgeBaseRetrieveSerializer(serializers.Serializer):
    """
    Payload for KB retrieval.

    Either:
      - provide `query` directly, or
      - provide `ticket_id` (we'll build query from ticket subject+body).

    `k` controls how many chunks to return (default 5).
    """

    query = serializers.CharField(required=False, allow_blank=True)
    ticket_id = serializers.IntegerField(required=False)
    k = serializers.IntegerField(required=False, min_value=1, max_value=50, default=5)

    def validate(self, data):
        query = (data.get("query") or "").strip()
        ticket_id = data.get("ticket_id")

        if not query and not ticket_id:
            raise serializers.ValidationError(
                "Either 'query' or 'ticket_id' must be provided."
            )
        return data
