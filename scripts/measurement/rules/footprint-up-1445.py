"""footprint-up-1445 — the footprint lens reads up at 14:45 CT. [st-djb9]

Pre-registered 2026-08-29 in scripts/measurement/final_hour_lens.py:11-19
(commit ac02296, "written before the first run; do not tune"), and carried
here unchanged, named by its entity id (knowledge/footprint-up-1445.md):

    box = 13:00 -> T, last30 = T-30m -> T, pos = (p_T - box_low) / box_range
    pos >= 0.80 and last30 chg > 0 and last30 delta > 0   -> up

The state is the final-hour lens row at T (strader/blotter/state.py); this
file reads three of its footprint fields and nothing else.
"""

ID = "footprint-up-1445"
STATE = "final-hour-lens"
FIRE_AT = ("14:45",)


def call(state: dict) -> str | None:
    fp = state.get("fp")
    if not fp:
        return None
    if fp["pos"] >= 0.80 and fp["l30_chg"] > 0 and fp["l30_delta"] > 0:
        return "up"
    return None
