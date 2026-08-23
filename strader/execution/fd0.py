"""FD0 state machine, attempt ledger, journal and go/no-go checklist.

Design: ``docs/superpowers/specs/2026-08-02-fd0-flushdown-design.md``.
Bead: Cut And Await (st-apzt).

    IDLE ──s──▶ COMPOSED ──in <px>──▶ OPEN ──────────out <px> (his own cut)──┐
      ▲            │ n                  │ tape through the stop trigger        │
      └────────────┘                    ▼                                      ▼
                              CUT_PRESUMED ──out <px>──▶ WAITING ──s──▶ COMPOSED
    DONE ◀── x ── from any state

Two properties this module exists to guarantee, both of them about *not*
acting:

**It never transmits.** There is no order API here and no credentials. The
harness renders a string; Steve pastes it. The stop lives on Schwab's side once
he sends it, conditioned on the SPX tape, which is why the harness watching the
tape is only ever *bookkeeping* — the broker owns the exit, not this process.

**It never re-enters.** Reload is Steve pressing the key again. The whole point
of the generation is "cut and WAIT" — it counters the chasing instinct rather
than automating it. ``observe()`` can move the machine to CUT_PRESUMED and it
can refuse a compose, but no code path in this file opens a position.

The ledger is a list of attempts rather than a running total, so the tape
estimate booked at presumption can be *corrected* by Steve's confirmed exit
without any risk of double-debiting the budget.

2026-08-23, joined to the intent dialect (st-79z.3) as the engine's trigger
desk: the machine now saves itself after every transition (``save``/``load``)
because the dictation pane runs one line per process and ``in 1.25`` has to
find what ``go`` composed; ``out`` is also legal straight from OPEN, because
Steve's own word that he is out beats a presumption the tape never made.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Sequence

from strader.execution.compose import (
    Budget, CannotFund, NoStrikeInBand, Ticket, compose, CONTRACT_MULTIPLIER,
)

log = logging.getLogger(__name__)

__all__ = ["State", "Attempt", "Fd0", "IllegalTransition", "checklist", "CheckLine",
           "journal_path_for", "state_path_for"]


class State(str, Enum):
    IDLE = "IDLE"
    COMPOSED = "COMPOSED"
    OPEN = "OPEN"
    CUT_PRESUMED = "CUT_PRESUMED"
    WAITING = "WAITING"
    DONE = "DONE"


class IllegalTransition(Exception):
    """A key that means nothing in the current state. Refused loudly rather
    than ignored — a silently swallowed keystroke on an execution surface is
    indistinguishable from a stuck terminal."""


@dataclass(frozen=True)
class Attempt:
    """One entry, from ticket to close. ``realized_usd`` is positive for a
    loss; ``estimated`` marks a loss booked from the tape rather than from
    Steve's confirmed fill."""

    ticket: Ticket
    entry_premium_pts: float
    exit_premium_pts: float | None = None
    realized_usd: float = 0.0
    estimated: bool = True
    opened_at: datetime | None = None
    closed_at: datetime | None = None

    @property
    def closed(self) -> bool:
        return self.closed_at is not None

    def to_dict(self) -> dict:
        return {
            "ticket": self.ticket.to_dict(),
            "entry_premium_pts": self.entry_premium_pts,
            "exit_premium_pts": self.exit_premium_pts,
            "realized_usd": self.realized_usd,
            "estimated": self.estimated,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Attempt":
        return cls(
            ticket=Ticket.from_dict(d["ticket"]),
            entry_premium_pts=float(d["entry_premium_pts"]),
            exit_premium_pts=(None if d.get("exit_premium_pts") is None
                              else float(d["exit_premium_pts"])),
            realized_usd=float(d.get("realized_usd", 0.0)),
            estimated=bool(d.get("estimated", True)),
            opened_at=datetime.fromisoformat(d["opened_at"]) if d.get("opened_at") else None,
            closed_at=datetime.fromisoformat(d["closed_at"]) if d.get("closed_at") else None,
        )


# ------------------------------------------------------------- checklist ---

@dataclass(frozen=True)
class CheckLine:
    name: str
    passed: bool
    detail: str

    def render(self) -> str:
        return f"  [{'PASS' if self.passed else 'FAIL'}]  {self.name} — {self.detail}"


def checklist(
    *,
    token_status: str,
    spx_ticks: Sequence[tuple[datetime, float]],
    chain_ok: bool,
    chain_detail: str,
    tos_validated: bool,
    budget: Budget,
    journal_path: Path,
    build_complete: bool = True,
    build_detail: str = "",
) -> list[CheckLine]:
    """The Monday 08:15 checklist. Renders PASS/FAIL; Steve makes the call.

    ``build_complete`` is the design's own rule made machine-visible: *"If any
    of 1–4 slips past Sunday, that is a NO-GO input, stated plainly in Monday's
    checklist."* It is a checklist line rather than a comment so a slipped
    build cannot be quietly forgotten on a busy morning.
    """
    lines = [
        CheckLine("Schwab token", token_status == "ok",
                  f"status {token_status!r}"),
    ]

    moving = (len(spx_ticks) >= 3
              and all(b[0] > a[0] for a, b in zip(spx_ticks, spx_ticks[1:]))
              and len({p for _, p in spx_ticks}) > 1)
    lines.append(CheckLine(
        "SPX quote stream", moving,
        f"{len(spx_ticks)} tick(s)"
        + (", monotonic and moving" if moving else ", not three monotonic moving ticks"),
    ))

    lines.append(CheckLine("Chain / delta band", chain_ok, chain_detail))
    lines.append(CheckLine(
        "TOS order construct", tos_validated,
        "Steve confirmed the saved SPX-conditional exit reloads with its trigger editable"
        if tos_validated else
        "the 1st Triggers pair was confirmed 08-03; the SPX mark condition on the SELL "
        "leg, saved and reloaded, is not — the one item that is Steve's"))
    lines.append(CheckLine(
        "Budget ledger armed",
        budget.spent_usd == 0 and budget.attempts_used == 0,
        f"${budget.total_usd:.0f} / {budget.attempts} attempts / "
        f"${budget.spent_usd:.0f} spent",
    ))

    writable = False
    try:
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        with journal_path.open("a"):
            pass
        writable = True
        detail = str(journal_path)
    except OSError as exc:
        detail = f"{journal_path}: {exc}"
    lines.append(CheckLine("Journal writable", writable, detail))

    lines.append(CheckLine(
        "Build plan complete", build_complete,
        build_detail or ("steps 1-4 done" if build_complete
                         else "steps 1-4 did not complete — the design makes this a NO-GO input")))
    return lines


# ----------------------------------------------------------------- engine ---

@dataclass
class Fd0:
    """The harness. One instance per session."""

    budget_total_usd: float = 100.0
    budget_attempts: int = 2
    journal_path: Path | None = None
    state_path: Path | None = None      # set, the machine saves itself after every transition

    state: State = State.IDLE
    attempts: list[Attempt] = field(default_factory=list)
    pending: Ticket | None = None
    open_attempt: Attempt | None = None

    # ------------------------------------------------------- persistence ---

    def to_dict(self) -> dict:
        d = {
            "budget_total_usd": self.budget_total_usd,
            "budget_attempts": self.budget_attempts,
            "state": self.state.value,
            "attempts": [a.to_dict() for a in self.attempts],
            "pending": self.pending.to_dict() if self.pending else None,
            "open_attempt": None,
        }
        # After a presumed cut the open attempt *is* the last ledger entry;
        # store that as a reference so a reload cannot hold it twice.
        if self.open_attempt is not None:
            if self.attempts and self.open_attempt is self.attempts[-1]:
                d["open_attempt"] = "last"
            else:
                d["open_attempt"] = self.open_attempt.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict, *, journal_path: Path | None = None,
                  state_path: Path | None = None) -> "Fd0":
        h = cls(budget_total_usd=float(d.get("budget_total_usd", 100.0)),
                budget_attempts=int(d.get("budget_attempts", 2)),
                journal_path=journal_path, state_path=state_path,
                state=State(d.get("state", "IDLE")),
                attempts=[Attempt.from_dict(a) for a in d.get("attempts", [])],
                pending=Ticket.from_dict(d["pending"]) if d.get("pending") else None)
        oa = d.get("open_attempt")
        if oa == "last":
            h.open_attempt = h.attempts[-1] if h.attempts else None
        elif isinstance(oa, dict):
            h.open_attempt = Attempt.from_dict(oa)
        return h

    def save(self) -> None:
        """Write the machine to ``state_path`` (no-op without one). Atomic — a
        half-written state file on an execution surface is worse than none."""
        if self.state_path is None:
            return
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_path.with_suffix(self.state_path.suffix + ".partial")
            tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
            tmp.replace(self.state_path)
        except OSError as exc:
            log.error("FD0 STATE SAVE FAILED (%s): %s", self.state_path, exc)

    @classmethod
    def load(cls, state_path: Path, *, journal_path: Path | None = None,
             **defaults) -> "Fd0":
        """The machine as it was left, or a fresh one when there is no file.
        A file that cannot be parsed is an error, not a fresh start — a fresh
        start would silently forget an OPEN attempt."""
        if not state_path.is_file():
            return cls(journal_path=journal_path, state_path=state_path, **defaults)
        data = json.loads(state_path.read_text(encoding="utf-8"))
        h = cls.from_dict(data, journal_path=journal_path, state_path=state_path)
        log.info("FD0 state loaded from %s: %s", state_path, h.state.value)
        return h

    # ------------------------------------------------------------ ledger ---

    @property
    def budget(self) -> Budget:
        """Rebuilt from the attempt ledger every time, so a corrected exit
        cannot double-debit and a mis-sequenced update cannot drift."""
        closed = [a for a in self.attempts if a.closed]
        return Budget(
            total_usd=self.budget_total_usd,
            attempts=self.budget_attempts,
            spent_usd=sum(max(0.0, a.realized_usd) for a in closed),
            attempts_used=len(closed),
        )

    # ----------------------------------------------------------- journal ---

    def _journal(self, event: str, **payload) -> None:
        record = {"at": datetime.now().isoformat(), "event": event,
                  "state": self.state.value, **payload}
        if self.journal_path is None:
            log.debug("journal (no path): %s", record)
            return
        try:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            with self.journal_path.open("a") as fh:
                fh.write(json.dumps(record) + "\n")
        except OSError as exc:
            # An unwritable journal must never take the surface down mid-session,
            # but it must be loud — the journal is the audit trail.
            log.error("JOURNAL WRITE FAILED (%s): %s", exc, record)

    # --------------------------------------------------------- transitions ---

    def compose(self, chain, spx_now: float, **kw) -> Ticket:
        """``s`` — build a ticket. Legal from IDLE and WAITING."""
        if self.state not in (State.IDLE, State.WAITING):
            raise IllegalTransition(f"cannot compose from {self.state.value}")

        try:
            ticket = compose(chain, spx_now, self.budget, **kw)
        except (CannotFund, NoStrikeInBand) as exc:
            self._journal("refuse", reason=type(exc).__name__, detail=str(exc))
            log.warning("compose refused: %s", exc)
            raise

        self.pending = ticket
        self.state = State.COMPOSED
        self._journal("compose", ticket=ticket.as_record())
        for w in ticket.warnings:
            self._journal("warn", message=w)
        self.save()
        return ticket

    def discard(self) -> None:
        """``n`` — Steve didn't send it."""
        if self.state is not State.COMPOSED:
            raise IllegalTransition(f"nothing to discard from {self.state.value}")
        self._journal("discard", ticket=self.pending.as_record() if self.pending else None)
        self.pending = None
        self.state = State.IDLE
        self.save()

    def confirm_fill(self, premium_pts: float, *, now: datetime | None = None) -> Attempt:
        """``in <px>`` — Steve sent it and it filled at ``premium_pts``."""
        if self.state is not State.COMPOSED or self.pending is None:
            raise IllegalTransition(f"no ticket to fill from {self.state.value}")

        attempt = Attempt(ticket=self.pending, entry_premium_pts=premium_pts,
                          opened_at=now or datetime.now())
        self.open_attempt = attempt
        self.pending = None
        self.state = State.OPEN
        self._journal("confirm_fill", entry_premium_pts=premium_pts,
                      stop_trigger_spx=attempt.ticket.stop_trigger_spx)
        self.save()
        return attempt

    def observe(self, spx: float, *, now: datetime | None = None) -> bool:
        """Feed the tape. Returns True when this observation presumed a cut.

        Only ever *presumes*. The real stop is resident at the broker; this is
        bookkeeping so the harness knows what state Steve is in, and so the
        next attempt's budget is already re-derived when he reaches for it.
        """
        if self.state is not State.OPEN or self.open_attempt is None:
            return False
        ticket = self.open_attempt.ticket
        through = (spx >= ticket.stop_trigger_spx if ticket.right == "PUT"
                   else spx <= ticket.stop_trigger_spx)
        if not through:
            return False

        # Book the tape's estimate now; Steve's confirmed exit corrects it.
        estimate_usd = self.open_attempt.ticket.derivation.attempt_risk_usd
        closed = replace(self.open_attempt, realized_usd=estimate_usd,
                         estimated=True, closed_at=now or datetime.now())
        self.attempts.append(closed)
        self.open_attempt = closed
        self.state = State.CUT_PRESUMED
        self._journal("presume_cut", spx=spx,
                      trigger_spx=closed.ticket.stop_trigger_spx,
                      estimated_loss_usd=round(estimate_usd, 2))
        log.warning("presumed cut at SPX %.2f (trigger %.2f) — estimated loss $%.2f",
                    spx, closed.ticket.stop_trigger_spx, estimate_usd)
        self.save()
        return True

    def confirm_exit(self, premium_pts: float, *, now: datetime | None = None) -> Attempt:
        """``out <px>`` — the real exit premium.

        From CUT_PRESUMED it corrects the tape's estimate. From OPEN it books a
        cut the tape never presumed — Steve's own hand, or a stop the harness
        did not see because nothing was feeding it. Either way his word is the
        ledger's; the presumption only ever pre-computed.
        """
        if self.open_attempt is None or self.state not in (State.CUT_PRESUMED, State.OPEN):
            raise IllegalTransition(f"no open attempt to close from {self.state.value}")

        entry = self.open_attempt.entry_premium_pts
        realized_usd = (entry - premium_pts) * CONTRACT_MULTIPLIER * self.open_attempt.ticket.lots
        manual = self.state is State.OPEN

        corrected = replace(self.open_attempt, exit_premium_pts=premium_pts,
                            realized_usd=realized_usd, estimated=False,
                            closed_at=self.open_attempt.closed_at or now or datetime.now())
        if manual:
            self.attempts.append(corrected)
        else:
            # Replace in place: the estimate and the confirmation are the same
            # attempt, so the ledger must never hold both.
            self.attempts[-1] = corrected
        self.open_attempt = None
        self.state = State.WAITING

        self._journal("confirm_exit", exit_premium_pts=premium_pts,
                      realized_usd=round(realized_usd, 2), manual_cut=manual,
                      budget_remaining_usd=round(self.budget.remaining_usd, 2),
                      attempts_left=self.budget.attempts_left)
        if realized_usd < 0:
            log.info("attempt closed for a gain of $%.2f", -realized_usd)
        self.save()
        return corrected

    def end(self) -> None:
        """``x`` — end the session from any state."""
        self._journal("end", attempts=len(self.attempts),
                      spent_usd=round(self.budget.spent_usd, 2))
        self.pending = None
        self.open_attempt = None
        self.state = State.DONE
        self.save()

    # ----------------------------------------------------------- surface ---

    # The pane text, in three parts so the intent desk can reuse the stop and
    # exit blocks under its own paste line. Plain words, every number in the
    # derivation shown, so the reasoning is auditable at a glance.

    @staticmethod
    def render_stop(ticket: Ticket) -> list[str]:
        d = ticket.derivation
        per = f"{'each' if ticket.lots > 1 else ''}"
        return [
            f"  Cut if SPX reaches {ticket.stop_trigger_spx:.2f}  "
            f"— that is {d.stop_distance_spx:.2f} points "
            f"{'below' if ticket.right == 'CALL' else 'above'} {ticket.spx_at_compose:.2f}",
            f"  Most this costs you: ${ticket.max_loss_usd:.2f}",
            "",
            "  How that stop was worked out:",
            f"    ${d.budget_remaining_usd:.2f} left, {d.attempts_left} attempt(s) "
            f"-> ${d.budget_remaining_usd / d.attempts_left:.2f} for this one",
            f"    less ${d.spread_usd:.2f} spread and ${d.fees_rt_usd:.2f} fees"
            f"{f' ({ticket.lots} lots)' if ticket.lots > 1 else ''} "
            f"= ${d.attempt_risk_usd:.2f} to risk",
            f"    ${d.attempt_risk_usd:.2f} is {d.stop_premium_pts:.2f} of premium"
            f"{' ' + per if per else ''}, which at {d.delta_live:.2f} delta is "
            f"{d.stop_distance_spx:.2f} SPX points",
            f"    the tape's own noise is about {d.noise_floor_spx:.2f} points",
        ]

    @staticmethod
    def render_exit(ticket: Ticket) -> list[str]:
        ef = ticket.exit_fields
        return [
            "  EXIT — cannot be pasted. Make the entry a 1st Triggers order,",
            "  add the SELL leg, then click the gear on THAT row (not the buy):",
            f"    symbol     {ef['trigger_symbol']}",
            f"    method     {ef['method']}",
            f"    condition  {ef['trigger_direction']}  {ef['trigger_price']:.2f}",
            f"    order      {ef['action']}",
        ]

    def render(self, ticket: Ticket, *, clipboard: bool = False) -> str:
        """The whole pane text. ``clipboard`` says whether the caller actually
        put the order string there — the text never claims it otherwise."""
        d = ticket.derivation
        lines = [
            f"  BUY {ticket.lots} SPX {ticket.right.lower()}, strike {ticket.contract.strike:g}, "
            f"delta {d.delta_live:.2f}",
            f"  Pay up to {ticket.limit_pts:.2f}  "
            f"(book {ticket.contract.bid_pts:.2f} / {ticket.contract.ask_pts:.2f})",
            "",
            *self.render_stop(ticket),
            "",
            "  ENTRY — paste this" + (" (clipboard holds it):" if clipboard else ":"),
            f"  {ticket.order_string}",
            "",
            *self.render_exit(ticket),
        ]
        for w in ticket.warnings:
            lines += ["", f"  ** {w}"]
        return "\n".join(lines)

    def status_line(self) -> str:
        """One line for a read-back: where the machine is and what it holds."""
        b = self.budget
        money = f"${b.remaining_usd:.0f} left, {b.attempts_left} attempt(s)"
        if self.state is State.IDLE:
            return f"FD0: idle. {money}."
        if self.state is State.COMPOSED and self.pending:
            t = self.pending
            return (f"FD0: composed — {t.lots} {t.contract.strike:g} {t.right.lower()}"
                    f"{'s' if t.lots > 1 else ''} at {t.limit_pts:.2f}, cut at "
                    f"{t.stop_trigger_spx:.2f}. Say in <premium> when it fills. {money}.")
        if self.state is State.OPEN and self.open_attempt:
            a = self.open_attempt
            return (f"FD0: open — in at {a.entry_premium_pts:.2f}, cut at "
                    f"{a.ticket.stop_trigger_spx:.2f}. Say out <premium> when you are out. {money}.")
        if self.state is State.CUT_PRESUMED and self.open_attempt:
            a = self.open_attempt
            return (f"FD0: cut presumed at SPX {a.ticket.stop_trigger_spx:.2f}, booked "
                    f"${a.realized_usd:.2f} until you say out <premium>. {money}.")
        if self.state is State.WAITING:
            return f"FD0: waiting — cut and wait. {money}."
        return f"FD0: {self.state.value.lower()}. {money}."


def journal_path_for(day: date | None = None, root: Path | None = None) -> Path:
    day = day or date.today()
    root = root or Path("data/exec")
    return root / f"fd0-{day.isoformat()}.jsonl"


def state_path_for(day: date | None = None, root: Path | None = None) -> Path:
    """Where the machine saves itself — beside the day's journal."""
    day = day or date.today()
    root = root or Path("data/exec")
    return root / f"fd0-{day.isoformat()}-state.json"
