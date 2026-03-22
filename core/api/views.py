# core/api/views.py
from django.db import transaction, IntegrityError
from django.db.models import Avg, Count
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

        # Create / reuse JobRun under lock
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

        # For demo/local dev: run triage synchronously so UI gets the suggestion immediately
        suggestion_id = run_ticket_triage(job.id)

        suggestion = None
        if suggestion_id is not None:
            try:
                suggestion = Suggestion.objects.select_related(
                    "ticket", "organization", "job_run"
                ).get(id=suggestion_id)
            except Suggestion.DoesNotExist:
                suggestion = None

        payload = {
            "job_run_id": job.id,
            "status": job.status,
            "created": created,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "error": job.error,
            "suggestion": SuggestionSerializer(suggestion).data if suggestion else None,
        }

        return Response(payload, status=status.HTTP_200_OK)


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


class DashboardView(APIView):
    """
    GET /api/organizations/<org_id>/dashboard/

    Aggregated metrics for the organization (members only).

    Optional query: ?detail=triaged|reviewed|confidence
    — returns the same summary metrics plus detail payload for drill-down.
    """

    permission_classes = [IsAuthenticated]

    def _build_dashboard_summary(self, org_id: int) -> dict:
        total_triaged = JobRun.objects.filter(
            organization_id=org_id,
            status=JobRun.Status.SUCCEEDED,
        ).count()

        auto_resolved = TicketEvent.objects.filter(
            organization_id=org_id,
            event_type=TicketEvent.EventType.AUTO_RESOLUTION_APPLIED,
        ).count()

        human_reviewed = Suggestion.objects.filter(
            organization_id=org_id,
            status__in=[
                Suggestion.Status.ACCEPTED,
                Suggestion.Status.REJECTED,
            ],
        ).count()

        avg_row = Suggestion.objects.filter(organization_id=org_id).aggregate(
            avg=Avg("confidence")
        )
        avg_raw = avg_row["avg"]
        average_confidence = (
            0.0 if avg_raw is None else round(float(avg_raw), 2)
        )

        accepted_count = Suggestion.objects.filter(
            organization_id=org_id,
            status=Suggestion.Status.ACCEPTED,
        ).count()
        reviewed_count = Suggestion.objects.filter(
            organization_id=org_id,
            status__in=[
                Suggestion.Status.ACCEPTED,
                Suggestion.Status.REJECTED,
            ],
        ).count()
        if reviewed_count == 0:
            acceptance_rate = 0.0
        else:
            acceptance_rate = round(
                100.0 * accepted_count / reviewed_count, 1
            )

        time_saved_minutes = total_triaged * 4

        return {
            "total_triaged": total_triaged,
            "auto_resolved": auto_resolved,
            "human_reviewed": human_reviewed,
            "average_confidence": average_confidence,
            "acceptance_rate": acceptance_rate,
            "time_saved_minutes": time_saved_minutes,
        }

    def _triaged_items(self, org_id: int) -> list[dict]:
        jobs = (
            JobRun.objects.filter(
                organization_id=org_id,
                status=JobRun.Status.SUCCEEDED,
            )
            .select_related("ticket")
            .order_by("-finished_at", "-id")
        )
        out: list[dict] = []
        for job in jobs:
            try:
                sug = job.suggestion
            except Suggestion.DoesNotExist:
                continue
            t = job.ticket
            triage_at = job.finished_at or job.started_at
            out.append(
                {
                    "ticket_id": t.id,
                    "subject": t.subject,
                    "requester_email": t.requester_email,
                    "triage_at": triage_at.isoformat() if triage_at else None,
                    "confidence": sug.confidence,
                    "suggested_team": sug.suggested_team or "",
                    "ticket_status": t.status,
                }
            )
        return out

    def _reviewed_items(self, org_id: int) -> list[dict]:
        suggestions = list(
            Suggestion.objects.filter(
                organization_id=org_id,
                status__in=[
                    Suggestion.Status.ACCEPTED,
                    Suggestion.Status.REJECTED,
                ],
            )
            .select_related("ticket")
            .order_by("-id")
        )
        if not suggestions:
            return []

        suggestion_ids = [s.id for s in suggestions]
        status_by_sid = {s.id: s.status for s in suggestions}

        # Single query for all review events; map latest event per suggestion id (match status).
        events = (
            TicketEvent.objects.filter(
                organization_id=org_id,
                event_type__in=[
                    TicketEvent.EventType.SUGGESTION_APPROVED,
                    TicketEvent.EventType.SUGGESTION_REJECTED,
                ],
                payload__suggestion_id__in=suggestion_ids,
            )
            .select_related("actor_user")
            .order_by("-created_at")
        )

        ev_by_suggestion: dict[int, TicketEvent] = {}
        for ev in events:
            raw_sid = ev.payload.get("suggestion_id")
            if raw_sid is None:
                continue
            try:
                sid = int(raw_sid)
            except (TypeError, ValueError):
                continue
            if sid not in status_by_sid:
                continue
            expected_type = (
                TicketEvent.EventType.SUGGESTION_APPROVED
                if status_by_sid[sid] == Suggestion.Status.ACCEPTED
                else TicketEvent.EventType.SUGGESTION_REJECTED
            )
            if ev.event_type != expected_type:
                continue
            if sid not in ev_by_suggestion:
                ev_by_suggestion[sid] = ev

        out: list[dict] = []
        for s in suggestions:
            ev = ev_by_suggestion.get(s.id)
            reviewed_at = ev.created_at.isoformat() if ev else None
            reviewer = None
            if ev and ev.actor_user:
                reviewer = ev.actor_user.get_username()
            out.append(
                {
                    "ticket_id": s.ticket_id,
                    "subject": s.ticket.subject,
                    "suggestion_status": s.status,
                    "reviewed_at": reviewed_at,
                    "reviewer_username": reviewer,
                }
            )
        return out

    def _confidence_distribution(self, org_id: int) -> dict:
        base = Suggestion.objects.filter(organization_id=org_id)
        high = base.filter(
            confidence__isnull=False,
            confidence__gte=0.8,
            confidence__lte=1.0,
        ).count()
        medium = base.filter(
            confidence__isnull=False,
            confidence__gte=0.6,
            confidence__lt=0.8,
        ).count()
        low = base.filter(
            confidence__isnull=False,
            confidence__lt=0.6,
        ).count()
        unknown = base.filter(confidence__isnull=True).count()
        total_banded = high + medium + low
        if total_banded == 0:
            high_pct = medium_pct = low_pct = 0.0
        else:
            high_pct = round(100.0 * high / total_banded, 1)
            medium_pct = round(100.0 * medium / total_banded, 1)
            low_pct = round(100.0 * low / total_banded, 1)
        return {
            "high": high,
            "medium": medium,
            "low": low,
            "unknown": unknown,
            "high_pct": high_pct,
            "medium_pct": medium_pct,
            "low_pct": low_pct,
            "total_with_confidence": total_banded,
        }

    def get(self, request, org_id: int):
        if org_id not in user_org_ids(request.user):
            raise NotFound()

        data = self._build_dashboard_summary(org_id)
        detail = (request.query_params.get("detail") or "").strip().lower()
        if detail == "triaged":
            data["triaged_items"] = self._triaged_items(org_id)
        elif detail == "reviewed":
            data["reviewed_items"] = self._reviewed_items(org_id)
        elif detail == "confidence":
            data["confidence_distribution"] = self._confidence_distribution(org_id)

        return Response(data, status=status.HTTP_200_OK)


class SuggestionApproveView(APIView):
    """
    POST /api/organizations/<org_id>/tickets/<ticket_id>/suggestions/<sid>/approve/

    Marks a suggestion as accepted, applies suggested fields to the ticket,
    and logs a TicketEvent.
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

        ticket = suggestion.ticket

        if suggestion.status == Suggestion.Status.ACCEPTED:
            # idempotent: approving again is OK
            return Response(
                SuggestionSerializer(suggestion).data,
                status=status.HTTP_200_OK,
            )

        old_status = suggestion.status
        suggestion.status = Suggestion.Status.ACCEPTED
        suggestion.save(update_fields=["status"])

        # Apply suggested changes to the ticket where present
        updated_fields = []

        if suggestion.suggested_priority and (
            suggestion.suggested_priority != ticket.priority
        ):
            ticket.priority = suggestion.suggested_priority
            updated_fields.append("priority")

        if suggestion.suggested_team and (
            suggestion.suggested_team != ticket.assigned_team
        ):
            ticket.assigned_team = suggestion.suggested_team
            updated_fields.append("assigned_team")

        if updated_fields:
            ticket.save(update_fields=updated_fields)

        TicketEvent.objects.create(
            organization=suggestion.organization,
            ticket=ticket,
            job_run=suggestion.job_run,
            event_type=TicketEvent.EventType.SUGGESTION_APPROVED,
            actor_type=TicketEvent.ActorType.USER,
            actor_user=request.user,
            payload={
                "suggestion_id": suggestion.id,
                "from_status": old_status,
                "to_status": suggestion.status,
                "applied_fields": updated_fields,
            },
        )

        return Response(
            SuggestionSerializer(suggestion).data,
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

        if suggestion.status == Suggestion.Status.REJECTED:
            return Response(
                SuggestionSerializer(suggestion).data,
                status=status.HTTP_200_OK,
            )

        old_status = suggestion.status
        suggestion.status = Suggestion.Status.REJECTED
        suggestion.save(update_fields=["status"])

        TicketEvent.objects.create(
            organization=suggestion.organization,
            ticket=suggestion.ticket,
            job_run=suggestion.job_run,
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
            SuggestionSerializer(suggestion).data,
            status=status.HTTP_200_OK,
        )
