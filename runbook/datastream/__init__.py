"""Datastream health gate for the Runbook. [co-i10h]

The pre-open gate: verify Databento + TOS/Schwab ingestion is live and flowing
before any downstream Runbook step trusts the data. If the streams are down, the
Runbook halts and alerts rather than emitting confident-but-stale levels, charts,
and regime reads. It is a gate, not just a task.

This pilot reads the corpus manifest (data/corpus/YYYY-MM-DD/manifest.json) as
the health signal. The full liveness criteria are #1's own spec; the pilot
consumes a boolean gate.
"""
