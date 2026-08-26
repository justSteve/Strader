"""In-session surfacing of bridge memos addressed to Strader. [st-92m7]

The bug this guards: on 2026-08-25 a Desk ruling sat unread for 9h35m, not
because it was mis-routed but because Strader's only surfacing ran at tap-in.
So the tests that matter are about the SESSION-SCALE behaviour — a memo that
arrives after start-up is reported, a quiet bridge says nothing, and an absent
Windows mount is silence rather than a crash.
"""
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools import bridge_inbox as bi


HEADER = ("# {title}\n\n"
          "**class:** {klass} · **from:** {sender} · **for:** COO, Strader\n\n"
          "body\n")


@pytest.fixture(autouse=True)
def _isolated_seen_ledger(tmp_path, monkeypatch):
    """Never let a test append to the real /var/moo ledger."""
    monkeypatch.setattr(bi, "SEEN_LEDGER", tmp_path / "seen.jsonl")


@pytest.fixture
def bridge(tmp_path):
    (tmp_path / "Strader" / "inbox").mkdir(parents=True)
    return tmp_path


def drop(bridge, name, sender="Desk", klass="ruling", age_s=0):
    p = bridge / "Strader" / "inbox" / name
    p.write_text(HEADER.format(title=name, klass=klass, sender=sender),
                 encoding="utf-8")
    if age_s:
        old = time.time() - age_s
        import os
        os.utime(p, (old, old))
    return p


# ── reading ────────────────────────────────────────────────────────────────

def test_an_empty_inbox_reports_nothing_and_exits_clean(bridge, capsys):
    assert bi.main(["--bridge", str(bridge)]) == 0
    assert "empty" in capsys.readouterr().out


def test_an_absent_mount_is_silence_not_a_crash(tmp_path):
    """The Windows host is often away. A start-up path must never die on it."""
    assert bi.scan(str(tmp_path / "no-such-bridge")) == []


def test_a_waiting_memo_is_reported_with_sender_class_and_recipients(bridge, capsys):
    drop(bridge, "20260826T012334__Desk__ruling-9.md", klass="ruling")
    assert bi.main(["--bridge", str(bridge)]) == 1
    out = capsys.readouterr().out
    assert "1 waiting for Strader" in out
    assert "Desk" in out and "ruling" in out
    assert "COO, Strader" in out


def test_exit_code_one_means_something_is_waiting(bridge):
    assert bi.main(["--bridge", str(bridge)]) == 0
    drop(bridge, "20260826T012334__Desk__x.md")
    assert bi.main(["--bridge", str(bridge)]) == 1


def test_the_oldest_memo_sorts_first(bridge, capsys):
    drop(bridge, "20260826T010000__Desk__new.md", age_s=60)
    drop(bridge, "20260826T000000__Desk__old.md", age_s=36000)
    bi.main(["--bridge", str(bridge)])
    out = capsys.readouterr().out
    assert out.index("old") < out.index("new")


def test_a_headerless_memo_still_surfaces(bridge, capsys):
    """Pre-2026-08 memos carry no header. A parser that refused them would
    silence exactly the backlog this tool exists to surface, so the filename
    convention is the fallback."""
    p = bridge / "Strader" / "inbox" / "20260819T054837__co__bar-339.md"
    p.write_text("# just a title\n\nbody\n", encoding="utf-8")
    assert bi.main(["--bridge", str(bridge)]) == 1
    out = capsys.readouterr().out
    assert "co" in out and "bar-339" in out


def test_json_output_is_machine_readable(bridge, capsys):
    drop(bridge, "20260826T012334__Desk__ruling-9.md")
    bi.main(["--bridge", str(bridge), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    assert payload["memos"][0]["sender"] == "Desk"


# ── the ledger join ────────────────────────────────────────────────────────

def test_the_stem_is_the_join_key_to_the_ledger(bridge, monkeypatch, tmp_path):
    """A MEMO/ACK row's REF column carries the memo filename without `.md`,
    so a memo already logged must not be re-logged."""
    ledger = tmp_path / "inbox.md"
    ledger.write_text("| x | Strader | ACK | st-1 | 20260826T012334__Desk__ruling-9 | - | y |\n")
    monkeypatch.setattr(bi, "LEDGER", ledger)
    drop(bridge, "20260826T012334__Desk__ruling-9.md")
    drop(bridge, "20260826T014102__Desk__ruling-10.md")
    memos = bi.scan(str(bridge))
    assert {m.stem: m.in_ledger for m in memos} == {
        "20260826T012334__Desk__ruling-9": True,
        "20260826T014102__Desk__ruling-10": False,
    }
    rows = bi.ledger_rows(memos, "2026-08-26 02:00 CT")
    assert len(rows) == 1 and "ruling-10" in rows[0]


def test_a_ledger_row_matches_the_format_contract(bridge, monkeypatch, tmp_path):
    ledger = tmp_path / "inbox.md"
    ledger.write_text("")
    monkeypatch.setattr(bi, "LEDGER", ledger)
    drop(bridge, "20260826T012334__Desk__ruling-9.md")
    rows = bi.ledger_rows(bi.scan(str(bridge)), "2026-08-26 02:00 CT")
    fields = [f.strip() for f in rows[0].strip("|").split("|")]
    assert len(fields) == 7, "WHEN|ACTOR|KIND|BEAD|REF|PATHS|WHY"
    assert fields[1] == "Strader" and fields[2] == "MEMO"
    assert fields[3] == "st-92m7" and fields[4] == "20260826T012334__Desk__ruling-9"
    assert "NOTE" not in fields[2], "retired kind, st-xa5p"


def test_appending_no_rows_leaves_the_ledger_untouched(monkeypatch, tmp_path):
    ledger = tmp_path / "inbox.md"
    ledger.write_text("original\n")
    monkeypatch.setattr(bi, "LEDGER", ledger)
    assert bi.append_rows([]) == 0
    assert ledger.read_text() == "original\n"


def test_the_ledger_timestamp_is_central_never_utc(monkeypatch):
    """Every human-facing stamp renders CT. A UTC row in this column reads as
    a five-hour-old memo that just arrived."""
    stamp = bi._now_ct()
    assert stamp.endswith(" CT")
    import datetime
    datetime.datetime.strptime(stamp[:-3].strip(), "%Y-%m-%d %H:%M")


# ── the watch: every printed line is a model wake ──────────────────────────

def test_the_watch_is_seeded_and_does_not_replay_the_backlog(bridge, capsys):
    """Arming mid-session must not re-report what tap-in already showed."""
    drop(bridge, "20260826T010000__Desk__already-here.md")
    bi.watch(interval=1, bridge=str(bridge), once=True)
    assert capsys.readouterr().out == ""


def test_a_quiet_bridge_wakes_nobody(bridge, capsys):
    bi.watch(interval=1, bridge=str(bridge), once=True)
    assert capsys.readouterr().out == ""


def test_an_arrival_prints_exactly_one_wake(bridge, capsys, monkeypatch):
    """The whole point: a memo landing DURING a session is surfaced without
    waiting for the next tap-in."""
    real_sleep = time.sleep

    def sleep_then_deliver(_):
        drop(bridge, "20260826T013442__Desk__intent.md", klass="intent")
        real_sleep(0)

    monkeypatch.setattr(bi.time, "sleep", sleep_then_deliver)
    bi.watch(interval=1, bridge=str(bridge), once=True)
    out = capsys.readouterr().out
    assert out.count("[BRIDGE]") == 1
    assert "intent" in out and "Desk" in out


def test_only_strader_inbox_is_read(bridge, capsys):
    """Deliberate scope. The superseded fix proposed scanning peer OUTBOX and
    _archive folders for a `for:` naming Strader — that addresses a failure
    that did not happen and reads other agents' mail to do it."""
    (bridge / "Desk" / "inbox").mkdir(parents=True)
    (bridge / "Desk" / "inbox" / "20260826T012334__Desk__for-strader.md").write_text(
        HEADER.format(title="t", klass="ruling", sender="Desk"), encoding="utf-8")
    (bridge / "Strader" / "_archive").mkdir(parents=True)
    (bridge / "Strader" / "_archive" / "20260825T143000__Desk__done.md").write_text(
        HEADER.format(title="t", klass="ruling", sender="Desk"), encoding="utf-8")
    assert bi.scan(str(bridge)) == []


# ── arrival: the durable mark, and its fallbacks [st-w87l] ─────────────────

def test_first_sighting_falls_back_to_mtime_and_records_it(bridge):
    """Nothing has seen it yet, so mtime is the floor — and the row written
    says so, because a claim's provenance travels with it."""
    drop(bridge, "20260826T012334__Desk__x.md", age_s=600)
    memos = bi.scan(str(bridge))
    assert memos[0].first_seen_source == "mtime"
    rows = [json.loads(l) for l in bi.SEEN_LEDGER.read_text().splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0]["stem"] == "20260826T012334__Desk__x"
    assert rows[0]["observed_source"] == "mtime"


def test_the_second_read_prefers_the_ledger(bridge):
    drop(bridge, "20260826T012334__Desk__x.md")
    assert bi.scan(str(bridge))[0].first_seen_source == "mtime"
    assert bi.scan(str(bridge))[0].first_seen_source == "ledger"


def test_the_ledger_survives_an_mtime_rewrite(bridge):
    """THE POINT OF THE BEAD. On 2026-08-25 the Drive sync re-delivered four
    edited-in-place memos and overwrote their arrival mtimes. Once this
    observer has recorded a sighting, a later rewrite cannot move it."""
    p = drop(bridge, "20260826T012334__Desk__x.md", age_s=7200)
    first = bi.scan(str(bridge))[0]
    assert first.first_seen_source == "mtime" and first.age_s >= 7000

    now = time.time()                      # the re-delivery
    os.utime(p, (now, now))

    after = bi.scan(str(bridge))[0]
    assert after.first_seen_source == "ledger"
    assert after.age_s >= 7000, "a rewrite must not make an old memo look new"
    assert abs(after.first_seen_ts - first.first_seen_ts) < 1


def test_first_write_wins_when_the_ledger_has_duplicates(bridge):
    """Append-only means a later row is history, not an update."""
    stem = "20260826T012334__Desk__x"
    bi.SEEN_LEDGER.write_text(
        json.dumps({"ts": "2026-08-26T01:00:00+00:00", "stem": stem}) + "\n"
        + json.dumps({"ts": "2026-08-26T09:00:00+00:00", "stem": stem}) + "\n")
    assert bi._ledger_first_seen()[stem] == \
        datetime.fromisoformat("2026-08-26T01:00:00+00:00").timestamp()


def test_a_torn_ledger_line_does_not_lose_the_rest(bridge):
    """An append-only file written by a poller can be torn by a crash
    mid-write. Losing every arrival mark because of one bad line would be the
    same class of loss this ledger exists to prevent."""
    bi.SEEN_LEDGER.write_text(
        json.dumps({"ts": "2026-08-26T01:00:00+00:00", "stem": "good-1"}) + "\n"
        + '{"ts": "2026-08-26T02:00:00+00:00", "stem": "tor\n'
        + "not json at all\n"
        + json.dumps({"stem": "no-ts"}) + "\n"
        + json.dumps({"ts": "nonsense", "stem": "bad-ts"}) + "\n"
        + json.dumps({"ts": "2026-08-26T03:00:00+00:00", "stem": "good-2"}) + "\n")
    seen = bi._ledger_first_seen()
    assert set(seen) == {"good-1", "good-2"}


def test_an_unwritable_ledger_does_not_break_the_poll(bridge, monkeypatch):
    """/var/moo can be absent or read-only. Bookkeeping must never be the
    reason a bridge poll dies — the poll is the safety mechanism."""
    monkeypatch.setattr(bi, "SEEN_LEDGER", bridge / "nope" / "x" / "seen.jsonl")
    monkeypatch.setattr(bi.Path, "mkdir",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("ro")))
    drop(bridge, "20260826T012334__Desk__x.md")
    memos = bi.scan(str(bridge))
    assert len(memos) == 1 and memos[0].first_seen_source == "mtime"


def test_git_author_date_supplies_send_time_not_arrival(bridge):
    """Ruling 12a: the bridge becomes a git repo. Git answers WHEN IT WAS SENT,
    which is the leg st-92m7 measures; arrival stays this observer's to record.
    Wired before the cutover so it needs no second pass."""
    import subprocess
    inbox = bridge / "Strader" / "inbox"
    p = drop(bridge, "20260826T012334__Desk__x.md")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "GIT_AUTHOR_DATE": "2026-08-26T01:00:00-05:00",
           "GIT_COMMITTER_DATE": "2026-08-26T01:00:00-05:00",
           "PATH": os.environ.get("PATH", ""), "HOME": str(bridge)}
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "commit", "-qm", "x"]):
        r = subprocess.run(cmd, cwd=bridge, env=env, capture_output=True)
        if r.returncode != 0:
            pytest.skip(f"git unavailable: {r.stderr[:120]}")
    now = time.time()
    os.utime(p, (now, now))                # checkout-time mtime, i.e. wrong

    memo = bi.read_memo(p, "", seen={})
    assert memo.sent_source == "git", "git author date is SEND time, not arrival"
    assert datetime.fromtimestamp(memo.sent_ts, timezone.utc).astimezone(
        timezone(timedelta(hours=-5))).hour == 1
    assert memo.first_seen_source == "mtime", "arrival is still ours to observe"


def test_the_report_marks_a_weaker_first_seen_source(bridge, capsys):
    """An mtime-sourced age is weaker evidence than a ledger-sourced one, and
    the difference has already changed a diagnosis once."""
    drop(bridge, "20260826T012334__Desk__x.md")
    bi.main(["--bridge", str(bridge)])
    assert "(mtime)" in capsys.readouterr().out
    bi.main(["--bridge", str(bridge)])
    assert "(mtime)" not in capsys.readouterr().out


# ── first-seen and sent are different quantities [st-w87l, COO's catch] ─────

def test_send_and_arrival_are_recorded_separately(bridge):
    """Collapsing them would answer the question we do not ask and lose the
    one we keep asking: st-92m7 is a SEND-to-read measurement."""
    drop(bridge, "20260826T012334__Desk__x.md", age_s=600)
    m = bi.scan(str(bridge))[0]
    assert m.first_seen_source == "mtime"
    assert m.sent_source == "stamp"
    assert m.sent_ts != m.first_seen_ts
    assert m.transit_s == int(m.first_seen_ts - m.sent_ts)


def test_the_filename_stamp_is_read_as_central():
    """Every human-facing stamp here is CT. Reading one as UTC would put a
    five-hour error straight into a transit figure."""
    p = Path("/x/20260826T013442__Desk__x.md")
    ts, src = bi.sent_at(p, "20260826T013442__Desk__x")
    assert src == "stamp"
    ct = datetime.fromtimestamp(ts, timezone.utc).astimezone(bi._CT)
    assert (ct.hour, ct.minute) == (1, 34)


def test_an_unparseable_name_yields_no_send_time_rather_than_a_guess(bridge):
    """`none` is a real answer. Substituting arrival for send would manufacture
    a transit of zero and look like perfect delivery."""
    p = bridge / "Strader" / "inbox" / "not-a-memo-name.md"
    p.write_text("# x\n", encoding="utf-8")
    ts, src = bi.sent_at(p, "not-a-memo-name")
    assert (ts, src) == (None, "none")
    assert bi.read_memo(p, "", seen={}).transit_s is None


def test_the_ledger_carries_send_time_beside_arrival(bridge):
    """After cutover a pull lands a backlog at one instant, so first-seen goes
    flat and send time is the only thing still separating the memos in it."""
    drop(bridge, "20260826T012334__Desk__x.md", age_s=600)
    bi.scan(str(bridge))
    row = json.loads(bi.SEEN_LEDGER.read_text().splitlines()[0])
    assert row["sent_source"] == "stamp"
    assert row["sent"] and row["sent"] != row["ts"]


def test_transit_is_reported_with_its_provenance(bridge, capsys):
    """A stamp-sourced transit inherits the stamp's uncertainty, so it may not
    appear without the label."""
    drop(bridge, "20260826T012334__Desk__x.md", age_s=7200)
    bi.main(["--bridge", str(bridge)])
    out = capsys.readouterr().out
    assert "transit" in out and "a claim" in out


# ── drained, broken and unreachable are three states [st-92m7, COO's catch] ──
#
# COO's git migration silently dropped seven empty directories, Strader/inbox
# among them, because git does not track them. A clone would have had no inbox
# and this tool would have said "empty" at exit 0. Its sentence: an empty inbox
# means drained, an absent one means broken. They were the same thing here
# always, not only at clone time.

def test_a_drained_inbox_says_the_directory_is_there(bridge, capsys):
    assert bi.main(["--bridge", str(bridge)]) == 0
    out = capsys.readouterr().out
    assert "drained" in out and "directory is there" in out


def test_a_missing_inbox_is_loud_and_non_zero(tmp_path, capsys):
    """THE CLONE CASE. The mount is present and our own inbox is not."""
    (tmp_path / "COO" / "inbox").mkdir(parents=True)     # a real bridge...
    assert bi.main(["--bridge", str(tmp_path)]) == 2     # ...missing ours
    # (tmp_path has no Strader/ — the `bridge` fixture is not used here)
    out = capsys.readouterr().out
    assert "[ALERT]" in out
    assert "BROKEN, not drained" in out


def test_an_unreachable_mount_is_normal_and_not_an_alert(capsys):
    """The Windows host is often away. That is not a fault and must not cry
    wolf, or the alert that matters gets filtered out with it."""
    assert bi.main(["--bridge", "/no/such/mount"]) == 0
    out = capsys.readouterr().out
    assert "[ALERT]" not in out and "normal" in out


def test_the_three_states_do_not_share_a_string(tmp_path, bridge):
    other = tmp_path / "other-bridge"          # `bridge` IS tmp_path
    (other / "COO" / "inbox").mkdir(parents=True)
    drained = bi.render([], *bi.channel_state(str(bridge)))
    missing = bi.render([], *bi.channel_state(str(other)))
    unreach = bi.render([], *bi.channel_state("/no/such/mount"))
    assert len({drained, missing, unreach}) == 3, "a state that reads like another is not a state"


def test_json_carries_the_state(bridge, capsys):
    bi.main(["--bridge", str(bridge), "--json"])
    assert json.loads(capsys.readouterr().out)["state"] == "empty"


def test_the_watch_announces_a_channel_that_breaks_mid_session(bridge, capsys, monkeypatch):
    """A watch silently watching a directory that no longer exists produces the
    same silence as a quiet channel. That silence is the failure."""
    inbox = bridge / "Strader" / "inbox"
    real_sleep = time.sleep

    def sleep_then_break(_):
        if inbox.exists():
            inbox.rmdir()
        real_sleep(0)

    monkeypatch.setattr(bi.time, "sleep", sleep_then_break)
    bi.watch(interval=1, bridge=str(bridge), once=True)
    out = capsys.readouterr().out
    assert "[ALERT]" in out and "missing" in out


def test_the_watch_does_not_cry_wolf_every_tick(bridge, capsys, monkeypatch):
    """Report the TRANSITION. An away host reported every tick is a wake
    generator, and a noisy alert is one that gets ignored."""
    (bridge / "Strader" / "inbox").rmdir()
    real_sleep = time.sleep
    monkeypatch.setattr(bi.time, "sleep", lambda _: real_sleep(0))
    seen = []
    for _ in range(3):
        bi.watch(interval=1, bridge=str(bridge), once=True)
        seen.append(capsys.readouterr().out)
    # Each call is a fresh watch, and a fresh watch arming on an already
    # broken channel MUST announce — saying nothing there is the failure.
    assert all(s.count("[BRIDGE]") == 1 for s in seen), seen
    assert all("[ALERT]" in s for s in seen)
