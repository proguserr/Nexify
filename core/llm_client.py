import json
import os
import urllib.request
import urllib.error
from typing import List, Dict, Any

from core.models import Ticket


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


class LLMError(Exception):
    """
    Generic error raised when an LLM call fails or returns an unexpected response.
    """

    pass


def _resolve_llm_provider() -> str:
    """
    Which backend classify_ticket_with_llm uses.

    - Explicit LLM_PROVIDER=gemini|ollama wins.
    - Otherwise: if GEMINI_API_KEY is set, use gemini; else ollama.
    """
    explicit = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    if explicit in ("gemini", "ollama"):
        return explicit
    if os.getenv("GEMINI_API_KEY", "").strip():
        return "gemini"
    return "ollama"


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


def _gemini_generate_json(system_msg: str, user_msg: str) -> str:
    """
    Call Google Gemini with JSON response mode; return raw text (should be JSON).
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise LLMError("GEMINI_API_KEY is not set (required for LLM_PROVIDER=gemini)")

    try:
        import google.generativeai as genai
    except ImportError as e:
        raise LLMError("google-generativeai is not installed") from e

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        GEMINI_MODEL,
        system_instruction=system_msg,
    )

    try:
        response = model.generate_content(
            user_msg,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
    except Exception as e:
        raise LLMError(f"Gemini request failed: {e}") from e

    try:
        text = response.text
    except Exception as e:
        raise LLMError(f"Gemini response has no text: {e}; {response!r}") from e

    if not text or not text.strip():
        raise LLMError("Gemini returned empty response")

    return text.strip()


def _parse_json_from_text(text: str) -> Dict[str, Any]:
    """
    LLM may wrap JSON in extra text; try to extract the first {...} block
    and parse it as JSON.
    """
    first = text.find("{")
    last = text.rfind("}")
    if first == -1 or last == -1 or last <= first:
        raise LLMError(f"No JSON object found in LLM output: {text!r}")
    snippet = text[first : last + 1]
    return json.loads(snippet)


def _parse_llm_json(raw: str) -> Dict[str, Any]:
    """Parse model output; prefer strict JSON when response_mime_type is json."""
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return _parse_json_from_text(raw)


def _normalize_llm_dict(parsed: Dict[str, Any], raw: str) -> Dict[str, Any]:
    """Shared normalization for Ollama and Gemini outputs."""
    priority = (parsed.get("priority") or "medium").lower()
    if priority not in {"low", "medium", "high", "urgent"}:
        priority = "medium"

    classification = parsed.get("classification") or parsed.get("category") or "general"

    confidence = parsed.get("confidence", None)
    try:
        if confidence is not None:
            confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = None

    auto_resolve_raw = parsed.get("auto_resolve", False)
    auto_resolve = bool(auto_resolve_raw)

    return {
        "category": parsed.get("category") or "general",
        "team": parsed.get("team") or "support",
        "priority": priority,
        "draft_reply": parsed.get("draft_reply") or "",
        "classification": classification,
        "confidence": confidence,
        "auto_resolve": auto_resolve,
        "raw_output": raw,
    }


def _build_triage_prompts(
    ticket: Ticket, kb_results: List[Dict[str, Any]]
) -> tuple[str, str]:
    kb_snippets = []
    for r in kb_results[:5]:
        title = r.get("document_title") or "untitled"
        kb_snippets.append(f"- [doc:{title}] {r.get('text', '')}")
    kb_block = "\n".join(kb_snippets) if kb_snippets else "None found."

    system_msg = (
        "You are an AI assistant helping a support team triage customer tickets.\n"
        "You MUST respond with a single JSON object only, no explanation.\n"
        "Schema:\n"
        "{\n"
        '  "category": string,          # short category like "billing", "technical", "account"\n'
        '  "team": string,              # team to route to, e.g. "billing", "support", "engineering"\n'
        '  "priority": string,          # one of: "low", "medium", "high", "urgent"\n'
        '  "draft_reply": string,       # short 2-5 sentence reply to send the customer\n'
        '  "classification": string,    # OPTIONAL: finer-grained label like "billing_refund"\n'
        '  "confidence": number,        # OPTIONAL: 0.0–1.0 model confidence in the overall suggestion\n'
        '  "auto_resolve": boolean      # OPTIONAL: true if it is safe to apply this suggestion automatically\n'
        "}\n"
        "If you are unsure, guess reasonable defaults: "
        'category="general", team="support", priority="medium".\n'
        "If you are not confident enough to auto-resolve, set auto_resolve=false.\n"
        "Respond with ONLY the JSON object."
    )

    user_msg = (
        f"Ticket subject:\n{ticket.subject}\n\n"
        f"Ticket body:\n{ticket.body or ''}\n\n"
        "Relevant knowledge base snippets:\n"
        f"{kb_block}\n\n"
        "Now produce ONLY the JSON object as described in the schema."
    )

    return system_msg, user_msg


def classify_ticket_with_llm(
    ticket: Ticket, kb_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Classify a ticket and draft a reply using Gemini (default when GEMINI_API_KEY is set)
    or Ollama (LLM_PROVIDER=ollama or no Gemini key).

    Returns dict with keys:
      - category: str
      - team: str
      - priority: str  (low|medium|high|urgent)
      - draft_reply: str
      - classification: str (optional, falls back to category)
      - confidence: float | None (0.0–1.0)
      - auto_resolve: bool
      - raw_output: str (raw LLM response text)
    """
    system_msg, user_msg = _build_triage_prompts(ticket, kb_results)
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    provider = _resolve_llm_provider()
    if provider == "gemini":
        raw = _gemini_generate_json(system_msg, user_msg)
    else:
        raw = _ollama_chat(messages, temperature=0.2)

    try:
        parsed = _parse_llm_json(raw)
    except Exception as e:
        raise LLMError(f"Failed to parse JSON from LLM output: {e}; raw={raw!r}") from e

    return _normalize_llm_dict(parsed, raw)
