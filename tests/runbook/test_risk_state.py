"""Risk-state reset — the Playbook hard limits as code. [st-958]

What must hold: the reset is idempotent (recorded trades survive a re-fire),
the daily loss limit flips the day to HALTED and alerts, per-strat budgets
trip violations, and the 2%-of-balance rule tightens dollar caps only when a
balance is configured.
"""
import json
from pathlib import Path

import pytest

from runbook import risk_state

CFG = {
    "account_balance_usd": None,
    "max_daily_loss_usd": 300,
    "max_open_positions": 2,
    "pct_max_per_trade": 2.0,
    "escalation_notional_usd": 5000,
    "strategies": {
        "butterflies": {"max_trades": 3, "max_risk_per_trade_usd": 150},
        "orb": {"max_trades": 1, "max_risk_per_trade_usd": 100},
        "scalps": {"max_trades": 3, "max_risk_per_trade_usd": 100},
    },
}


@pytest.fixture
def wired(monkeypatch, tmp_path):
    alerts = []
    monkeypatch.setattr(risk_state, "RISK_ROOT", tmp_path)
    monkeypatch.setattr(risk_state, "load_config", lambda path=None: json.loads(json.dumps(CFG)))
    import scripts.corpus_daily as cd
    monkeypatch.setattr(cd, "emit_alert",
                        lambda kind, msg, detail: alerts.append((kind, msg)))
    return alerts


def test_reset_snapshots_config(wired):
    state = risk_state.reset("2026-08-01")
    assert state["limits"]["max_daily_loss_usd"] == 300
    assert state["realized_pnl_usd"] == 0.0
    assert not state["halted"]
    assert risk_state.state_path("2026-08-01").exists()


def test_reset_is_idempotent_preserves_trades(wired):
    risk_state.reset("2026-08-01")
    risk_state.record("2026-08-01", "butterflies", -45.0, 130.0, close=False)
    state = risk_state.reset("2026-08-01")
    assert len(state["trades"]) == 1
    assert state["realized_pnl_usd"] == -45.0
    # --force is the explicit clobber
    state = risk_state.reset("2026-08-01", force=True)
    assert state["trades"] == []


def test_daily_loss_limit_halts_and_alerts(wired):
    risk_state.record("2026-08-01", "butterflies", -180.0, 150.0, close=False)
    assert wired == []
    state = risk_state.record("2026-08-01", "scalps", -140.0, 90.0, close=False)
    assert state["halted"]
    assert any("STOP trading" in v for v in state["violations"])
    assert wired and wired[0][0] == "risk_limit"
    # render carries the halt loudly
    assert "HALTED" in risk_state.render(state)


def test_per_strat_trade_budget_trips(wired):
    risk_state.record("2026-08-01", "orb", 20.0, 80.0, close=False)
    state = risk_state.record("2026-08-01", "orb", 15.0, 80.0, close=False)
    assert any("orb: 2 trades exceed budget 1" in v for v in state["violations"])


def test_per_trade_risk_cap_trips(wired):
    state = risk_state.record("2026-08-01", "butterflies", 0.0, 400.0, close=False)
    assert any("exceeds per-trade cap" in v for v in state["violations"])


def test_close_decrements_open_positions(wired):
    risk_state.record("2026-08-01", "butterflies", 0.0, 100.0, close=False)
    state = risk_state.record("2026-08-01", "butterflies", 60.0, None, close=True)
    assert state["open_positions"] == 0


def test_open_position_cap_trips(wired):
    for _ in range(3):
        state = risk_state.record("2026-08-01", "scalps", 0.0, 50.0, close=False)
    assert any("open positions 3 exceed cap 2" in v for v in state["violations"])


def test_balance_activates_pct_cap(wired, monkeypatch):
    cfg = json.loads(json.dumps(CFG))
    cfg["account_balance_usd"] = 5000  # 2% = $100 < $150 configured for flies
    monkeypatch.setattr(risk_state, "load_config", lambda path=None: cfg)
    state = risk_state.reset("2026-08-02")
    fly = state["limits"]["strategies"]["butterflies"]
    assert fly["max_risk_per_trade_usd"] == 100.0
    assert "tightens" in fly["note"]


def test_no_balance_notes_inactive_pct_cap(wired):
    state = risk_state.reset("2026-08-03")
    note = state["limits"]["strategies"]["butterflies"]["note"]
    assert "balance unset" in note
