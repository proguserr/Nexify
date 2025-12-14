# core/llm.py
import json
import logging
import os
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)


LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama").lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")


class LLMError(Exception):
    pass


def _call_ollama_chat(prompt: str, system_prompt: str | None = None, timeout: float = 20.0) -> str:
    """
    Call Ollama's /api/chat endpoint with a single user message (plus optional system).
    Returns the assistant content as a string.
    """
    url = f"{OLLAMA_BASE_URL}/api/chat"

    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = httpx.post(
            url,
            json={
                "model": OLLAMA_MODEL,
                "messages": messages,
                "stream": False,  # easier than streaming for now
            },
            timeout=timeout,
        )
    except Exception as e:
        logger.exception("Error calling Ollama")
        raise LLMError(f"Error calling Ollama: {e!r}") from e

    if resp.status_code != 200:
        logger.error("Ollama returned non-200: %s %s", resp.status_code, resp.text)
        raise LLMError(f"Ollama error {resp.status_code}: {resp.text}")

    data = resp.json()
    # non-streaming response has shape: { "message": { "role": "assistant", "content": "..." }, ... }
    msg = data.get("message") or {}
    content = msg.get("content")
    if not content:
        raise LLMError("Ollama response missing 'message.content'")
    return content


def _backend_name() -> str:
    return LLM_BACKEND


def generate_json(prompt: str, schema_hint: str, timeout: float = 20.0) -> Dict[str, Any]:
    """
    Ask the LLM to return STRICT JSON following the given schema hint.
    We do simple JSON parsing + key validation, no pydantic to keep deps light.
    """
    system_prompt = (
        "You are a backend service that MUST respond with STRICT JSON only. "
        "No prose, no markdown, no explanations. "
        "If you cannot comply, return an empty JSON object {}."
    )

    full_prompt = f"""
You will receive instructions and must respond with JSON only.

Schema (example shape, not actual data):

{schema_hint}

Now respond with a single JSON object that matches this shape.

User request:
{prompt}
""".strip()

    backend = _backend_name()
    if backend == "ollama":
        raw = _call_ollama_chat(full_prompt, system_prompt=system_prompt, timeout=timeout)
    else:
        # fallback "mock" backend for tests
        logger.warning("LLM_BACKEND=%s not implemented, returning mock output", backend)
        return {}

    # Try to locate JSON in the reply
    text = raw.strip()
    # crude but effective: find first '{' and last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        logger.error("LLM did not return JSON-looking text: %r", text[:200])
        raise LLMError("LLM did not return a JSON object")

    json_str = text[start : end + 1]

    try:
        obj = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM JSON: %s; text=%r", e, json_str[:200])
        raise LLMError(f"Failed to parse LLM JSON: {e}") from e

    if not isinstance(obj, dict):
        raise LLMError("LLM JSON root must be an object")

    return obj


def triage_ticket(
    subject: str,
    body: str,
    kb_snippets: List[str],
) -> Dict[str, Any]:
    """
    High-level helper for PR12: classify a ticket and draft a reply using the LLM.

    Returns dict like:
      {
        "category": str,
        "priority": "low"|"medium"|"high",
        "team": str,
        "draft_reply": str,
      }
    """
    kb_text = "\n\n-----\n".join(kb_snippets) if kb_snippets else "No KB context available."

    schema_hint = """
{
  "category": "short label like 'billing', 'technical', 'account', etc.",
  "priority": "one of: low, medium, high",
  "team": "best-fit internal team to handle (e.g., 'billing', 'support', 'engineering')",
  "draft_reply": "a short, polite email-style reply to the customer, using the KB if relevant"
}
""".strip()

    prompt = f"""
You are a support triage assistant for a SaaS product.

You receive:
- A ticket subject and body
- A list of knowledge-base snippets (internal policy docs, FAQs, etc.).

Your job:
1. Classify the ticket into a broad category (billing, technical, account, etc.).
2. Assign an appropriate priority (low, medium, high) based on urgency/impact.
3. Choose the best internal team to route this to.
4. Draft a short, clear, and polite reply to the customer using the KB when relevant.

Ticket subject:
{subject}

Ticket body:
{body}

Knowledge-base snippets:
{kb_text}
""".strip()

    obj = generate_json(prompt, schema_hint=schema_hint, timeout=25.0)

    # Defensive defaults
    category = str(obj.get("category") or "general").strip()
    priority = str(obj.get("priority") or "medium").strip().lower()
    team = str(obj.get("team") or "support").strip()
    draft_reply = str(obj.get("draft_reply") or "").strip()

    if priority not in {"low", "medium", "high"}:
        priority = "medium"

    return {
        "category": category or "general",
        "priority": priority,
        "team": team or "support",
        "draft_reply": draft_reply,
    }
