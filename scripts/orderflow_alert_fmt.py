"""Human one-liner formatter for orderflow sentinel alerts. [st-igim]

Reads alert JSON lines on stdin, emits a compact strike-first sentence per
line. Sits between `tail -F orderflow_alerts.jsonl` and any human surface —
the harness Monitor notification, a tmux pane, a phone push. The jsonl file
stays machine-readable; this is presentation only.
"""
from __future__ import annotations

import json
import sys


def fmt(a: dict) -> str:
    k = a.get("kind", "?")
    name = a.get("name", a.get("level", ""))
    if k == "approach":
        side = "below" if a.get("side") == "from_below" else "above"
        return (f"{a.get('strike')} {name} — approach from {side}, "
                f"spot {a.get('spot')} ({a.get('distance_pts')} pts)")
    if k == "zone":
        return (f"{a.get('strike_low')}-{a.get('strike_high')} {name} — "
                f"ZONE declared (recurring contest), spot {a.get('spot')}")
    if k == "zone_dissolved":
        return (f"{a.get('strike')} {name} — zone dissolved, "
                f"settled here, spot {a.get('spot')}")
    if k == "contested":
        cs = " vs ".join(f"{c.get('strike')} ({round(c.get('share', 0) * 100)}%)"
                         for c in a.get("contenders", []))
        return f"{name} contested: {cs}, spot {a.get('spot')}"
    if k in ("resolved", "relocation"):
        old = a.get("old")
        return (f"{a.get('strike')} {name} — {k} "
                f"(was {round(old) if old is not None else '?'}), "
                f"spot {a.get('spot')}")
    return json.dumps(a)


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            a = json.loads(line)
        except json.JSONDecodeError:
            print(line, flush=True)
            continue
        print(fmt(a), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
