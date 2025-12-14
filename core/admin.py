from django.contrib import admin
from .models import (
    Organization,
    Membership,
    Ticket,
    TicketEvent,
    JobRun,
    Suggestion,
)

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "created_at")
    search_fields = ("name",)
    ordering = ("-created_at",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "user", "role", "created_at")
    list_filter = ("role", "organization")
    search_fields = ("organization__name", "user__username", "user__email")
    ordering = ("-created_at",)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "subject", "status", "priority", "assigned_team", "created_at")
    list_filter = ("organization", "status", "priority", "assigned_team")
    search_fields = ("subject", "requester_email", "organization__name")
    ordering = ("-created_at",)


@admin.register(TicketEvent)
class TicketEventAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "ticket", "event_type", "actor_type", "actor_user", "created_at")
    list_filter = ("organization", "event_type", "actor_type")
    search_fields = ("ticket__subject", "organization__name", "actor_user__username")
    ordering = ("-created_at",)


@admin.register(JobRun)
class JobRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "organization",
        "ticket",
        "status",
        "idempotency_key",
        "triggered_by",
        "started_at",
        "finished_at",
        "created_at",
    )
    list_filter = ("organization", "status")
    search_fields = ("idempotency_key", "ticket__subject", "triggered_by__username", "organization__name")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)


@admin.register(Suggestion)
class SuggestionAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "ticket", "job_run", "suggested_team", "suggested_priority", "created_at")
    list_filter = ("organization", "suggested_team", "suggested_priority")
    search_fields = ("ticket__subject", "organization__name", "draft_reply")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)