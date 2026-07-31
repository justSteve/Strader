#!/usr/bin/env python3
"""Risk-state reset — the Playbook hard limits expressed as code. [st-958]

Runbook #8 (COO design co-59ky): pure Python, runs at day-start. The morning
reset snapshots config/risk.yaml into data/risk/<day>.json; the day is then
traded against that snapshot. Steve's fast-cut edge as an enforced artifact:
when the daily loss limit is hit the state flips to HALTED, and every surface
that reads it says stop.

There is no broker feed here by design — the account API is physically removed
from the lib (hobbled-readonly). Fills are recorded by hand, which makes this
a discipline surface, not a guardian angel: it is only as current as the last
`record` call. That is the accepted v1 trade-off.

Usage:
    .venv/bin/python -m runbook.risk_state reset            # idempotent day-start
    .venv/bin/python -m runbook.risk_state status
    .venv/bin/python -m runbook.risk_state record --strat butterflies --pnl -45 --risk 130
    .venv/bin/python -m runbook.risk_state record --strat orb --pnl 80 --close
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from market.corpus.paths import central_date  # noqa: E402

CONFIG_PATH = REPO_ROOT / "config" / "risk.yaml"
RISK_ROOT = REPO_ROOT / "data" / "risk"

KNOWN_STRATS = ("butterflies", "orb", "scalps")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_config(path: Path = CONFIG_PATH) -> dict:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    for strat in KNOWN_STRATS:
        if strat not in cfg.get("strategies", {}):
            raise ValueError(f"config missing strategy budget: {strat}")
    return cfg


def state_path(day: str) -> Path:
    return RISK_ROOT / f"{day}.json"


def effective_per_trade_cap(cfg: dict, strat: str) -> tuple[float, str | None]:
    """Configured dollar cap, tightened by the 2%-of-balance Playbook rule when
    a balance is set. Returns (cap_usd, note)."""
    configured = float(cfg["strategies"][strat]["max_risk_per_trade_usd"])
    balance = cfg.get("account_balance_usd")
    if not balance:
        return configured, "balance unset — 2% cap not active, dollar cap stands alone"
    pct_cap = float(balance) * float(cfg.get("pct_max_per_trade", 2.0)) / 100.0
    if pct_cap < configured:
        return pct_cap, f"2% of balance (${pct_cap:.0f}) tightens the configured ${configured:.0f}"
    return configured, None


def reset(day: str, force: bool = False) -> dict:
    """Create the day's risk state from config. Idempotent: an existing day
    file is NOT clobbered (it may already carry recorded trades) unless force."""
    path = state_path(day)
    if path.exists() and not force:
        return json.loads(path.read_text(encoding="utf-8"))
    cfg = load_config()
    limits = {
        "max_daily_loss_usd": float(cfg["max_daily_loss_usd"]),
        "max_open_positions": int(cfg["max_open_positions"]),
        "escalation_notional_usd": float(cfg["escalation_notional_usd"]),
        "strategies": {},
    }
    for strat in KNOWN_STRATS:
        cap, note = effective_per_trade_cap(cfg, strat)
        limits["strategies"][strat] = {
            "max_trades": int(cfg["strategies"][strat]["max_trades"]),
            "max_risk_per_trade_usd": round(cap, 2),
            "note": note,
        }
    state = {
        "day": day,
        "ts_reset": _utc_now_iso(),
        "limits": limits,
        "realized_pnl_usd": 0.0,
        "open_positions": 0,
        "trades": [],
        "halted": False,
        "violations": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def _evaluate(state: dict) -> dict:
    """Recompute derived fields: halt + violations from the recorded facts."""
    limits = state["limits"]
    violations: list[str] = []
    if state["realized_pnl_usd"] <= -limits["max_daily_loss_usd"]:
        state["halted"] = True
        violations.append(
            f"daily loss limit hit: realized ${state['realized_pnl_usd']:.0f} "
            f"vs limit -${limits['max_daily_loss_usd']:.0f} — STOP trading")
    if state["open_positions"] > limits["max_open_positions"]:
        violations.append(
            f"open positions {state['open_positions']} exceed cap "
            f"{limits['max_open_positions']}")
    for strat, budget in limits["strategies"].items():
        rows = [t for t in state["trades"] if t["strat"] == strat]
        if len(rows) > budget["max_trades"]:
            violations.append(
                f"{strat}: {len(rows)} trades exceed budget {budget['max_trades']}")
        for t in rows:
            risk = t.get("risk_usd")
            if risk is not None and risk > budget["max_risk_per_trade_usd"]:
                violations.append(
                    f"{strat}: trade risk ${risk:.0f} exceeds per-trade cap "
                    f"${budget['max_risk_per_trade_usd']:.0f}")
    state["violations"] = violations
    return state


def record(day: str, strat: str, pnl_usd: float, risk_usd: float | None,
           close: bool) -> dict:
    """Append a fill to the day and re-evaluate limits. `close` decrements the
    open-position count (an entry increments it)."""
    path = state_path(day)
    if not path.exists():
        state = reset(day)
    else:
        state = json.loads(path.read_text(encoding="utf-8"))
    state["trades"].append({
        "ts": _utc_now_iso(), "strat": strat,
        "pnl_usd": pnl_usd, "risk_usd": risk_usd, "close": close,
    })
    state["realized_pnl_usd"] = round(state["realized_pnl_usd"] + pnl_usd, 2)
    state["open_positions"] += (-1 if close else 1)
    state["open_positions"] = max(0, state["open_positions"])
    state = _evaluate(state)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    if state["halted"] or state["violations"]:
        # Same durable alert surface the heartbeat and cron wrappers use.
        from scripts.corpus_daily import emit_alert
        emit_alert("risk_limit",
                   "; ".join(state["violations"]) or "risk state halted",
                   {"day": day, "realized_pnl_usd": state["realized_pnl_usd"]})
    return state


def render(state: dict) -> str:
    lines = []
    header = f"risk state {state['day']}"
    if state["halted"]:
        header += "  [ALERT] HALTED — daily loss limit hit, no further entries"
    lines.append(header)
    lines.append(f"  realized P&L: ${state['realized_pnl_usd']:.2f}   "
                 f"daily stop: -${state['limits']['max_daily_loss_usd']:.0f}   "
                 f"open positions: {state['open_positions']}/"
                 f"{state['limits']['max_open_positions']}")
    for strat, budget in state["limits"]["strategies"].items():
        used = len([t for t in state["trades"] if t["strat"] == strat])
        line = (f"  {strat:<12} {used}/{budget['max_trades']} trades, "
                f"max ${budget['max_risk_per_trade_usd']:.0f}/trade")
        if budget.get("note"):
            line += f"  ({budget['note']})"
        lines.append(line)
    for v in state["violations"]:
        lines.append(f"  [ALERT] {v}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Risk-state reset / status / record [st-958]")
    ap.add_argument("--date", default=None, help="Trading day (default: today CT)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_reset = sub.add_parser("reset", help="Idempotent day-start reset from config")
    p_reset.add_argument("--force", action="store_true",
                         help="Clobber an existing day file (loses recorded trades)")
    sub.add_parser("status", help="Print the day's budgets and usage")
    p_rec = sub.add_parser("record", help="Record a fill by hand")
    p_rec.add_argument("--strat", required=True, choices=KNOWN_STRATS)
    p_rec.add_argument("--pnl", type=float, required=True,
                       help="Realized P&L in USD (negative = loss)")
    p_rec.add_argument("--risk", type=float, default=None,
                       help="Risk taken on the trade in USD (checked against the cap)")
    p_rec.add_argument("--close", action="store_true",
                       help="This fill closes a position (decrements open count)")
    args = ap.parse_args(argv)

    day = args.date or central_date().isoformat()
    if args.cmd == "reset":
        state = reset(day, force=args.force)
    elif args.cmd == "record":
        state = record(day, args.strat, args.pnl, args.risk, args.close)
    else:
        path = state_path(day)
        if not path.exists():
            print(f"no risk state for {day} — run: python -m runbook.risk_state reset")
            return 1
        state = json.loads(path.read_text(encoding="utf-8"))

    print(render(state))
    return 1 if state["halted"] else 0


if __name__ == "__main__":
    sys.exit(main())
