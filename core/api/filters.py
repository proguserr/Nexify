import django_filters
from core.models import Ticket, TicketEvent


class TicketFilter(django_filters.FilterSet):
    created_from = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_to = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr = "lte")

    class Meta:
        model = Ticket
        fields = ["status", "priority", "assigned_team"]


class TicketEventFilter(django_filters.FilterSet):
    created_from = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_to = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    event_type = django_filters.CharFilter(field_name="event_type", lookup_expr="exact")
    actor_type = django_filters.CharFilter(field_name="actor_type", lookup_expr="exact")

    class Meta:
        model = TicketEvent
        fields = ["event_type", "actor_type"]

