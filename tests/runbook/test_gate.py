"""Datastream health gate tests. [co-i10h, st-jc8p]

All against the pure ``evaluate`` function with a fixed ``now`` so they are
deterministic.

Fixtures are anchored to a CT CLOCK TIME on the data-day, not to an age relative
to ``now`` [st-jc8p]. That is the whole point of the rule change: the gate asks
whether a stream covered the session it claims to describe, so what matters is
when it stopped relative to that day's close — not how long ago that was in
wall-clock terms. An age-anchored fixture cannot express "healthy Friday read on
Monday morning", which is the case that used to fail.
"""
from datetime import date, datetime, timezone

from runbook.datastream import gate
from strader.market_calendar import CENTRAL

#: A Monday.
DATA_DAY = date(2026, 6, 29)
#: The Tuesday morning after it — the gate's normal running condition.
NOW = datetime(2026, 6, 30, 12, 0, 0, tzinfo=timezone.utc)


def _stamp(hhmm: str, day: date = DATA_DAY) -> str:
    """A last_pull_utc for `hhmm` US/Central on `day`, in the writer's format."""
    h, m = (int(x) for x in hhmm.split(":"))
    return (datetime(day.year, day.month, day.day, h, m, tzinfo=CENTRAL)
            .astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def _manifest(es_end="15:05", opra_end="15:05", es_cycles=124928,
              opra_cycles=435985, es_errors=None, opra_errors=None,
              day: date = DATA_DAY):
    """A day's manifest. Defaults are a healthy session: live capture stops at
    15:05 CT, five minutes past the 15:00 cash close."""
    return {
        "date": day.isoformat(),
        "streams": {
            "databento_glbx_es": {
                "cycles": es_cycles,
                "errors": es_errors or [],
                "last_pull_utc": _stamp(es_end, day),
            },
            "databento_opra": {
                "cycles": opra_cycles,
                "errors": opra_errors or [],
                "last_pull_utc": _stamp(opra_end, day),
            },
        },
    }


def test_healthy_manifest_passes():
    res = gate.evaluate(_manifest(), now=NOW)
    assert res.ok, res.reasons
    assert res.checked["databento_glbx_es"]["present"] is True


def test_missing_stream_fails():
    m = _manifest()
    del m["streams"]["databento_glbx_es"]
    res = gate.evaluate(m, now=NOW)
    assert not res.ok
    assert any("databento_glbx_es" in r and "missing" in r for r in res.reasons)


def test_missing_opra_no_longer_fails():
    """Steve halted the daily OPRA import 2026-08-07; it is ad hoc now (st-7av4).

    A gate that requires a stream nobody collects fails every morning, and a
    gate that always fails gets bypassed. Absence of OPRA is a fact about the
    collection policy, not a health failure — the measurement scripts that
    actually read the OPRA tape own their own missing-file errors.
    """
    m = _manifest()
    del m["streams"]["databento_opra"]
    res = gate.evaluate(m, now=NOW)
    assert res.ok, res.reasons


def test_zero_cycles_fails():
    res = gate.evaluate(_manifest(es_cycles=0), now=NOW)
    assert not res.ok
    assert any("no cycles" in r for r in res.reasons)


def test_errors_present_fails():
    res = gate.evaluate(_manifest(es_errors=["429 from gexbot"]), now=NOW)
    assert not res.ok
    assert any("error" in r for r in res.reasons)


def test_a_capture_that_died_mid_session_fails():
    """The failure the gate exists to catch: ES stopped at 10:00 CT and the day
    has a five-hour hole. Wall-clock age would call this the FRESHEST case."""
    res = gate.evaluate(_manifest(es_end="10:00"), now=NOW)
    assert not res.ok
    assert any("stopped before" in r and "hole" in r for r in res.reasons)
    assert res.checked["databento_glbx_es"]["covers_day"] is False


def test_no_streams_object_fails():
    res = gate.evaluate({"date": "2026-06-29"}, now=NOW)
    assert not res.ok


def test_z_suffix_timestamp_parses():
    m = _manifest()
    # Confirm the Z-suffixed stamp the manifest writer uses round-trips.
    assert m["streams"]["databento_glbx_es"]["last_pull_utc"].endswith("Z")
    res = gate.evaluate(m, now=NOW)
    assert res.ok, res.reasons


def test_check_reads_manifest_for_the_resolved_gate_day(tmp_path, monkeypatch):
    """check(day=X) inspects the corpus manifest for exactly day X — the day
    run.py resolves via most_recent_session_day. This ties the shared day
    resolution to the file the gate actually reads: pointing it at the completed
    session's manifest (not the empty plan-day dir) is the whole point of
    Decision A. [co-i10h]
    """
    import json
    from datetime import date

    import market.corpus.paths as paths

    gate_day = date(2026, 6, 29)  # most-recent-completed session as of NOW
    monkeypatch.setattr(paths, "CORPUS_ROOT", tmp_path)

    day_dir = tmp_path / gate_day.isoformat()
    day_dir.mkdir()
    (day_dir / "manifest.json").write_text(json.dumps(_manifest()))

    # Reads tmp_path/2026-06-29/manifest.json via the corpus path convention.
    res = gate.check(day=gate_day, now=NOW)
    assert res.ok, res.reasons

    # A different day has no manifest dir — the gate fails closed, not silently.
    missing = gate.check(day=date(2026, 7, 1), now=NOW)
    assert not missing.ok
    assert any("not found" in r for r in missing.reasons)


# --- coverage, not recency [st-jc8p] ----------------------------------------
# The gate used to ask "was this written recently". For a stream filled by live
# capture, last_pull_utc is the SESSION END and nothing touches it again, so
# Friday close to Monday morning is ~64h against a 36h ceiling and the check
# failed every Monday by construction. On 2026-08-10 it took down both the 06:30
# corpus job and the 08:15 Mancini pre-open while 2026-08-07's tape was complete:
# 377,721 ES ticks, clean "0 reconnect(s)" close.

FRIDAY = date(2026, 8, 7)
MONDAY_0715 = datetime(2026, 8, 10, 12, 15, 0, tzinfo=timezone.utc)  # 07:15 CT


def test_the_monday_regression_a_complete_friday_passes_on_monday():
    """THE bug. 64 hours old, and correct — the day is fully covered."""
    m = _manifest(day=FRIDAY, es_end="15:05", opra_end="15:05")
    res = gate.evaluate(m, now=MONDAY_0715)
    assert res.ok, res.reasons
    assert res.checked["databento_glbx_es"]["age_hours"] > 36
    assert res.checked["databento_glbx_es"]["covers_day"] is True


def test_a_holed_friday_still_fails_on_monday():
    """The rule must not become 'weekends are always fine'."""
    m = _manifest(day=FRIDAY, es_end="10:00")
    res = gate.evaluate(m, now=MONDAY_0715)
    assert not res.ok
    assert any("stopped before" in r for r in res.reasons)


def test_the_verdict_does_not_change_with_the_passage_of_time():
    """Same manifest, judged a day apart, must give the same answer. Under the
    old rule the second call flipped to failing for no reason but the clock."""
    m = _manifest(day=FRIDAY)
    soon = gate.evaluate(m, now=datetime(2026, 8, 7, 21, 0, tzinfo=timezone.utc))
    later = gate.evaluate(m, now=datetime(2026, 9, 30, 21, 0, tzinfo=timezone.utc))
    assert soon.ok and later.ok


# --- early closes ------------------------------------------------------------

BLACK_FRIDAY = date(2026, 11, 27)   # 12:00 CT close


def test_an_early_close_day_is_judged_against_noon():
    """A 12:05 stop covers a 12:00 close. Judged against 15:00 it would look
    like a three-hour hole every half session."""
    res = gate.evaluate(_manifest(day=BLACK_FRIDAY, es_end="12:05",
                                  opra_end="12:05"), now=NOW)
    assert res.ok, res.reasons


def test_an_early_close_day_still_catches_a_real_hole():
    res = gate.evaluate(_manifest(day=BLACK_FRIDAY, es_end="10:00"), now=NOW)
    assert not res.ok
    assert any("12:00 CT close" in r for r in res.reasons)


# --- the slack window --------------------------------------------------------

def test_a_stop_just_inside_the_slack_passes():
    """14:55 is five minutes early — a final commit landing short, not a hole."""
    res = gate.evaluate(_manifest(es_end="14:55"), now=NOW)
    assert res.ok, res.reasons


def test_a_stop_outside_the_slack_fails():
    res = gate.evaluate(_manifest(es_end="14:35"), now=NOW)
    assert not res.ok


# --- recovered reconnects [st-mmh9] ------------------------------------------
# On 2026-08-12 the gate halted the morning Mancini parse over a single
# "reconnect #1: ... (possible gap)" entry on a day with 267k cycles and a last
# write past the close. A recovered reconnect bounds its possible gap at the
# heartbeat timeout (seconds), so failing a verifiably covered day over one
# asks the wrong question — and a gate that fails on immaterial grounds trains
# its operator to bypass it. Leniency is narrow: reconnect-shaped entries only,
# at most MAX_RECOVERED_RECONNECTS of them, and only when the day is covered.

RECONNECT = ("reconnect #1: BentoError: Gateway timeout: 40 second(s) "
             "since last message (possible gap)")


def test_a_recovered_reconnect_on_a_covered_day_passes():
    """The 2026-08-12 case: one heartbeat lapse, full coverage — not a hole."""
    res = gate.evaluate(_manifest(es_errors=[RECONNECT]), now=NOW)
    assert res.ok, res.reasons
    assert res.checked["databento_glbx_es"]["recovered_reconnects"] == 1


def test_a_reconnect_on_an_uncovered_day_still_fails():
    """A feed that reconnected and then died mid-session gets no leniency."""
    res = gate.evaluate(_manifest(es_end="10:00", es_errors=[RECONNECT]),
                        now=NOW)
    assert not res.ok
    assert any("error" in r for r in res.reasons)


def test_a_non_reconnect_error_stays_fatal_even_when_covered():
    res = gate.evaluate(_manifest(es_errors=["disk full: write failed"]),
                        now=NOW)
    assert not res.ok


def test_a_mixed_error_list_stays_fatal():
    """One real error among the reconnects must not ride through on them."""
    res = gate.evaluate(_manifest(es_errors=[RECONNECT, "disk full"]), now=NOW)
    assert not res.ok


def test_a_flapping_feed_on_a_covered_day_passes_with_a_warning_naming_the_count():
    """Revised 2026-09-04 (co-8b60y). More reconnects than the ceiling used to
    be fatal; a 42-hour outage then left a fully backfilled day carrying 6,466
    notes per stream and reading UNHEALTHY forever, halting the morning chain
    on data that was present. The count is now a warning the operator reads,
    not a verdict on the tape."""
    errs = [f"reconnect #{i}: BentoError: Gateway timeout: 40 second(s) "
            f"since last message (possible gap)" for i in range(1, 5)]
    assert len(errs) > gate.MAX_RECOVERED_RECONNECTS
    res = gate.evaluate(_manifest(es_errors=errs), now=NOW)
    assert res.ok, res.reasons
    assert res.degraded and res.status == "DEGRADED"
    assert res.checked["databento_glbx_es"]["recovered_reconnects"] == 4
    assert any("reconnected 4 times" in w for w in res.warnings), res.warnings


def test_the_2026_09_03_manifest_shape_passes_once_backfilled():
    """The measured shape: 5,544 reconnect lines and 922 give-up lines per
    stream, then a batch pull that covers the day. Both line shapes are the
    transport talking; neither is a hole in a covered tape."""
    errs = [f"reconnect #{i % 7 + 1}: BentoError: Connection to glbx-mdp3.lsg.databento.com:13000 "
            f"timed out after 10.0 second(s). (possible gap)" for i in range(5544)]
    errs += ["giving up after 6 reconnects"] * 922
    assert len(errs) == 6466
    res = gate.evaluate(_manifest(es_errors=errs, es_cycles=323929), now=NOW)
    assert res.ok, res.reasons[:2]
    assert res.checked["databento_glbx_es"]["recovered_reconnects"] == 6466
    assert len(res.warnings) == 1 and "6466" in res.warnings[0]


def test_the_give_up_line_alone_is_reconnect_shaped():
    assert gate._is_reconnect_error("giving up after 6 reconnects")
    assert gate._is_reconnect_error("reconnect #3: BentoError: x (possible gap)")
    assert not gate._is_reconnect_error("disk full: write failed")
    assert not gate._is_reconnect_error(None)


def test_a_flapping_feed_on_an_uncovered_day_still_fails():
    """Leniency is about coverage, never about the count: a feed that flapped
    and then died before the close still has a hole in it."""
    errs = [f"reconnect #{i}: BentoError: Gateway timeout (possible gap)" for i in range(1, 9)]
    res = gate.evaluate(_manifest(es_end="10:00", es_errors=errs), now=NOW)
    assert not res.ok


def test_at_or_below_the_ceiling_there_is_no_warning():
    errs = [f"reconnect #{i}: BentoError: Gateway timeout (possible gap)" for i in range(1, 4)]
    assert len(errs) == gate.MAX_RECOVERED_RECONNECTS
    res = gate.evaluate(_manifest(es_errors=errs), now=NOW)
    assert res.ok and not res.warnings and res.status == "HEALTHY"


def test_resolved_errors_are_reported_and_do_not_count_against_the_day():
    m = _manifest()
    m["streams"]["databento_glbx_es"]["errors_resolved"] = {
        "count": 6466, "resolved_utc": "2026-06-30T11:40:00Z", "sample": ["reconnect #1: x"]}
    res = gate.evaluate(m, now=NOW)
    assert res.ok and res.status == "HEALTHY"
    assert res.checked["databento_glbx_es"]["errors_resolved"] == 6466


def test_a_reconnect_with_no_date_stays_fatal():
    """No data-day means coverage is unverifiable, so no leniency applies."""
    m = _manifest(es_errors=[RECONNECT])
    del m["date"]
    res = gate.evaluate(m, now=NOW, max_age_hours=36)
    assert not res.ok


# --- fallback when the manifest cannot say which day it is -------------------

def test_a_manifest_with_no_date_falls_back_to_wall_clock_age():
    m = _manifest()
    del m["date"]
    res = gate.evaluate(m, now=datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc),
                        max_age_hours=36)
    assert not res.ok
    assert any("no 'date'" in r for r in res.reasons)
    assert res.checked["databento_glbx_es"]["covers_day"] is None


def test_a_manifest_with_an_unparseable_date_falls_back_too():
    m = _manifest()
    m["date"] = "last tuesday"
    res = gate.evaluate(m, now=NOW, max_age_hours=36)
    assert res.ok, res.reasons          # 20h old, inside the fallback ceiling


# --- degraded: a configured non-required stream ran and got nothing ----------
# [co-03ojd.7 J-F3] Measured 2026-08-07 → 08-15: databento_opra recorded
# cycles=0 with a 403 on seven consecutive runs while the verdict said HEALTHY.

OPRA_403 = ("403 license_not_found_unauthorized: a live data license is required "
            "to access OPRA.PILLAR data after 2026-08-07T13:30:00Z")


def test_configured_stream_with_no_cycles_and_errors_degrades_but_passes():
    m = _manifest(opra_cycles=0, opra_errors=[OPRA_403])
    res = gate.evaluate(m, now=NOW)
    assert res.ok, res.reasons                      # required tape is fine
    assert res.degraded
    assert res.status == "DEGRADED"
    assert len(res.warnings) == 1
    assert "databento_opra" in res.warnings[0]
    assert "cycles=0" in res.warnings[0]
    assert "403" in res.warnings[0]
    assert res.checked["databento_opra"]["empty_with_errors"] is True


def test_healthy_manifest_is_not_degraded():
    res = gate.evaluate(_manifest(), now=NOW)
    assert res.ok and not res.degraded and res.warnings == []
    assert res.status == "HEALTHY"


def test_empty_stream_without_errors_is_not_flagged():
    """cycles=0 and no errors is 'nothing arrived', not 'ran and failed' —
    the rule is deliberately narrow so it cannot cry on a quiet stream."""
    res = gate.evaluate(_manifest(opra_cycles=0, opra_errors=[]), now=NOW)
    assert res.ok and not res.degraded


def test_required_stream_failure_is_unhealthy_not_degraded():
    """A dead REQUIRED stream is still the fatal path; degraded never masks it."""
    m = _manifest(es_cycles=0, es_errors=["boom"], opra_cycles=0, opra_errors=[OPRA_403])
    res = gate.evaluate(m, now=NOW)
    assert not res.ok
    assert res.status == "UNHEALTHY"
    assert not res.degraded
    assert res.warnings                              # still reported alongside


def test_degraded_warning_truncates_a_long_error():
    m = _manifest(opra_cycles=0, opra_errors=["x" * 500])
    res = gate.evaluate(m, now=NOW)
    assert res.degraded
    assert len(res.warnings[0]) < 400
    assert res.warnings[0].endswith("...")
