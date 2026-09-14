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
    ("Previewed", "previewed", 640),
    ("Working", "working", 620),
    ("Main", "filled", 720),
    ("Exiting", "exiting", 540),
    ("Closed", "closed", 600),
    ("Refused", "refused", 470),
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
                      "left to right. The panel replaces the position block at the foot of the page.\n\n"
                      "Every stage: the stage word, the mode chip, one number that matters, the rows "
                      "behind it, and only the controls that act on this stage. The header's refresh, "
                      "pause and less/more work on each artboard; the chips above each artboard switch "
                      "stage, density and mode.\n\n"
                      "Numbers are sample values from today's first paper cycle.")},
        ],
        "launch": {"view": "canvas"},
    }
    (out / "canvas.json").write_text(json.dumps(canvas, indent=2))
    print(f"wrote {len(boards)} artboards + canvas.json to {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "build")
