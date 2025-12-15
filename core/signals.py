# core/signals.py
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from core.models import Ticket, TicketEvent


@receiver(pre_save, sender=Ticket)
def ticket_pre_save(sender, instance: Ticket, **kwargs):
    if not instance.pk:
        instance._old = None
        return
    try:
        instance._old = Ticket.objects.get(pk=instance.pk)
    except Ticket.DoesNotExist:
        instance._old = None


@receiver(post_save, sender=Ticket)
def ticket_post_save(sender, instance: Ticket, created: bool, **kwargs):
    if created:
        if getattr(instance, "_skip_created_event", False):
            return

        TicketEvent.objects.create(
            organization=instance.organization,
            ticket=instance,
            event_type=TicketEvent.EventType.CREATED,
            actor_type=getattr(
                instance, "_event_actor_type", TicketEvent.ActorType.SYSTEM
            ),
            payload={
                "status": instance.status,
                "priority": instance.priority,
                "assigned_team": instance.assigned_team,
            },
        )
        return

    old = getattr(instance, "_old", None)
    if not old:
        return

    actor_type = getattr(instance, "_event_actor_type", TicketEvent.ActorType.SYSTEM)

    def log(event_type: str, payload: dict):
        TicketEvent.objects.create(
            organization=instance.organization,
            ticket=instance,
            event_type=event_type,
            actor_type=actor_type,
            payload=payload,
        )

    if old.status != instance.status:
        log(
            TicketEvent.EventType.STATUS_CHANGED,
            {"from": old.status, "to": instance.status},
        )

    if old.priority != instance.priority:
        log(
            TicketEvent.EventType.PRIORITY_CHANGED,
            {"from": old.priority, "to": instance.priority},
        )

    if old.assigned_team != instance.assigned_team:
        log(
            TicketEvent.EventType.ASSIGNED_TEAM_CHANGED,
            {"from": old.assigned_team, "to": instance.assigned_team},
        )
