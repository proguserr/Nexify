# core/api/views.py
from django.db import transaction, IntegrityError
from django.db.models import Count
from django.shortcuts import get_object_or_404

from rest_framework import status, viewsets, mixins
from rest_framework.exceptions import NotFound, ValidationError, PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django_filters.rest_framework import DjangoFilterBackend

from core.api.filters import TicketFilter, TicketEventFilter
from core.api.pagination import StandardPagination
from core.api.permissions import TicketRolePermission
from core.api.tenancy import user_org_ids, user_role_in_org

from core.models import (
    Organization,
    Membership,
    Ticket,
    TicketEvent,
    Suggestion,
    JobRun,
    Document,
    DocumentChunk,
)

from core.tasks import run_ticket_triage
from core.tasks import embed_document_chunks

from .serializers import (
    TicketCreateSerializer,
    TicketSerializer,
    TicketUpdateSerializer,
    TicketEventSerializer,
    SuggestionSerializer,
    SuggestionUpdateAgentSerializer,
    SuggestionUpdateAdminSerializer,
    DocumentCreateSerializer,
    DocumentSerializer,
    DocumentDetailSerializer,
    DocumentChunkSerializer,
    KnowledgeBaseRetrieveSerializer,
)

from core.kb import chunk_text, normalize_text, search_kb_chunks_for_query

# -------------------------
# Simple helpers (keep them here to avoid import shadowing issues)
# -------------------------

''' 
def normalize_text(text: str) -> str:
    if text is None:
        return ""
    # normalize newlines + strip outer whitespace
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200):
    """
    Returns a list of tuples: (char_start, char_end, chunk_str)
    """
    text = text or ""
    n = len(text)
    if n == 0:
        return []

    if overlap >= chunk_size:
        overlap = max(0, chunk_size - 1)

    step = max(1, chunk_size - overlap)
    out = []

    i = 0
    while i < n:
        start = i
        end = min(n, i + chunk_size)
        chunk_str = text[start:end]
        if chunk_str.strip():  # skip pure whitespace chunks
            out.append((start, end, chunk_str))
        if end >= n:
            break
        i += step

    return out
'''

# -------------------------
# Auth / Me
# -------------------------


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        return Response(
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "first_name": u.first_name,
                "last_name": u.last_name,
            },
            status=status.HTTP_200_OK,
        )


# -------------------------
# Tickets
# -------------------------


class TicketIngestView(APIView):
    """
    POST /api/tickets/  -> create ticket from external client/webhook
    """

    permission_classes = [AllowAny]

    def post(self, request):
        inp = TicketCreateSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        ticket = inp.save()
        return Response(TicketSerializer(ticket).data, status=status.HTTP_201_CREATED)


class TicketDetailView(APIView):
    permission_classes = [IsAuthenticated, TicketRolePermission]

    def get(self, request, pk: int):
        org_ids = user_org_ids(request.user)
        ticket = get_object_or_404(Ticket, pk=pk, organization_id__in=org_ids)
        self.check_object_permissions(request, ticket)
        return Response(TicketSerializer(ticket).data, status=status.HTTP_200_OK)

    def patch(self, request, pk: int):
        org_ids = user_org_ids(request.user)
        ticket = get_object_or_404(Ticket, pk=pk, organization_id__in=org_ids)
        self.check_object_permissions(request, ticket)

        actor = (request.headers.get("X-Actor-Type") or "").strip().lower()
        if actor == "":
            ticket._event_actor_type = TicketEvent.ActorType.SYSTEM
        elif actor == "webhook":
            ticket._event_actor_type = TicketEvent.ActorType.WEBHOOK
        elif actor == "system":
            ticket._event_actor_type = TicketEvent.ActorType.SYSTEM
        else:
            raise ValidationError({"X-Actor-Type": "Must be 'webhook' or 'system'."})

        inp = TicketUpdateSerializer(ticket, data=request.data, partial=True)
        inp.is_valid(raise_exception=True)
        updated_ticket = inp.save()

        return Response(
            TicketSerializer(updated_ticket).data, status=status.HTTP_200_OK
        )


class OrganizationTicketListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TicketSerializer
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = TicketFilter
    ordering_fields = ["id", "created_at", "updated_at", "priority", "status"]
    ordering = ["-id"]

    def get_queryset(self):
        org_id = self.kwargs["org_id"]
        role = user_role_in_org(self.request.user, org_id)
        if role is None:
            raise NotFound("Not found.")
        return Ticket.objects.filter(organization_id=org_id).order_by("-id")


class TicketEventListView(ListAPIView):
    permission_classes = [IsAuthenticated, TicketRolePermission]
    serializer_class = TicketEventSerializer
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = TicketEventFilter
    ordering_fields = ["id", "created_at", "event_type", "actor_type"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        org_ids = user_org_ids(self.request.user)
        ticket = get_object_or_404(
            Ticket, pk=self.kwargs["pk"], organization_id__in=org_ids
        )
        self.check_object_permissions(self.request, ticket)
        return TicketEvent.objects.filter(ticket=ticket)


class TicketTriggerTriageView(APIView):
    permission_classes = [IsAuthenticated, TicketRolePermission]

    def post(self, request, pk: int):
        org_ids = user_org_ids(request.user)
        ticket = get_object_or_404(Ticket, pk=pk, organization_id__in=org_ids)
        self.check_object_permissions(request, ticket)

        idem_key = (request.headers.get("Idempotency-Key") or "").strip()
        if not idem_key:
            raise ValidationError({"Idempotency-Key": "This header is required."})
        if len(idem_key) > 80:
            raise ValidationError({"Idempotency-Key": "Max length is 80 characters."})

        try:
            with transaction.atomic():
                job, created = JobRun.objects.select_for_update().get_or_create(
                    organization=ticket.organization,
                    ticket=ticket,
                    idempotency_key=idem_key,
                    defaults={
                        "status": JobRun.Status.QUEUED,
                        "triggered_by": request.user,
                    },
                )
        except IntegrityError:
            with transaction.atomic():
                job = JobRun.objects.select_for_update().get(
                    organization=ticket.organization,
                    ticket=ticket,
                    idempotency_key=idem_key,
                )
            created = False

        should_enqueue = created or (
            job.status == JobRun.Status.QUEUED and job.started_at is None
        )
        if should_enqueue:
            run_ticket_triage.delay(job.id)

        payload = {
            "job_run_id": job.id,
            "status": job.status,
            "created": created,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "error": job.error,
        }

        return Response(
            payload, status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK
        )


# -------------------------
# Suggestions
# -------------------------


class SuggestionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    lookup_url_kwarg = "sid"

    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["id", "created_at"]
    ordering = ["-created_at", "-id"]

    def _require_membership_or_404(self, request, org_id: int):
        if not Membership.objects.filter(
            user=request.user, organization_id=org_id
        ).exists():
            raise NotFound()

    def get_queryset(self):
        org_id = int(self.kwargs["org_id"])
        ticket_id = int(self.kwargs["ticket_id"])
        return (
            Suggestion.objects.select_related("job_run", "ticket", "organization")
            .filter(organization_id=org_id, ticket_id=ticket_id)
            .order_by("-created_at", "-id")
        )

    def get_serializer_class(self):
        if self.action in ("partial_update", "update"):
            org_id = int(self.kwargs["org_id"])
            role = user_role_in_org(self.request.user, org_id)
            if role == "admin":
                return SuggestionUpdateAdminSerializer
            return SuggestionUpdateAgentSerializer
        return SuggestionSerializer

    def list(self, request, *args, **kwargs):
        self._require_membership_or_404(request, int(kwargs["org_id"]))
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        self._require_membership_or_404(request, int(kwargs["org_id"]))
        return super().retrieve(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        org_id = int(kwargs["org_id"])
        self._require_membership_or_404(request, org_id)

        role = user_role_in_org(request.user, org_id)
        if role not in ("admin", "agent"):
            raise PermissionDenied("Only admin/agent can edit suggestions.")

        return super().partial_update(request, *args, **kwargs)

    def perform_update(self, serializer):
        suggestion = self.get_object()

        before = {
            "status": suggestion.status,
            "draft_reply": suggestion.draft_reply,
            "suggested_team": suggestion.suggested_team,
            "suggested_priority": suggestion.suggested_priority,
            "metadata": suggestion.metadata,
        }

        updated = serializer.save()

        after = {
            "status": updated.status,
            "draft_reply": updated.draft_reply,
            "suggested_team": updated.suggested_team,
            "suggested_priority": updated.suggested_priority,
            "metadata": updated.metadata,
        }

        changes = {}
        for k in before:
            if before[k] != after[k]:
                changes[k] = {"from": before[k], "to": after[k]}

        if changes:
            TicketEvent.objects.create(
                organization=updated.organization,
                ticket=updated.ticket,
                event_type=TicketEvent.EventType.COMMENT_ADDED,
                actor_type=TicketEvent.ActorType.USER,
                actor_user=self.request.user,
                payload={
                    "suggestion_id": updated.id,
                    "changes": changes,
                },
            )


class SuggestionApproveView(APIView):
    """
    POST /api/organizations/<org_id>/tickets/<ticket_id>/suggestions/<sid>/approve/
    Marks a suggestion as approved and logs a TicketEvent.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, org_id: int, ticket_id: int, sid: int):
        # must belong to org
        if not Membership.objects.filter(
            user=request.user, organization_id=org_id
        ).exists():
            raise NotFound()

        role = user_role_in_org(request.user, org_id)
        if role not in ("admin", "agent"):
            raise PermissionDenied("Only admin/agent can approve suggestions.")

        suggestion = get_object_or_404(
            Suggestion,
            id=sid,
            organization_id=org_id,
            ticket_id=ticket_id,
        )

        old_status = suggestion.status
        if old_status == Suggestion.Status.APPROVED:
            # idempotent: approving again is OK
            return Response(
                {"detail": "Suggestion already approved.", "status": suggestion.status},
                status=status.HTTP_200_OK,
            )

        suggestion.status = Suggestion.Status.APPROVED
        suggestion.save(update_fields=["status"])

        TicketEvent.objects.create(
            organization=suggestion.organization,
            ticket=suggestion.ticket,
            event_type=TicketEvent.EventType.SUGGESTION_APPROVED,
            actor_type=TicketEvent.ActorType.USER,
            actor_user=request.user,
            payload={
                "suggestion_id": suggestion.id,
                "from_status": old_status,
                "to_status": suggestion.status,
            },
        )

        return Response(
            {
                "id": suggestion.id,
                "status": suggestion.status,
            },
            status=status.HTTP_200_OK,
        )


class SuggestionRejectView(APIView):
    """
    POST /api/organizations/<org_id>/tickets/<ticket_id>/suggestions/<sid>/reject/
    Marks a suggestion as rejected and logs a TicketEvent.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, org_id: int, ticket_id: int, sid: int):
        if not Membership.objects.filter(
            user=request.user, organization_id=org_id
        ).exists():
            raise NotFound()

        role = user_role_in_org(request.user, org_id)
        if role not in ("admin", "agent"):
            raise PermissionDenied("Only admin/agent can reject suggestions.")

        suggestion = get_object_or_404(
            Suggestion,
            id=sid,
            organization_id=org_id,
            ticket_id=ticket_id,
        )

        old_status = suggestion.status
        if old_status == Suggestion.Status.REJECTED:
            return Response(
                {"detail": "Suggestion already rejected.", "status": suggestion.status},
                status=status.HTTP_200_OK,
            )

        suggestion.status = Suggestion.Status.REJECTED
        suggestion.save(update_fields=["status"])

        TicketEvent.objects.create(
            organization=suggestion.organization,
            ticket=suggestion.ticket,
            event_type=TicketEvent.EventType.SUGGESTION_REJECTED,
            actor_type=TicketEvent.ActorType.USER,
            actor_user=request.user,
            payload={
                "suggestion_id": suggestion.id,
                "from_status": old_status,
                "to_status": suggestion.status,
            },
        )

        return Response(
            {
                "id": suggestion.id,
                "status": suggestion.status,
            },
            status=status.HTTP_200_OK,
        )


# -------------------------
# Documents (PR8)
# -------------------------


class DocumentViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    lookup_url_kwarg = "doc_id"

    filter_backends = [OrderingFilter]
    ordering_fields = ["id", "created_at"]
    ordering = ["-id"]

    def _require_membership_or_404(self, request, org_id: int):
        if not Membership.objects.filter(
            user=request.user, organization_id=org_id
        ).exists():
            raise NotFound()

    def _require_admin_or_agent(self, request, org_id: int):
        role = user_role_in_org(request.user, org_id)
        if role not in ("admin", "agent"):
            raise PermissionDenied("Only admin/agent can upload documents.")

    def get_queryset(self):
        org_id = int(self.kwargs["org_id"])
        return (
            Document.objects.select_related("uploaded_by", "organization")
            .filter(organization_id=org_id)
            .annotate(chunk_count=Count("chunks"))
            .order_by("-id")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return DocumentCreateSerializer
        if self.action == "retrieve":
            return DocumentDetailSerializer
        return DocumentSerializer

    def list(self, request, *args, **kwargs):
        self._require_membership_or_404(request, int(kwargs["org_id"]))
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        self._require_membership_or_404(request, int(kwargs["org_id"]))
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        org_id = int(kwargs["org_id"])
        self._require_membership_or_404(request, org_id)
        self._require_admin_or_agent(request, org_id)

        inp = DocumentCreateSerializer(data=request.data)
        inp.is_valid(raise_exception=True)

        title = (inp.validated_data["title"] or "").strip()
        text = normalize_text(inp.validated_data.get("text", ""))
        metadata = inp.validated_data.get("metadata", {}) or {}

        if not title:
            raise ValidationError({"title": "Title cannot be empty."})
        if not text:
            raise ValidationError({"text": "Text cannot be empty."})

        pieces = chunk_text(text, chunk_size=1200, overlap=200)
        if not pieces:
            raise ValidationError({"text": "Could not chunk text."})

        org = get_object_or_404(Organization, id=org_id)

        with transaction.atomic():
            doc = Document.objects.create(
                organization=org,
                title=title,
                text=text,
                metadata=metadata,
                uploaded_by=request.user,
            )

            chunks = [
                DocumentChunk(
                    organization=org,
                    document=doc,
                    chunk_index=i,
                    text=chunk_str,
                    char_start=s,
                    char_end=e,
                )
                for i, (s, e, chunk_str) in enumerate(pieces)
            ]
            DocumentChunk.objects.bulk_create(chunks)
            embed_document_chunks.delay(doc.id)

        # Return the created document (includes chunk_count via relation)
        return Response(DocumentSerializer(doc).data, status=status.HTTP_201_CREATED)


class DocumentChunkViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination

    filter_backends = [OrderingFilter]
    ordering_fields = ["chunk_index", "id", "created_at"]
    ordering = ["chunk_index", "id"]

    def _require_membership_or_404(self, request, org_id: int):
        if not Membership.objects.filter(
            user=request.user, organization_id=org_id
        ).exists():
            raise NotFound()

    def get_queryset(self):
        org_id = int(self.kwargs["org_id"])
        doc_id = int(self.kwargs["doc_id"])
        return DocumentChunk.objects.filter(
            organization_id=org_id, document_id=doc_id
        ).order_by("chunk_index")

    def list(self, request, *args, **kwargs):
        self._require_membership_or_404(request, int(kwargs["org_id"]))
        return super().list(request, *args, **kwargs)

    def get_serializer_class(self):
        return DocumentChunkSerializer


class KnowledgeBaseRetrieveView(APIView):
    """
    POST /api/organizations/<org_id>/kb/retrieve/

    Body:
      { "query": "...", "k": 5 }
      OR
      { "ticket_id": 13, "k": 5 }

    Returns top-k KB chunks for that org.
    """

    permission_classes = [IsAuthenticated]

    def _require_membership_or_404(self, request, org_id: int):
        if not Membership.objects.filter(
            user=request.user, organization_id=org_id
        ).exists():
            raise NotFound()

    def post(self, request, org_id: int):
        self._require_membership_or_404(request, org_id)

        ser = KnowledgeBaseRetrieveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        query = (data.get("query") or "").strip()
        ticket_id = data.get("ticket_id")
        k = data.get("k", 5)

        if ticket_id and not query:
            # Use ticket subject + body as the query text
            ticket = get_object_or_404(Ticket, id=ticket_id, organization_id=org_id)
            query = f"{ticket.subject}\n\n{ticket.body}"

        results = search_kb_chunks_for_query(
            org_id=org_id,
            query=query,
            k=k,
        )

        return Response({"results": results}, status=status.HTTP_200_OK)
