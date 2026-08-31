# GexBot WebSocket payload probe — operation

**`WebSocket Payload Probe` (`st-8qqw`)** · `scripts/gexbot_ws_probe.py`

## Why this exists

Everything in `docs/reports/2026-08-30-gexbot-websocket-and-the-state-move.md`
about this feed is **documentary** — read off the vendor's OpenAPI spec,
`AGENTS.md` and `websocket.md`. Verified 2026-08-30: `negotiate` appeared in no
other `.py` or `.sh` in this repo, the reference client
(`nfa-llc/quant-python-sockets`) was never cloned, and `data/` held no captured
frame. The brief's recommendation rested on the vendor's say-so.

This probe replaces that with observation, on three questions:

1. What does a frame weigh, compressed and decompressed?
2. What is the real cadence against the stated 1 Hz — and against the **62%** our
   REST poller captures (2026-08-27: 14,487 polls, median spacing 2.0 s across a
   ~23,470 s session)?
3. Is the payload decodable without the vendor's client? They publish no `.proto`.

## The deadline is Friday 2026-09-04, not 09-06

`/negotiate` is Quant-only and lapses with `/hist` after **2026-09-06**. But the
feed publishes **only during NYSE cash hours**, and 09-05/09-06 are Saturday and
Sunday. So the usable window is five sessions:

> **Mon 2026-08-31 · Tue 09-01 · Wed 09-02 · Thu 09-03 · Fri 09-04**

**Friday 2026-09-04 is the last session this can ever run.** `/hist` carries no
such restriction, which is why `st-qcj3`'s hand sweep can and must still fall on
that weekend — do not conflate the two deadlines.

Unlike the GEX archive there is no backfill argument here: nothing was ever
captured, so after the lapse the feed is permanently unknowable to us.

## Run it

```bash
cd /root/projects/Strader
.venv/bin/python3 scripts/gexbot_ws_probe.py                     # 120s, SPX_state_gamma_zero
.venv/bin/python3 scripts/gexbot_ws_probe.py --duration 600      # longer sample
.venv/bin/python3 scripts/gexbot_ws_probe.py --group SPX_classic_gex_full
.venv/bin/python3 scripts/gexbot_ws_probe.py --force             # outside RTH, deliberately
```

Default group is `SPX_state_gamma_zero` — the front-expiry gamma ladder, chosen
because the 08-30 brief showed we cannot resolve it at our 60 s state cadence
(`major_long_gamma` differed from its previous sample 50% of the time). It is the
series where a push feed has the most to prove.

Ctrl-C produces a report over whatever was captured. An interrupted probe inside
a closing window is worth more than nothing.

### Exit codes

| | |
|---|---|
| 0 | captured and analysed |
| 2 | preflight refusal — outside RTH without `--force`, or no key |
| 3 | negotiate failed. **401 = the key. 403 = the tier or the group cap** |
| 4 | connected, no frames in the window |
| 5 | network / transport failure |

**After 2026-09-06 a `403` on exit 3 is the correct answer, not a fault** — it is
the entitlement drop, observed.

## Artifacts

`data/probes/gexbot-ws/<run-id>/` — the whole `data/` tree is gitignored
(`.gitignore:14`), so promote a report worth keeping into `docs/reports/` by hand.

| file | |
|---|---|
| `negotiate.json` | the response, **access tokens redacted** |
| `frames.bin` | length-prefixed raw frames, exactly as they arrived |
| `frames.jsonl` | index: seq, wall CT, monotonic offset, opcode, bytes |
| `analysis.json` | the computed answer to the three questions |
| `report.md` | the readable version |
| `probe.log` | the run log |

## Safety

- **Read-only against the vendor.** One `POST /negotiate`, one socket, one group.
- **Tokens never reach disk.** `redact()` runs on every path out, applied at the
  boundary rather than at each write site so a new print cannot leak one by
  omission. Pinned by four tests.
- **One group, not 150.** The cap is 150 on a standard Quant key; this asks for one.
- **A successful POST negotiate closes existing connections on the same slot** —
  the vendor's warning. It does *not* affect the REST collectors
  (`corpus_poll_gexbot.py`, `corpus_poll_gexbot_orderflow_1s.py`), which do not use
  the socket. Two probes at once would fight each other; don't.
- **No subprotocol is requested.** The POST flow auto-joins server-side and the
  vendor says not to call client-side `joinGroup`, so simple-client mode is correct
  and frames arrive as sent. Asking for `json.webpubsub.azure.v1` would wrap every
  payload in an envelope and defeat the point.

## Preflight, run 2026-08-30 15:04 CT (`--force`, outside RTH)

Five documentary claims already converted to observed, so a live session is spent
on the payload rather than on debugging auth:

- **`POST /v2/negotiate` → 200 OK.** The key works and the flow is as specified.
- **All six hubs authorized** — `classic`, `state_gex`, `state_greeks`,
  `state_greeks_zero`, `state_greeks_one`, `orderflow`. Quant is live right now.
- **Hub routing works.** `SPX_state_gamma_zero` → `state_greeks_zero`.
- **The socket opens.** Azure Web PubSub accepts a raw connection, no subprotocol.
- **Zero frames in 25 s outside RTH** — exactly as `websocket.md` states. The RTH
  restriction is now measured, not quoted.

Artifacts: `data/probes/gexbot-ws/20260830T150431/`.

## Day 1 is armed (2026-08-31)

A transient one-shot timer fires the first capture at the open, so day 1 of five
is banked whether or not anyone is at the screen:

```bash
systemctl list-timers strader-ws-probe-day1 --no-pager   # Mon 2026-08-31 08:32 CDT, 300s capture
systemctl stop strader-ws-probe-day1.timer               # cancel
journalctl -u strader-ws-probe-day1 --no-pager           # after it runs
```

Log tees to `/var/moo/logs/gexbot-ws-probe-day1.log`; artifacts land in the usual
run directory.

**Do not fire a manual probe while it is running** — a successful POST negotiate
closes existing connections on the same slot, so two probes fight. It starts
08:32 and is done by roughly 08:37; after that the socket is free.

It is transient (`systemd-run`), not a catalogued standing timer, and it fires
once. **Clean it up when the window closes** — `systemctl stop
strader-ws-probe-day1.timer` — so it does not linger as an orphan unit that no
`SCHEDULE.md` entry explains.

## Tests

```bash
.venv/bin/python3 -m pytest tests/scripts/test_gexbot_ws_probe.py -q
```

37 tests over the pure functions — redaction, the `gexbot_custom_` prefix guard,
hub resolution (including `ES_SPX_orderflow_orderflow`, where naive `split("_")`
index arithmetic picks the wrong hub), the RTH window at both boundaries and across
timezones, the protobuf wire walker, and the spacing statistics.

The socket half cannot be tested without a live Quant key inside RTH, and that
lapses 09-06 — so what can be pinned is pinned, because afterwards a regression
here could never be caught by running it.

## What it deliberately does not do

- Wire a collector. Capture-for-keeps is a **second decision for Steve**, and only
  worth raising if question 3 comes back cheap.
- Decode field semantics. The walker recovers field numbers and wire types;
  protobuf carries no names. Mapping them to `spot`, `zero_gamma` and the rest
  needs the vendor's `.proto` or a correlation study against a simultaneous REST
  poll.
- Touch explicit-expiry groups. They publish at ~5 s, are never persisted to
  `/hist`, and for SPX 0DTE the `zero`/`one` ordinals already cover the front two
  expiries.
