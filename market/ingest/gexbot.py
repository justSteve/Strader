"""GexBot State-tier ingestion + distillation. [st-rks]

The job of this module is to convert raw GexBot responses into a 4-tuple
decision-grade emission Steve can read at a glance — center_strike,
regime, confidence, and a plain-English sentence. The ladders and raw
strike arrays stay inside this module; Steve never sees them.

V1 thresholds are educated guesses (range cutoffs of 50 / 100 pts for
SPX, distance-to-edge ratios of 0.25 / 0.30). These get calibrated
against actual EOD outcomes once the pairing harness has 20+ days of
data; until then, treat the regime/confidence as approximations, not
authority.

Per spec docs/gexbot/gexbot.spec3.yaml: 1 req/sec/metric, <=1s timeout
for steady-state polling, IPv4 only on this distro (WSL IPv6 broken).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from strader.settings import load_gexbot

BASE_URL = "https://api.gex.bot/v2"
USER_AGENT = "Strader-Distill/0.1 (st-rks)"
TIMEOUT_S = 5.0
LOCAL_ADDR_V4 = "0.0.0.0"

Regime = Literal["pinning", "trending", "unclear"]
Confidence = Literal["low", "med", "high"]


@dataclass(frozen=True)
class Distillation:
    """The 4-tuple Steve sees. Everything else stays in the module."""
    timestamp: int
    spot: float
    center_strike: int
    regime: Regime
    confidence: Confidence
    reason: str


def load_api_key(env_path: Path) -> str:
    """The GexBot bearer, through the shared fail-fast loader.

    ``env_path`` is the repo ``.env`` — the pointer file. The value itself comes
    from the vault file it names, never from the tree (strader/config.py,
    convention 2026-08-25). Raises ``strader.config.ConfigError`` when the key
    is missing, malformed, or sitting in ``.env``.
    """
    return load_gexbot(env_path)["GEXBOT_API_KEY"]


def make_client(api_key: str) -> httpx.Client:
    """Build the IPv4-only httpx client with bearer auth pre-loaded."""
    token = api_key if api_key.startswith("gexbot_custom_") else f"gexbot_custom_{api_key}"
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    transport = httpx.HTTPTransport(local_address=LOCAL_ADDR_V4)
    return httpx.Client(
        base_url=BASE_URL,
        headers=headers,
        transport=transport,
        timeout=TIMEOUT_S,
    )


def fetch_state(client: httpx.Client, ticker: str, category: str) -> dict:
    """One state-endpoint pull. Caller is responsible for rate-limiting."""
    resp = client.get(f"/{ticker}/state/{category}")
    resp.raise_for_status()
    return resp.json()


def distill(state_resp: dict) -> Distillation:
    """Convert a /state/* response into the 4-tuple emission.

    Algorithm V1:
    - Range = major_positive - major_negative (the bracket the market is
      pricing for the session).
    - Center strike: if spot sits within 25% of either edge, lean to that
      edge (the magnet is closer than the flip); otherwise round spot to
      the nearest 5pt strike (or zero-gamma if very close to it).
    - Regime: tight range (<50pts on SPX) = pinning; wide (>100pts) =
      trending; in between = unclear.
    - Confidence: high only when pinning + spot mid-range; low when spot
      is sitting on the gamma flip (transition state); med otherwise.
    """
    spot: float = state_resp["spot"]
    major_pos: float = state_resp["major_positive"]
    major_neg: float = state_resp["major_negative"]
    long_g: float = state_resp.get("major_long_gamma", 0.0)
    short_g: float = state_resp.get("major_short_gamma", 0.0)

    range_size = major_pos - major_neg
    dist_to_pos = abs(spot - major_pos)
    dist_to_neg = abs(spot - major_neg)
    edge_frac = min(dist_to_pos, dist_to_neg) / range_size if range_size > 0 else 0.0

    if range_size < 50:
        regime: Regime = "pinning"
    elif range_size > 100:
        regime = "trending"
    else:
        regime = "unclear"

    if dist_to_pos < range_size * 0.25:
        center = round(major_pos / 5) * 5
        bias = "upper-edge"
    elif dist_to_neg < range_size * 0.25:
        center = round(major_neg / 5) * 5
        bias = "lower-edge"
    else:
        center = round(spot / 5) * 5
        bias = "mid-range"

    # Spot sitting on zero_gamma (within 5pts) is a transition signal —
    # confidence drops because price can resolve either way.
    zero_g = state_resp.get("zero_gamma")
    on_flip = zero_g is not None and abs(spot - zero_g) < 5

    if on_flip:
        confidence: Confidence = "low"
    elif regime == "pinning" and edge_frac > 0.30:
        confidence = "high"
    elif regime == "unclear":
        confidence = "low"
    else:
        confidence = "med"

    reason = (
        f"Spot {spot:.1f} in {major_neg:.0f}–{major_pos:.0f} ({range_size:.0f}pt range, "
        f"{bias}). Long-gamma wall {long_g:.0f}, short-gamma {short_g:.0f}. "
        f"{regime.capitalize()} regime"
        + (", transition risk (spot on flip)." if on_flip else ".")
    )

    return Distillation(
        timestamp=int(state_resp["timestamp"]),
        spot=float(spot),
        center_strike=int(center),
        regime=regime,
        confidence=confidence,
        reason=reason,
    )
