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
  * each required stream has an empty errors list — EXCEPT recovered
    reconnects on a fully-covered day (see below)
  * each required stream's last write COVERS the data-day (see below)

Recovered reconnects are a warning, not a hole [st-mmh9]
--------------------------------------------------------
The collector logs ``reconnect #N: ... (possible gap)`` when its heartbeat
lapses and it re-subscribes (corpus_stream_databento.py). That entry records a
possible gap bounded by the heartbeat timeout — tens of seconds — after which
the stream demonstrably kept collecting. On 2026-08-12 the gate halted the
morning Mancini parse over exactly one such entry on a day with 267k cycles
and a last write past the close. Failing the day over that asks the wrong
question, and (per the coverage fix below) a gate that fails on immaterial
grounds trains its operator to bypass it.

So: when every error is reconnect-shaped, there are at most
``MAX_RECOVERED_RECONNECTS`` of them, and the stream verifiably covered its
day, the errors demote to ``recovered_reconnects`` in ``checked`` instead of
failing the gate. Any other error string, an uncovered day, or a flapping feed
(more reconnects than the ceiling) stays fatal.

Freshness is coverage, not recency [st-jc8p]
-------------------------------------------
This check used to be "last_pull_utc is within 36h of now", and that is the
wrong question for a stream filled by LIVE capture. For a T+1 batch stream
last_pull_utc is the FETCH time, so it refreshes every morning and 36h works.
For a live stream it is the SESSION END — 2026-08-07T20:05:00Z, Friday 15:05 CT
— and nothing ever touches it again, because the batch has nothing to fetch for
a day live capture already filled. Friday close to Monday morning is 64h, so the
gate failed EVERY MONDAY by construction. It took down the 06:30 corpus job and
the 08:15 Mancini pre-open on 2026-08-10 while the data was perfectly good:
2026-08-07 held 377,721 ES ticks with a clean "0 reconnect(s)" close.

The two obvious repairs are both worse than the bug:

  * ``--no-gate`` at the call site — a gate that is routinely bypassed is not a
    gate, and the operator learns to reach for the flag before reading why.
  * raising 36h to 72h — buys one weekend and blinds the check to a Friday feed
    that genuinely died at 10:00, which is the exact failure it exists to catch.

So the question changed instead. A stream covers its day if its last write lands
at or after that day's session close. That is true of a T+1 batch (fetched after
the close), true of a healthy live capture (stops at 15:05 CT, five minutes past
the 15:00 cash close), and false of a capture that died mid-session — which is
what we actually want to know. Wall-clock age no longer enters into it, so the
answer does not change just because a weekend went by.

``max_age_hours`` survives only as the fallback for a manifest with no usable
``date`` field, where there is no session close to measure against.

Degraded is a third answer, not a softer failure [co-03ojd.7 J-F3]
------------------------------------------------------------------
The gate halts only over the REQUIRED streams. But the manifest also records
every other stream a collector was configured to fill that day — GexBot, the 1
Hz leg, Schwab, an ad-hoc OPRA pull — and a configured stream that ran and got
NOTHING (``cycles=0`` with an error list) used to be invisible here: the verdict
line said HEALTHY, the pre-open heartbeat said ``corpus [hard] ok``, and the
only record was one manifest field nobody opened. Measured 2026-08-07 → 08-15:
the SPXW OPRA pull failed 403 on seven consecutive runs, the job exited rc=2
nightly, and the gate printed HEALTHY every morning.

So ``evaluate`` now also returns ``warnings``: one per present, non-required
stream that reports ``cycles <= 0`` together with at least one error. ``ok``
is untouched — the day is still tradable on the required tape — but the caller
gets a distinct DEGRADED state to print and alert on. It is deliberately not a
failure: making it one would re-create the always-failing gate the required-
stream list was pruned to avoid (see DEFAULT_REQUIRED_STREAMS).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from strader.market_calendar import CENTRAL, session_close_ct

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

#: Fallback only — used when a manifest carries no usable ``date`` and there is
#: therefore no session close to measure coverage against. Not the primary rule;
#: see the module docstring on why wall-clock age is the wrong question.
DEFAULT_MAX_AGE_HOURS = 36.0

#: How far before the session close a stream's last write may land and still
#: count as having covered the day. Live capture stops at 15:05 CT against a
#: 15:00 close, so it clears this comfortably; the slack absorbs a final commit
#: that lands a few minutes early without excusing a feed that died at lunchtime.
DEFAULT_CLOSE_SLACK_MIN = 10.0

#: Reconnect-shaped errors above this count on a covered day are reported as a
#: WARNING naming the count — a flapping feed deserves a look — but they do not
#: fail the day. Revised 2026-09-04 (co-8b60y): under the original rule
#: [st-mmh9] the count was fatal, and a 42-hour network outage left 2026-09-03
#: carrying 6,466 reconnect notes per stream; the tape was then backfilled in
#: full and the day still read UNHEALTHY, which halted the 08:15 parse and
#: failed the 08:25 heartbeat on data that was present. Nothing ever removes a
#: note from a manifest, so a fatal count is a permanent verdict on a day whose
#: data may be whole. Coverage and cycles are the questions the gate exists to
#: ask; the note count is a fact about the transport, and it is surfaced as one.
MAX_RECOVERED_RECONNECTS = 3


def _is_reconnect_error(err: Any) -> bool:
    """True for the collector's transport entries: the heartbeat-lapse line
    ``reconnect #1: BentoError: Gateway timeout: 40 second(s) since last
    message (possible gap)`` and the budget line ``giving up after 6
    reconnects`` that closes a run which never got through. Both prefixes are
    the stable contract with corpus_stream_databento.py's error logging
    (``_note_reconnect`` and the give-up branch). Measured 2026-09-04: the
    2026-09-03 manifest held 5,544 of the first and 922 of the second per
    stream, and a rule that knew only the first read the day as carrying 922
    real errors."""
    return isinstance(err, str) and (err.startswith("reconnect #")
                                     or err.startswith("giving up after "))


@dataclass
class GateResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    checked: dict[str, Any] = field(default_factory=dict)
    #: Non-fatal findings about configured-but-empty streams [co-03ojd.7 J-F3].
    #: ``ok`` may be True while this is non-empty — that is the DEGRADED state.
    warnings: list[str] = field(default_factory=list)

    @property
    def degraded(self) -> bool:
        return self.ok and bool(self.warnings)

    @property
    def status(self) -> str:
        """HEALTHY / DEGRADED / UNHEALTHY — the word the callers print."""
        if not self.ok:
            return "UNHEALTHY"
        return "DEGRADED" if self.warnings else "HEALTHY"


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


def _parse_day(value: Any) -> _date | None:
    """The data-day a manifest describes, or None if it does not say."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _date.fromisoformat(value.strip())
    except ValueError:
        return None


def coverage_deadline(day: _date, *, slack_min: float = DEFAULT_CLOSE_SLACK_MIN) -> datetime:
    """Earliest UTC instant a last write may land and still cover ``day``.

    Holiday- and early-close-aware via ``strader.market_calendar``, so a 12:00 CT
    half session is judged against noon rather than against a 15:00 close it was
    never going to reach.
    """
    close = datetime.combine(day, session_close_ct(day), tzinfo=CENTRAL)
    return (close - timedelta(minutes=slack_min)).astimezone(timezone.utc)


def evaluate(
    manifest: dict[str, Any],
    *,
    now: datetime | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    required_streams: tuple[str, ...] = DEFAULT_REQUIRED_STREAMS,
    close_slack_min: float = DEFAULT_CLOSE_SLACK_MIN,
) -> GateResult:
    """Pure evaluation of a manifest dict. No I/O."""
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    warnings: list[str] = []
    checked: dict[str, Any] = {}

    streams = manifest.get("streams") or {}
    if not isinstance(streams, dict):
        return GateResult(ok=False, reasons=["manifest has no 'streams' object"])

    day = _parse_day(manifest.get("date"))
    deadline = coverage_deadline(day, slack_min=close_slack_min) if day else None

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

        covers_day = (None if last_dt is None or deadline is None
                      else last_dt >= deadline)
        resolved = st.get("errors_resolved") or {}
        checked[name] = {
            "present": True,
            "cycles": cycles,
            "errors": len(errors),
            "errors_resolved": int(resolved.get("count", 0) or 0) if isinstance(resolved, dict) else 0,
            "last_pull_utc": last_pull,
            "age_hours": round(age_hours, 2) if age_hours is not None else None,
            "covers_day": covers_day,
        }

        if cycles <= 0:
            reasons.append(f"stream '{name}' has no cycles (cycles={cycles})")
        if errors:
            # Reconnect-shaped entries on a verifiably covered day are notes
            # about the transport, not holes in the tape: the day has rows and
            # a last write past its close. They pass, and above the ceiling
            # they pass with a warning that names the count. Anything that is
            # not reconnect-shaped stays fatal. [st-mmh9; revised co-8b60y]
            if (covers_day is True and cycles > 0
                    and all(_is_reconnect_error(e) for e in errors)):
                checked[name]["recovered_reconnects"] = len(errors)
                if len(errors) > MAX_RECOVERED_RECONNECTS:
                    warnings.append(
                        f"stream '{name}' reconnected {len(errors)} times on a "
                        f"covered day (ceiling {MAX_RECOVERED_RECONNECTS}) — the tape "
                        f"is whole, the feed was flapping; worth a look, not a halt"
                    )
            else:
                reasons.append(f"stream '{name}' reported {len(errors)} error(s)")
        if last_dt is None:
            reasons.append(
                f"stream '{name}' has missing/invalid last_pull_utc {last_pull!r}"
            )
        elif deadline is not None:
            # Coverage, not recency. A stream that stopped before its day closed
            # has a hole in it; one that stopped after does not, however long ago
            # that was. See the module docstring.
            if last_dt < deadline:
                short_by = (deadline - last_dt).total_seconds() / 60.0
                reasons.append(
                    f"stream '{name}' stopped before {day} closed: last pull "
                    f"{last_pull}, {short_by:.0f} min short of the "
                    f"{session_close_ct(day).strftime('%H:%M')} CT close. The "
                    f"day has a hole in it — this is not a staleness warning."
                )
        elif age_hours is not None and age_hours > max_age_hours:
            # Fallback: no data-day in the manifest, so there is no close to
            # measure against and wall-clock age is all we have.
            reasons.append(
                f"stream '{name}' is stale: last pull {age_hours:.1f}h ago "
                f"(> {max_age_hours}h; manifest carries no 'date' so coverage "
                f"could not be checked)"
            )

    # Configured-but-empty streams outside the required set: a collector ran
    # against this day and produced nothing but errors. Not fatal (see the
    # module docstring) but never silent again. [co-03ojd.7 J-F3]
    for name, st in streams.items():
        if name in required_streams or not isinstance(st, dict):
            continue
        cycles = st.get("cycles", 0) or 0
        errors = st.get("errors") or []
        if cycles <= 0 and errors:
            first = str(errors[0])
            if len(first) > 160:
                first = first[:157] + "..."
            checked[name] = {"present": True, "cycles": cycles,
                             "errors": len(errors), "empty_with_errors": True}
            warnings.append(
                f"configured stream '{name}' produced nothing: cycles={cycles} "
                f"with {len(errors)} error(s); first: {first}"
            )

    return GateResult(ok=not reasons, reasons=reasons, checked=checked,
                      warnings=warnings)


def check(
    manifest_path: Path | str | None = None,
    *,
    day=None,
    now: datetime | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    required_streams: tuple[str, ...] = DEFAULT_REQUIRED_STREAMS,
    close_slack_min: float = DEFAULT_CLOSE_SLACK_MIN,
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
        close_slack_min=close_slack_min,
    )
