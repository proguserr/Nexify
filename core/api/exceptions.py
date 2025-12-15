# core/api/exceptions.py
import logging
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    # Let DRF handle known exceptions (401/403/404/validation errors, etc.)
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response

    logger.error(
        "Unhandled exception in API",
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={
            "view": getattr(
                context.get("view"), "__class__", type("x", (), {})
            ).__name__,
            "request_path": getattr(context.get("request"), "path", None),
            "request_method": getattr(context.get("request"), "method", None),
        },
    )

    if settings.DEBUG:
        return Response(
            {
                "detail": "Internal server error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {"detail": "Internal server error"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
