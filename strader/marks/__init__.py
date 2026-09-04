"""Mark paths for blotter rows. [st-9hhc]

Two ways to know what a 0DTE single was worth minute by minute:

* ``strader.marks.prints`` — the actual OPRA print path, available 13:00-15:00
  CT on corpus days that carry ``databento_opra.jsonl(.gz)`` (276 days,
  2025-05-27 -> 2026-08-14). The truth, where it exists.
* ``strader.marks.estimated`` — a per-minute ES->premium proxy (delta x ES
  move with a 0DTE decay term), calibrated against the print path and usable
  on days with ES tape only. Second best, and it says so: every estimated
  mark outside the calibrated 13:00-15:00 CT window is either refused or
  labelled extrapolated.

The two paths never pool silently. Blotter aggregates split by mark path;
that contract is stated in docs/plans/estimated-mark-path-plan.md and this
package does not relax it.
"""
