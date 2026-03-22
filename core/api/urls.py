from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    TicketIngestView,
    TicketDetailView,
    OrganizationTicketListView,
    TicketEventListView,
    MeView,
    TicketTriggerTriageView,
    SuggestionViewSet,
    SuggestionApproveView,
    SuggestionRejectView,
    DocumentViewSet,
    DocumentChunkViewSet,
    KnowledgeBaseRetrieveView,
    DashboardView,
)

# Suggestions
suggestion_list = SuggestionViewSet.as_view(
    {
        "get": "list",
    }
)
suggestion_detail = SuggestionViewSet.as_view(
    {
        "get": "retrieve",
        "patch": "partial_update",
    }
)

# Documents
document_list = DocumentViewSet.as_view(
    {
        "get": "list",  # list documents
        "post": "create",  # upload + chunk + embed
    }
)
document_detail = DocumentViewSet.as_view(
    {
        "get": "retrieve",
    }
)

# Document chunks
document_chunks = DocumentChunkViewSet.as_view(
    {
        "get": "list",
    }
)


urlpatterns = [
    # Tickets
    path("tickets/", TicketIngestView.as_view(), name="ticket-ingest"),
    path("tickets/<int:pk>/", TicketDetailView.as_view(), name="ticket-detail"),
    path(
        "tickets/<int:pk>/events/",
        TicketEventListView.as_view(),
        name="ticket-events",
    ),
    path(
        "organizations/<int:org_id>/tickets/",
        OrganizationTicketListView.as_view(),
        name="org-ticket-list",
    ),
    path(
        "organizations/<int:org_id>/dashboard/",
        DashboardView.as_view(),
        name="org-dashboard",
    ),
    # Auth
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Me
    path("me/", MeView.as_view(), name="me"),
    # Triage
    path(
        "tickets/<int:pk>/trigger-triage/",
        TicketTriggerTriageView.as_view(),
        name="ticket-trigger-triage",
    ),
    # Suggestions CRUD
    path(
        "organizations/<int:org_id>/tickets/<int:ticket_id>/suggestions/",
        suggestion_list,
        name="ticket-suggestion-list",
    ),
    path(
        "organizations/<int:org_id>/tickets/<int:ticket_id>/suggestions/<int:sid>/",
        suggestion_detail,
        name="ticket-suggestion-detail",
    ),
    path(
        "organizations/<int:org_id>/tickets/<int:ticket_id>/suggestions/<int:sid>/approve/",
        SuggestionApproveView.as_view(),
        name="ticket-suggestion-approve",
    ),
    path(
        "organizations/<int:org_id>/tickets/<int:ticket_id>/suggestions/<int:sid>/reject/",
        SuggestionRejectView.as_view(),
        name="ticket-suggestion-reject",
    ),
    # Knowledge base documents (PR8–10)
    path(
        "organizations/<int:org_id>/documents/",
        document_list,
        name="org-document-list",
    ),
    path(
        "organizations/<int:org_id>/documents/<int:doc_id>/",
        document_detail,
        name="org-document-detail",
    ),
    path(
        "organizations/<int:org_id>/documents/<int:doc_id>/chunks/",
        document_chunks,
        name="org-document-chunks",
    ),
    # KB retrieval (PR11)
    path(
        "organizations/<int:org_id>/kb/retrieve/",
        KnowledgeBaseRetrieveView.as_view(),
        name="kb-retrieve",
    ),
]
