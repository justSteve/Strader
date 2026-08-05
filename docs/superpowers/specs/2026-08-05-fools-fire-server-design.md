# Fire Server — Design of Record

**Epic:** Fools Remote Arm (st-863b) · **Ruling:** Steve approved 2026-08-05
**Phase 1 delivered:** st-1o47 · **Phase 2 (order client):** st-bxls, blocked on Steve's key

## The covenant

The schwab-py fork is hobbled (`lib/schwab-py` ce2ccd9, Steve, 2026-05-20):
no agent-reachable code in this enterprise can transmit, preview, cancel, or
even enumerate orders or accounts. **That stays true forever.** This design
adds exactly one order-capable component, and puts it where no agent can
reach it:

| Layer | Can do | Cannot do |
|---|---|---|
| Agents / studies / detector | stage a ticket by writing `data/exec/fire-ticket.json` | call the fire server, import the order client, transmit anything |
| Fire server (`scripts/fire_server.py`) | render the staged ticket to Steve's tailnet devices; enforce rails; journal | stage tickets; act without Steve's tap |
| Order client (Phase 2, st-bxls) | 4 endpoints: account hash, preview, place, order status | exist without `~/.schwab_fire_key`, which only Steve creates |

Steve alone fires. The phone changes where his finger is, not who decides.

## Phase 1 (live now, dry-run)

- **Binding**: resolved Tailscale address only (`100.108.58.5:8777`), loud
  failure if tailscaled is down. Never 0.0.0.0, never LAN, never public.
- **Flow**: staged ticket renders with its evidence → **ARM** → single-use
  nonce (60 s) → **FIRE** → Phase 1 journals the intent and reports
  *"DRY RUN COMPLETE — nothing transmitted."*
- **Rails** (server-side, none bypassable from the form): qty hard cap
  (`QTY_CAP = 1`), stale-ticket refusal (staged > 10 min), kill-switch file
  (`data/exec/FIRE_DISABLED`), FIRE re-validates everything ARM checked,
  append-only journal `data/exec/fire-journal-<day>.jsonl`.
- **Tests**: 9 rail tests (`tests/scripts/test_fire_server.py`), full suite
  690 green.

## Phase 2 gate (before any real transmission)

1. Steve creates `~/.schwab_fire_key` (`touch` — agent never creates it).
2. Entitlement probe: read-only accountNumbers call verifies the app
   registration carries the trading product.
3. Preview-only milestone: FIRE runs `preview_order` and renders Schwab's
   own preview — still transmitting nothing — until Steve rules the preview
   output trustworthy.
4. Paper/1-contract pilot per the st-1tgh verdict.

## Journal scoring

The fire journal is scoreable the same way the meter journal is: every
armed/fired/refused event carries the ticket and timestamps. Nothing here is
"working" until its journal has been read back against outcomes — the audit's
artifact-verification rule applies to this build as to everything else.
