"""Optional local-only task selection. Never calls a remote endpoint."""
from __future__ import annotations

import json
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import URLError

from .catalog import CATALOG, BY_ID

# Hard-coded loopback interface. No URL parameter: prevents remote inference.
LOCAL_URL = "http://127.0.0.1:11434/api/generate"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LocalPlannerError("Local Ollama endpoint attempted a redirect; refusing to follow it")


class LocalPlannerError(RuntimeError):
    pass


def select_with_ollama(context: str, model: str = "qwen2.5:7b") -> tuple[list[str], list[str]]:
    """Return proposed capability IDs and notes; Python validates the response."""
    ids = [item.id for item in CATALOG]
    schema = {
        "type": "object",
        "properties": {
            "capabilities": {"type": "array", "items": {"type": "string", "enum": ids}},
            "notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["capabilities", "notes"],
        "additionalProperties": False,
    }
    prompt = (
        "You plan LOCAL documentation workflows. Read the project context. "
        "Select only capabilities needed for these objectives; choose from this catalog: "
        + ", ".join(f"{c.id}: {c.description}" for c in CATALOG)
        + ". Return JSON with capabilities (list of IDs) and notes (list of possible uncertainties). "
        "Do not execute tasks, invent source facts, or add capabilities outside the catalog. "
        "Security, human approval and local-only execution are enforced separately.\n\n"
        "PROJECT CONTEXT:\n" + context
    )
    payload = {
        "model": model,
        "prompt": prompt,
        "format": schema,
        "stream": False,
        "options": {"temperature": 0},
    }
    request = Request(
        LOCAL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=120) as response:
            envelope = json.load(response)
        candidate = json.loads(envelope["response"])
    except (URLError, OSError, ValueError, KeyError, TypeError) as error:
        raise LocalPlannerError(
            "Local Ollama planning failed. Check `ollama serve` and that the model is installed. "
            f"Details: {error}"
        ) from error

    caps = candidate.get("capabilities", [])
    notes = candidate.get("notes", [])
    if not isinstance(caps, list) or not caps or any(not isinstance(c, str) or c not in BY_ID for c in caps):
        raise LocalPlannerError("Ollama returned invalid capability identifiers")
    if not isinstance(notes, list) or any(not isinstance(n, str) for n in notes):
        raise LocalPlannerError("Ollama returned invalid notes")
    return list(dict.fromkeys(caps)), notes
