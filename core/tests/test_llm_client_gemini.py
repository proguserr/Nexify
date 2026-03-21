import json
import os
from unittest.mock import patch

import pytest

from core.llm_client import classify_ticket_with_llm, LLMError
from core.models import Organization, Ticket


@pytest.mark.django_db
def test_classify_ticket_with_llm_gemini_path_normalizes_output():
    org = Organization.objects.create(name="Org LLM")
    ticket = Ticket.objects.create(
        organization=org,
        requester_email="a@b.com",
        subject="Invoice missing",
        body="Where is my invoice?",
        priority=Ticket.Priority.MEDIUM,
        status=Ticket.Status.OPEN,
    )

    fake_json = json.dumps(
        {
            "category": "billing",
            "team": "billing",
            "priority": "HIGH",
            "draft_reply": "We will send your invoice.",
            "classification": "billing_invoice",
            "confidence": 0.91,
            "auto_resolve": False,
        }
    )

    with patch.dict(os.environ, {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"}):
        with patch("core.llm_client._gemini_generate_json", return_value=fake_json):
            out = classify_ticket_with_llm(ticket, [])

    assert out["category"] == "billing"
    assert out["team"] == "billing"
    assert out["priority"] == "high"
    assert out["classification"] == "billing_invoice"
    assert out["confidence"] == pytest.approx(0.91)
    assert out["auto_resolve"] is False
    assert "invoice" in out["draft_reply"].lower()
    assert out["raw_output"] == fake_json


@pytest.mark.django_db
def test_classify_ticket_gemini_missing_key_raises():
    org = Organization.objects.create(name="Org2")
    ticket = Ticket.objects.create(
        organization=org,
        requester_email="a@b.com",
        subject="x",
        body="y",
    )

    with patch.dict(
        os.environ,
        {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": ""},
    ):
        with pytest.raises(LLMError, match="GEMINI_API_KEY"):
            classify_ticket_with_llm(ticket, [])


@pytest.mark.django_db
@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="Set GEMINI_API_KEY for live Gemini smoke test",
)
@pytest.mark.skipif(
    os.getenv("RUN_GEMINI_LIVE") != "1",
    reason="Set RUN_GEMINI_LIVE=1 to call the real Gemini API (optional; avoids quota in CI)",
)
def test_classify_ticket_gemini_live_smoke():
    org = Organization.objects.create(name="Org Live")
    ticket = Ticket.objects.create(
        organization=org,
        requester_email="a@b.com",
        subject="Password reset",
        body="I cannot log in.",
        priority=Ticket.Priority.MEDIUM,
        status=Ticket.Status.OPEN,
    )

    with patch.dict(os.environ, {"LLM_PROVIDER": "gemini"}, clear=False):
        try:
            out = classify_ticket_with_llm(ticket, [])
        except LLMError as e:
            if "429" in str(e) or "quota" in str(e).lower():
                pytest.skip(f"Gemini quota/rate limit: {e}")
            raise

    assert out["priority"] in {"low", "medium", "high", "urgent"}
    assert out["team"]
    assert out["draft_reply"]
