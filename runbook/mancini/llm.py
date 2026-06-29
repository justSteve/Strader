"""Bounded LLM extraction: Mancini newsletter -> structured JSON. [co-7lyf]

This is the one genuinely interpretive step in the Mancini pilot. It is an LLM
*function call*, not an agent: a single Claude Messages request with a forced
tool call whose ``input_schema`` is the extraction contract. The model fills the
tool input; we read it back as a dict. No tools loop, no autonomy, no session.

Implementation mirrors the existing Strader Anthropic pattern
(scripts/lux_vision_probe.py): raw httpx against the Messages API, key from
``ANTHROPIC_API_KEY_DIRECT``, IPv4 local-address binding for the WSL distro.
Forced tool use (``tool_choice`` pinned to the tool) is more robust than
"return only JSON" prompting — the API guarantees a tool_use block whose input
conforms to the schema.

The ``extract`` callable is injected into parse.py, so unit tests mock it and
never hit the network.
"""
from __future__ import annotations

import os
from typing import Any, Callable

import httpx

from .schema import LEVEL_KINDS, TRIGGER_TYPES

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
# Current Opus. The repo's earlier probe used claude-opus-4-7; 4.8 is the
# current Opus-tier model with the same request surface.
MODEL = "claude-opus-4-8"
TIMEOUT_S = 120.0
LOCAL_ADDR_V4 = "0.0.0.0"  # WSL IPv6 is broken on this distro (see lux_vision_probe)
MAX_TOKENS = 8000

TOOL_NAME = "record_mancini_levels"

# The extraction contract, as a JSON Schema. Field names match
# schema.ParseResult so the tool input maps 1:1 onto ParseResult.from_dict.
TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "date": {
            "type": "string",
            "description": "ISO date (YYYY-MM-DD) the plan is FOR. If the "
            "newsletter states a session date, use it; else empty string.",
        },
        "instrument": {
            "type": "string",
            "description": "Primary instrument, e.g. 'ES'. Empty if unclear.",
        },
        "session_bias": {
            "type": "string",
            "description": "Short prose summary of Mancini's stated directional bias.",
        },
        "levels": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "price": {
                        "type": "number",
                        "description": "The numeric price. MUST be a number that "
                        "literally appears in the newsletter text.",
                    },
                    "kind": {"type": "string", "enum": list(LEVEL_KINDS)},
                    "label": {"type": "string"},
                    "source_quote": {
                        "type": "string",
                        "description": "Verbatim newsletter text this price came "
                        "from. Copy it exactly; do not paraphrase.",
                    },
                },
                "required": ["price", "kind", "source_quote"],
            },
        },
        "commentary": {
            "type": "array",
            "description": "Forward-looking conditional guidance ('if X then Y'), "
            "NOT recap of past price action.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "trigger": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "type": {"type": "string", "enum": list(TRIGGER_TYPES)},
                            "anchor_prices": {
                                "type": "array",
                                "items": {"type": "number"},
                                "description": "Prices that make this note "
                                "relevant. Each MUST appear in the newsletter.",
                            },
                            "condition_text": {"type": "string"},
                        },
                        "required": ["type"],
                    },
                    "source_quote": {
                        "type": "string",
                        "description": "Verbatim newsletter text this note came from.",
                    },
                },
                "required": ["text", "trigger", "source_quote"],
            },
        },
        "raw_excerpt": {
            "type": "string",
            "description": "The Trade Plan span you extracted levels from.",
        },
    },
    "required": ["date", "instrument", "session_bias", "levels", "commentary"],
}

SYSTEM_PROMPT = (
    "You extract structured trading levels and forward-looking commentary from "
    "Adam Mancini's nightly newsletter. This is financial data: accuracy is "
    "paramount.\n\n"
    "HARD RULES:\n"
    "- Only record a numeric price that LITERALLY appears in the newsletter "
    "text. Never infer, round, or invent a level. If you are unsure a number is "
    "really a level, omit it.\n"
    "- For every level and every commentary anchor price, copy the exact "
    "surrounding text into source_quote. A downstream check rejects any price "
    "not found verbatim in the source, so do not guess.\n"
    "- 'commentary' is for forward-looking, conditional guidance about the "
    "coming session ('if we hold X, target Y'; 'losing Z opens the door to W'). "
    "Do NOT put past-session recap there.\n"
    "- Classify each level kind precisely (support/resistance/pivot/target/"
    "trigger) based on how Mancini frames it."
)


def build_payload(raw_text: str, *, model: str = MODEL) -> dict[str, Any]:
    """Construct the Messages API request body for a forced extraction call."""
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "tools": [
            {
                "name": TOOL_NAME,
                "description": "Record the structured levels and forward-looking "
                "commentary extracted from the Mancini newsletter.",
                "input_schema": TOOL_SCHEMA,
            }
        ],
        # Force the tool: the response is guaranteed to contain a tool_use block
        # for TOOL_NAME whose input conforms to TOOL_SCHEMA.
        "tool_choice": {"type": "tool", "name": TOOL_NAME, "disable_parallel_tool_use": True},
        "messages": [
            {
                "role": "user",
                "content": "Extract levels and forward-looking commentary from "
                "this Mancini newsletter:\n\n<newsletter>\n" + raw_text + "\n</newsletter>",
            }
        ],
    }


def _extract_tool_input(response: dict[str, Any]) -> dict[str, Any]:
    """Pull the forced tool_use block's input from a Messages response."""
    stop = response.get("stop_reason")
    if stop == "refusal":
        details = response.get("stop_details") or {}
        raise RuntimeError(f"model refused extraction: {details}")
    for block in response.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == TOOL_NAME:
            return block.get("input", {})
    raise RuntimeError(
        f"no '{TOOL_NAME}' tool_use block in response (stop_reason={stop})"
    )


def extract(
    raw_text: str,
    *,
    api_key: str | None = None,
    model: str = MODEL,
    timeout_s: float = TIMEOUT_S,
) -> dict[str, Any]:
    """Call Claude once and return the validated tool-input dict.

    Raises RuntimeError on refusal or a missing tool block, and lets httpx
    errors (network, non-2xx) propagate so the caller's retry/fallback policy
    can decide.
    """
    key = api_key or os.environ.get("ANTHROPIC_API_KEY_DIRECT")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY_DIRECT not set")

    payload = build_payload(raw_text, model=model)
    headers = {
        "x-api-key": key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    transport = httpx.HTTPTransport(local_address=LOCAL_ADDR_V4)
    with httpx.Client(transport=transport, timeout=timeout_s) as client:
        resp = client.post(API_URL, headers=headers, json=payload)
    resp.raise_for_status()
    return _extract_tool_input(resp.json())


# Type alias for the injectable extractor used by parse.py.
Extractor = Callable[[str], dict[str, Any]]
