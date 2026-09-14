"""Generate one artboard per stage of an order's life from Panel.template.dc.html.

Each artboard is the same panel with a different default ``stage`` and a
frame height sized to that stage's content; canvas.json lays them out in
life-cycle order. Run from anywhere:

    python3 build.py <out-dir>

Writes Main.dc.html (the filled stage) plus one file per other stage, and
canvas.json, into <out-dir>.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = (HERE / "Panel.template.dc.html").read_text()

# (file stem, stage, frame height) in life-cycle order
STAGES = [
    ("Flat", "none", 260),
    ("Previewed", "previewed", 600),
    ("Working", "working", 500),
    ("Main", "filled", 720),
    ("Exiting", "exiting", 470),
    ("Closed", "closed", 440),
    ("Refused", "refused", 360),
]
W = 576
GAP_X = 96
GAP_Y = 160
PER_ROW = 4


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    boards = []
    x = y = 0
    row_h = 0
    for i, (stem, stage, h) in enumerate(STAGES):
        if i and i % PER_ROW == 0:
            x, y, row_h = 0, y + row_h + GAP_Y, 0
        src = TEMPLATE.replace("__STAGE__", stage).replace("__HEIGHT__", str(h))
        (out / f"{stem}.dc.html").write_text(src)
        boards.append({"file": f"{stem}.dc.html", "title": stage if stem != "Main" else "filled",
                       "x": x, "y": y, "w": W, "h": h, "is_interactive": True})
        x += W + GAP_X
        row_h = max(row_h, h)
    canvas = {
        "artboards": boards,
        "annotations": [
            {"id": "brief", "x": 0, "y": -260, "w": 640,
             "text": ("Order status panel for /exec/order, one artboard per stage of an order's life, "
                      "left to right. One ticking clock in the header; every other time is 'x ago'.\n\n"
                      "Names are [C|P][strike]. One net number, commissions included. The filled stage "
                      "is a live editor for the stop and the take-profit target (10x the fill price, "
                      "the standing assumption on st-fn5y).\n\n"
                      "Numbers are sample values from today's first paper cycle.")},
        ],
        "launch": {"view": "canvas"},
    }
    (out / "canvas.json").write_text(json.dumps(canvas, indent=2))
    print(f"wrote {len(boards)} artboards + canvas.json to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "build")
