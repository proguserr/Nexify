# core/api/filters.py
import django_filters
from django.db.models import Q

from core.models import Ticket, TicketEvent


class TicketFilter(django_filters.FilterSet):
    """
    Filters for listing tickets in an organization.

    Supported query params (examples):

    - ?status=open
    - ?priority=high
    - ?assigned_team=Billing
    - ?created_from=2025-01-01T00:00:00Z
    - ?created_to=2025-01-31T23:59:59Z
    - ?q=refund   (search subject/body/email)
    """

    created_from = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )
    created_to = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="lte"
    )
    q = django_filters.CharFilter(method="filter_q")

    class Meta:
        model = Ticket
        fields = [
            "status",
            "priority",
            "assigned_team",
            "created_from",
            "created_to",
        ]

    def filter_q(self, queryset, name, value):
        value = (value or "").strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(subject__icontains=value)
            | Q(body__icontains=value)
            | Q(requester_email__icontains=value)
        )


class TicketEventFilter(django_filters.FilterSet):
    """
    Filters for listing events for a ticket.

    Supported query params:

    - ?event_type=status_changed
    - ?actor_type=user
    - ?created_from=...
    - ?created_to=...
    """

    created_from = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )
    created_to = django_filters.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="lte"
    )

    class Meta:
        model = TicketEvent
        fields = [
            "event_type",
            "actor_type",
            "created_from",
            "created_to",
        ]
