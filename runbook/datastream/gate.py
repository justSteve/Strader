"""Datastream health gate. [co-i10h]

Reads the per-day corpus manifest and decides whether the data feeds are healthy
enough for the Runbook to proceed. The pure logic lives in ``evaluate`` (a
function over a manifest dict) so it is fully unit-testable without touching the
filesystem; ``check`` is the thin I/O wrapper that loads the manifest file.

Manifest shape (see market/corpus/paths.py and a real
data/corpus/YYYY-MM-DD/manifest.json):

    {
      "date": "2026-05-21",
      "streams": {
        "databento_opra":    {"cycles": 435985, "errors": [], "last_pull_utc": "2026-05-23T20:42:10Z"},
        "databento_glbx_es": {"cycles": 124928, "errors": [], "last_pull_utc": "2026-05-24T00:55:14Z"}
      }
    }

Health criteria (pilot v1):
  * manifest exists and parses
  * each required stream is present
  * each required stream has cycles > 0
  * each required stream has an empty errors list
  * each required stream's last_pull_utc is within ``max_age_hours`` of ``now``

The exact production liveness signals (live-tick recency vs T+1 batch, expected
symbol coverage) are defined in #1's own follow-on spec.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Streams a healthy trading day must have.
#
# databento_opra was required here until 2026-08-07, when Steve halted the daily
# OPRA import — historical OPRA is now pulled ad hoc when something warrants it
# (st-7av4). A gate that requires a stream nobody collects fails every single
# morning, and a gate that always fails teaches its operator to bypass it, which
# costs more than the check was ever worth.
#
# This does NOT mean OPRA stopped mattering. The measurement scripts that read
# databento_opra.jsonl — fly_replay, premium_trajectory, iv_pin_study,
# expected_move, greek_snapshot_study, trough_time_volume_analysis — still need
# it, and they should each fail loudly on a day that has no OPRA file rather
# than lean on this gate to have caught it upstream.
DEFAULT_REQUIRED_STREAMS = ("databento_glbx_es",)
DEFAULT_MAX_AGE_HOURS = 36.0  # T+1 batch + weekend slack


@dataclass
class GateResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    checked: dict[str, Any] = field(default_factory=dict)


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    raw = ts.strip()
    # Accept trailing Z (UTC) which datetime.fromisoformat historically rejected.
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def evaluate(
    manifest: dict[str, Any],
    *,
    now: datetime | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    required_streams: tuple[str, ...] = DEFAULT_REQUIRED_STREAMS,
) -> GateResult:
    """Pure evaluation of a manifest dict. No I/O."""
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    checked: dict[str, Any] = {}

    streams = manifest.get("streams") or {}
    if not isinstance(streams, dict):
        return GateResult(ok=False, reasons=["manifest has no 'streams' object"])

    for name in required_streams:
        st = streams.get(name)
        if st is None:
            reasons.append(f"required stream '{name}' missing from manifest")
            checked[name] = {"present": False}
            continue

        cycles = st.get("cycles", 0) or 0
        errors = st.get("errors") or []
        last_pull = st.get("last_pull_utc", "")
        last_dt = _parse_iso(last_pull)
        age_hours = None
        if last_dt is not None:
            age_hours = (now - last_dt).total_seconds() / 3600.0

        checked[name] = {
            "present": True,
            "cycles": cycles,
            "errors": len(errors),
            "last_pull_utc": last_pull,
            "age_hours": round(age_hours, 2) if age_hours is not None else None,
        }

        if cycles <= 0:
            reasons.append(f"stream '{name}' has no cycles (cycles={cycles})")
        if errors:
            reasons.append(f"stream '{name}' reported {len(errors)} error(s)")
        if last_dt is None:
            reasons.append(
                f"stream '{name}' has missing/invalid last_pull_utc {last_pull!r}"
            )
        elif age_hours is not None and age_hours > max_age_hours:
            reasons.append(
                f"stream '{name}' is stale: last pull {age_hours:.1f}h ago "
                f"(> {max_age_hours}h)"
            )

    return GateResult(ok=not reasons, reasons=reasons, checked=checked)


def check(
    manifest_path: Path | str | None = None,
    *,
    day=None,
    now: datetime | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    required_streams: tuple[str, ...] = DEFAULT_REQUIRED_STREAMS,
) -> GateResult:
    """Load the manifest file and evaluate it.

    If ``manifest_path`` is None, derive it from the corpus convention for
    ``day`` (default: today, US/Central) via market.corpus.paths.
    """
    import json

    if manifest_path is None:
        from market.corpus.paths import manifest_path as corpus_manifest_path

        manifest_path = corpus_manifest_path(day)
    path = Path(manifest_path)
    if not path.exists():
        return GateResult(ok=False, reasons=[f"manifest not found: {path}"])
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return GateResult(ok=False, reasons=[f"manifest is not valid JSON: {e}"])

    return evaluate(
        manifest,
        now=now,
        max_age_hours=max_age_hours,
        required_streams=required_streams,
    )
