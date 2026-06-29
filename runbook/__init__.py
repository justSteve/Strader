"""Strader Trading-Day Runbook.

Per-trading-day resource initialization across the active strats. See the
design spec in COO at docs/superpowers/specs/2026-06-29-trading-day-runbook-design.md
(bead co-7tw8); implementation epic co-rc4t.

Architecture (direction C): a deterministic Python harness that calls an LLM as
a *bounded function* only where free-text interpretation is genuinely required
(the Mancini commentary extraction). Everything else — fetch, validate, store,
render, schedule — is plain Python.

Pilot: Mancini (mancini/), gated on datastream health (datastream/).
"""
