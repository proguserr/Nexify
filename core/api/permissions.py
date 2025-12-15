from rest_framework.permissions import BasePermission, SAFE_METHODS
from core.models import Membership


class TicketRolePermission(BasePermission):
    """
    Allows:
      - Any org member to READ (GET/HEAD/OPTIONS)
      - Only agent/admin to WRITE (PATCH/PUT/DELETE)
    """

    message = "You do not have permission to modify tickets in this organization."

    def has_object_permission(self, request, view, obj):
        m = (
            Membership.objects.filter(user=request.user, organization=obj.organization)
            .only("role")
            .first()
        )

        if not m:
            return False

        if request.method in SAFE_METHODS:
            return True

        return m.role in ("admin", "agent")
