# core/llm_client.py

import json
import os
import urllib.request
import urllib.error
from typing import List, Dict, Any

from core.models import Ticket


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")


class LLMError(Exception):
    """
    Generic error raised when the LLM (Ollama) call fails
    or returns an unexpected response.
    """
    pass


def _ollama_chat(messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
    """
    Call Ollama /api/chat with the given messages and return the assistant content.
    Uses only standard library HTTP client.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            obj = json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        raise LLMError(f"Ollama request failed: {e}") from e

    try:
        content = obj["message"]["content"]
    except KeyError as e:
        raise LLMError(f"Unexpected Ollama response: {obj}") from e

    return content


def _parse_json_from_text(text: str) -> Dict[str, Any]:
    """
    LLM may wrap JSON in extra text; try to extract the first {...} block
    and parse it as JSON.
    """
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        raise LLMError(f"No JSON object found in LLM output: {text!r}")
    snippet = text[first:last + 1]
    return json.loads(snippet)


def classify_ticket_with_llm(ticket: Ticket, kb_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Use Llama 3 via Ollama to:
      - classify the ticket (category/team/priority)
      - draft a reply
      - return a structured dict with normalized keys.

    Returns dict with keys:
      - category: str
      - team: str
      - priority: str  (low|medium|high|urgent)
      - draft_reply: str
      - raw_output: str (raw LLM response text)
    """
    kb_snippets = []
    for r in kb_results[:5]:
        kb_snippets.append(f"- [doc:{r['document_title']}] {r['text']}")
    kb_block = "\n".join(kb_snippets) if kb_snippets else "None found."

    system_msg = (
        "You are an AI assistant helping a support team triage customer tickets.\n"
        "You MUST respond with a single JSON object only, no explanation.\n"
        "Schema:\n"
        "{\n"
        '  \"category\": string,        # short category like \"billing\", \"technical\", \"account\"\n'
        '  \"team\": string,            # team to route to, e.g. \"billing\", \"support\", \"engineering\"\n'
        '  \"priority\": string,        # one of: \"low\", \"medium\", \"high\", \"urgent\"\n'
        '  \"draft_reply\": string      # short 2-5 sentence reply to send the customer\n'
        "}\n"
        "If you are unsure, guess reasonable defaults: "
        "category=\"general\", team=\"support\", priority=\"medium\"."
    )

    user_msg = (
        f"Ticket subject:\n{ticket.subject}\n\n"
        f"Ticket body:\n{ticket.body or ''}\n\n"
        "Relevant knowledge base snippets:\n"
        f"{kb_block}\n\n"
        "Now produce ONLY the JSON object as described in the schema."
    )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    raw = _ollama_chat(messages, temperature=0.2)
    try:
        parsed = _parse_json_from_text(raw)
    except Exception as e:
        raise LLMError(f"Failed to parse JSON from LLM output: {e}; raw={raw!r}") from e

    # Normalize keys and provide safe defaults
    return {
        "category": parsed.get("category") or "general",
        "team": parsed.get("team") or "support",
        "priority": (parsed.get("priority") or "medium").lower(),
        "draft_reply": parsed.get("draft_reply") or "",
        "raw_output": raw,
    }