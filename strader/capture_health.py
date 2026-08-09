"""Live-capture health assessment — is the Databento streamer actually collecting? [st-6qx4]

`scripts/corpus_stream_databento.py` is the repo's first long-lived process; every
other piece of automation here is a cron tick that starts, does a thing, and
exits. That difference is the whole problem. A cron job that fails leaves a
non-zero rc and a log; a streamer that dies at 02:00 leaves nothing at all until
someone looks at a pane at 08:30 — and live trades and MBP-1 quotes are NEVER
backfilled, so those six hours cannot be bought later at any price.

This module is the pure assessor behind the supervisor. It answers one question
— *is a capture running and is data still arriving?* — from three inputs the
caller gathers: the live process list, the day's manifest, and the previous
answer. No I/O, no clock of its own; `scripts/capture_health.py` owns all of
that, so every branch here is unit-testable with an injected `now`.

Two failure modes, not one
--------------------------
DEATH is the easy one: no process. Detected BY PROCESS, never by tmux window
name — on 2026-07-23 three windows were named `gauge` with exactly one live
process behind them [st-cm5], and a window is not proof of anything.

STALENESS is the one that actually hurts: the process is alive, the pane looks
busy, and nothing is arriving. A pid check calls that healthy. The manifest does
not: `StreamWorker._commit_counts` only fires from inside the record loop, so
`streams.<name>.cycles` advances if and only if ticks are landing. Cycles not
moving while the venue is open is the true liveness signal.

`cycles` for a live stream is a TICK COUNT, not a poll count — the streamer
passes its tick delta as `increment_cycles` every 10s. Compare successive
observations for movement; never read an absolute value as meaningful.

Why the venue calendar is here
------------------------------
"Not advancing" is only a fault when the tape is open. ES has four regular
closures, and without them a supervisor cries wolf twice a day and gets ignored,
which is worse than no supervisor: the daily 15:15-15:30 CT pause, the
16:00-17:00 CT maintenance halt, the Friday 16:00 close and the Sunday 17:00
re-open. Holidays are NOT modeled for GLBX — same choice `most_recent_session_day`
makes, and the same consequence: a holiday can produce one spurious `stale`. That
is the safe direction to be wrong in, and it is deliberately not "fixed" by
pointing GLBX at the NYSE holiday table: CME equity-index futures trade a
shortened session on most NYSE closures (MLK, Presidents, Memorial, Juneteenth,
Labor, July 4, Thanksgiving), so an NYSE-closed day is a day ES really is
printing. Calling it closed would suppress a genuine `stale` seven times a year.

VENUES. The `venue` argument picks which calendar `expected` is measured against.
`"globex"` is the ES streamer's, above. `"cash"` [st-p3lv] means "the US cash
equity market holds a session today at all", holiday-aware via
`strader.market_calendar`, with the clock bounds left entirely to
`--window-start/--window-end` — that is what a GexBot collector wants, since its
pre-open ramp starts an hour before the cash open but a holiday is dead all day.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date as _date, datetime, time as _time, timezone
from zoneinfo import ZoneInfo

from strader.market_calendar import is_trading_day

CENTRAL = ZoneInfo("America/Chicago")
UTC = timezone.utc

#: Streamer `--streams` key -> corpus/manifest stream name. Mirrors
#: `scripts/corpus_stream_databento.py: default_specs()`; a test asserts the two
#: agree so this cannot drift silently.
STREAM_KEYS: dict[str, str] = {
    "opra": "databento_opra",
    "es": "databento_glbx_es",
    "es-mbp1": "databento_glbx_es_mbp1",
}

#: Phase B capture (st-d5f): ES trades for the footprint, MBP-1 for absorption.
DEFAULT_STREAMS: tuple[str, ...] = ("es", "es-mbp1")

#: How long a watched stream may sit at the same cycle count, with the venue
#: open, before it counts as stale. Generous on purpose: ES top-of-book updates
#: many times a second whenever GLBX is open, so ten quiet minutes is not a slow
#: tape, it is a dead connection. Tighter would trade a real guard for noise.
DEFAULT_STALE_SECS: float = 600.0

#: Grace after launch before an empty manifest is held against a process — it
#: has to connect, subscribe and receive before the first 10s commit lands.
DEFAULT_GRACE_SECS: float = 180.0

STATUS_OK = "ok"                # a capture is running and data is arriving
STATUS_STARTING = "starting"    # just launched, nothing committed yet
STATUS_QUIET = "quiet"          # alive, nothing arriving, venue closed — correct
STATUS_IDLE = "idle"            # no capture, and none expected — correct
STATUS_STALE = "stale"          # alive but a stream stopped advancing, venue open
STATUS_DEAD = "dead"            # no capture, one was expected
STATUS_DUPLICATE = "duplicate"  # >1 capture — both appending to the same file

#: Statuses that need someone (or the supervisor) to act.
ACTIONABLE = frozenset({STATUS_STALE, STATUS_DEAD, STATUS_DUPLICATE})

# --- ES / GLBX session calendar (CT) ---------------------------------------
GLOBEX_PAUSE = (_time(15, 15), _time(15, 30))   # daily equity-index pause
GLOBEX_MAINT = (_time(16, 0), _time(17, 0))     # daily maintenance halt
GLOBEX_WEEK_OPEN = _time(17, 0)                 # Sunday re-open
GLOBEX_WEEK_CLOSE = _time(16, 0)                # Friday close


def globex_open(now_ct: datetime) -> bool:
    """True when ES should be printing. Holidays are not modeled (see module doc)."""
    t = now_ct.time()
    dow = now_ct.weekday()          # 0=Mon .. 6=Sun
    if dow == 5:                    # Saturday — closed all day
        return False
    if dow == 6:                    # Sunday — closed until the 17:00 re-open
        return t >= GLOBEX_WEEK_OPEN
    if GLOBEX_PAUSE[0] <= t < GLOBEX_PAUSE[1]:
        return False
    if dow == 4:                    # Friday — closed from 16:00 to Sunday
        return t < GLOBEX_WEEK_CLOSE
    return not (GLOBEX_MAINT[0] <= t < GLOBEX_MAINT[1])


def cash_venue_open(now_ct: datetime) -> bool:
    """True when the US cash equity market holds a session on this date. [st-p3lv]

    Deliberately date-only. The clock window belongs to ``--window-start`` /
    ``--window-end``, which the GexBot collector sets wider than the cash session
    on purpose (pre-open ramp). Folding the 08:30 open in here would report
    ``idle`` through the ramp and the supervisor would never start the collector.
    """
    return is_trading_day(now_ct.date())


#: venue key -> (predicate, label used in verdict messages).
VENUES: dict[str, tuple] = {
    "globex": (globex_open, "GLBX"),
    "cash": (cash_venue_open, "the cash market"),
}
DEFAULT_VENUE = "globex"


def _hm(s: str) -> _time:
    h, m = (int(x) for x in s.split(":"))
    return _time(h, m)


def in_window(now_ct: datetime, start: str, end: str) -> bool:
    """Inside the CT clock window a capture is configured to run in.

    Bounds are inclusive at both ends so the round-the-clock default
    (00:00-23:59) covers the final minute of the day, which is exactly when the
    day-rollover relaunch has to happen.
    """
    return _hm(start) <= now_ct.time() <= _hm(end)


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        try:
            d = datetime.fromisoformat(s)
        except ValueError:
            return None
        return d if d.tzinfo else d.replace(tzinfo=UTC)


@dataclass(frozen=True)
class CaptureHealth:
    """One supervisor verdict. Serializable via ``to_dict``; the serialized form
    is both the state file and the next run's ``prev``."""
    status: str
    message: str
    checked_at: str                  # UTC iso of this observation
    day: str                         # corpus day the running capture writes to
    pids: list[int]
    capture_age_secs: float | None   # age of the live capture, None when dead
    in_window: bool
    globex_open: bool
    expected: bool                   # a capture SHOULD be running right now
    streams: dict[str, dict]         # manifest name -> per-stream observation
    stale_streams: list[str]
    since_utc: str                   # when this status first appeared
    last_ok_utc: str | None          # last observation with data arriving
    restarts: int                    # supervisor restarts recorded this day
    restarts_day: str

    @property
    def ok(self) -> bool:
        return self.status not in ACTIONABLE

    @property
    def actionable(self) -> bool:
        return self.status in ACTIONABLE

    @property
    def all_stale(self) -> bool:
        """Every watched stream frozen — an unambiguous dead connection, as
        opposed to one worker dying while the others keep receiving."""
        return bool(self.streams) and len(self.stale_streams) == len(self.streams)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ok"] = self.ok
        d["actionable"] = self.actionable
        d["all_stale"] = self.all_stale
        return d


def resolve_stream_names(streams) -> list[str]:
    """Accept either streamer keys (`es-mbp1`) or manifest names
    (`databento_glbx_es_mbp1`); return manifest names."""
    out = []
    for s in streams:
        s = s.strip()
        if not s:
            continue
        out.append(STREAM_KEYS.get(s, s))
    return out


def assess_capture(
    now_ct: datetime,
    *,
    day: _date,
    manifest: dict | None,
    pids: list[int],
    capture_age_secs: float | None = None,
    prev: dict | None = None,
    streams=DEFAULT_STREAMS,
    stale_secs: float = DEFAULT_STALE_SECS,
    grace_secs: float = DEFAULT_GRACE_SECS,
    window_start: str = "00:00",
    window_end: str = "23:59",
    venue: str = DEFAULT_VENUE,
) -> CaptureHealth:
    """Pure verdict from (process list, manifest, previous verdict).

    ``prev`` is the previous ``to_dict()``. It is what makes staleness knowable
    at all: a single manifest read cannot tell you whether a number is moving,
    only successive reads can. When ``prev`` is absent or belongs to another
    corpus day, every stream's quiet clock starts now — a fresh supervisor never
    inherits a stale verdict it did not observe.
    """
    now_utc = now_ct.astimezone(UTC)
    now_iso = utc_iso(now_utc)
    day_iso = day.isoformat()
    try:
        venue_open, venue_label = VENUES[venue]
    except KeyError:
        raise ValueError(
            f"unknown venue {venue!r}; expected one of {sorted(VENUES)}"
        ) from None
    gopen = venue_open(now_ct)
    inwin = in_window(now_ct, window_start, window_end)
    expected = gopen and inwin

    prev = prev or {}
    same_day = prev.get("day") == day_iso
    prev_streams = (prev.get("streams") or {}) if same_day else {}
    mstreams = ((manifest or {}).get("streams") or {})

    observed: dict[str, dict] = {}
    stale_streams: list[str] = []
    for name in resolve_stream_names(streams):
        entry = mstreams.get(name) or {}
        present = bool(mstreams.get(name))
        cycles = entry.get("cycles") if present else None
        p = prev_streams.get(name) or {}
        # Any CHANGE counts as advance, including a decrease: a relaunch against
        # a fresh manifest resets the counter, and that is movement, not death.
        if p.get("advanced_utc") and p.get("cycles") == cycles:
            advanced = p["advanced_utc"]
        else:
            advanced = now_iso
        adv_dt = _parse_iso(advanced) or now_utc
        quiet = (now_utc - adv_dt).total_seconds()
        stale = quiet > stale_secs
        observed[name] = {
            "present": present,
            "cycles": cycles,
            "advanced_utc": advanced,
            "quiet_secs": round(quiet, 1),
            "stale": stale,
            "last_pull_utc": entry.get("last_pull_utc"),
            "errors": len(entry.get("errors") or []),
        }
        if stale:
            stale_streams.append(name)

    # --- the verdict ------------------------------------------------------
    if len(pids) > 1:
        status = STATUS_DUPLICATE
        message = (f"{len(pids)} capture processes alive (pids {pids}) — they are "
                   f"appending the SAME corpus files, so today's tape is being "
                   f"double-written. Stop all but one by hand; the supervisor "
                   f"will not choose for you.")
    elif not pids:
        if expected:
            status = STATUS_DEAD
            message = (f"no capture process, and one is expected "
                       f"({window_start}-{window_end} CT, {venue_label} open). Live "
                       f"data is not backfillable — every minute down is gone.")
        else:
            why = (f"{venue_label} closed" if not gopen
                   else f"outside {window_start}-{window_end} CT")
            status = STATUS_IDLE
            message = f"no capture running and none expected ({why})."
    elif not stale_streams:
        status = STATUS_OK
        message = ("capture alive and receiving: "
                   + ", ".join(f"{n.replace('databento_', '')}={o['cycles']}"
                               for n, o in observed.items()))
    elif not gopen:
        status = STATUS_QUIET
        message = (f"capture alive, nothing arriving — {venue_label} is closed, "
                   "which is the correct state. Not a fault.")
    elif capture_age_secs is not None and capture_age_secs < grace_secs:
        status = STATUS_STARTING
        message = (f"capture launched {capture_age_secs:.0f}s ago; still connecting "
                   f"(grace {grace_secs:.0f}s).")
    else:
        status = STATUS_STALE
        worst = max(observed[n]["quiet_secs"] for n in stale_streams)
        message = (f"capture process is ALIVE but not receiving: "
                   f"{', '.join(n.replace('databento_', '') for n in stale_streams)} "
                   f"has not advanced in {worst / 60:.0f} min with {venue_label} "
                   f"open. A live pid is not a live feed.")

    since = prev.get("since_utc") if prev.get("status") == status else None
    last_ok = now_iso if status == STATUS_OK else prev.get("last_ok_utc")
    restarts_day = prev.get("restarts_day")
    restarts = int(prev.get("restarts") or 0) if restarts_day == day_iso else 0

    return CaptureHealth(
        status=status,
        message=message,
        checked_at=now_iso,
        day=day_iso,
        pids=sorted(pids),
        capture_age_secs=(round(capture_age_secs, 1)
                          if capture_age_secs is not None else None),
        in_window=inwin,
        globex_open=gopen,
        expected=expected,
        streams=observed,
        stale_streams=stale_streams,
        since_utc=since or now_iso,
        last_ok_utc=last_ok,
        restarts=restarts,
        restarts_day=day_iso,
    )
