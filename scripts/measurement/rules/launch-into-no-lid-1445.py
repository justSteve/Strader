"""launch-into-no-lid-1445 — R2 of the final-hour combination calls, at 14:45 CT. [st-djb9]

Pre-registered 2026-08-29 in scripts/measurement/final_hour_combo.py:11-45
(commit 9df6a9c, "written before the first run; not tuned"), and carried here
unchanged, named by its entity id (knowledge/launch-into-no-lid-1445.md):

    R2 launch : pos >= 0.75 and l30_chg > 0 and l30_delta > 0 and not lid  -> up

    lid = a Mancini resistance within 10 points above p_T whose state over
    13:00 -> T is held or reclaimed. A day with no parsed letter has no lid
    (the combo script's "treated as not present"), so the rule can fire on it.

R1 (the flush, pos <= 0.25) precedes R2 in the combo script's first-fire
chain; the two cannot both hold, so R2 alone is the same rule as R2 in the
chain — pinned by the registry test against the 08-29 rows.
"""

ID = "launch-into-no-lid-1445"
STATE = "final-hour-lens"
FIRE_AT = ("14:45",)


def call(state: dict) -> str | None:
    fp = state.get("fp")
    if not fp:
        return None
    mc = state.get("mc") or {}
    lid = mc.get("lid")
    if fp["pos"] >= 0.75 and fp["l30_chg"] > 0 and fp["l30_delta"] > 0 and not lid:
        return "up"
    return None
