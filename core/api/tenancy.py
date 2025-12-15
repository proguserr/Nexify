from core.models import Membership


def user_org_ids(user):
    """Return a list of organization IDs the user is a member of."""
    return set(
        Membership.objects.filter(user=user).values_list("organization_id", flat=True)
    )


def user_role_in_org(user, org_id: int):
    """Return role string ('admin', 'agent', 'viewer') or None if not a member."""
    m = (
        Membership.objects.filter(user=user, organization_id=org_id)
        .only("role")
        .first()
    )
    return m.role if m else None
