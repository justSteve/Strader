"""Test compositor against real TradingView screenshot with manual calibration."""
import sys
sys.path.insert(0, '/root/projects/Strader')

from pathlib import Path
from mancini.parser import ReviewStep, Level
from mancini.compositor import compose_frame, FrameConfig

OUTPUT_DIR = Path('/root/projects/Strader/mancini/output')

# Calibration from evenly-spaced label clusters in the price axis.
# Clusters at y=(506,564,622,680,739) are 58px apart = 10 price points each.
# This gives 5.8 px/point. Mapping these to prices using the visible axis:
#   y=506 ≈ 7470, y=564 ≈ 7460, y=622 ≈ 7450, y=680 ≈ 7440, y=739 ≈ 7430
# Extrapolating: 7530 → y≈160, 7400 → y≈917
# So chart area runs from y=160 (7530) to y=917 (7400).

CHART_Y_TOP = 160     # pixel Y where highest visible price sits
CHART_Y_BOTTOM = 917  # pixel Y where lowest visible price sits
PRICE_MAX = 7530.0
PRICE_MIN = 7400.0

step = ReviewStep(
    title='The 9:55AM 7435 Failed Breakdown',
    time_anchor='9:55AM',
    price_levels=[7421.0, 7435.0, 7460.0],
    direction='rip',
    text_excerpt=(
        "At 9:50AM we tagged 7421 exact and spiked out. "
        "From 4:30AM to 9:30AM ES set a shelf of lows at 7435 "
        "from which we rallied 35 points. By selling to 7421 at "
        "9:50AM, we lost that shelf. Shortly after at 9:55AM to "
        "10AM ES recovered the 7435 shelf and we ripped to 7460+."
    )
)

levels = [
    Level(price=7421, annotation="major — daily low"),
    Level(price=7435, annotation="major — shelf of lows"),
    Level(price=7442, annotation=""),
    Level(price=7450, annotation="major — prior resistance"),
    Level(price=7472, annotation="major — range high"),
]

frame = compose_frame(
    chart_path=Path('/mnt/c/myStuff/tvscreen.jpg'),
    step=step,
    levels=levels,
    price_min=PRICE_MIN,
    price_max=PRICE_MAX,
    config=FrameConfig(
        overlay_width_pct=0.30,
        chart_y_top=CHART_Y_TOP,
        chart_y_bottom=CHART_Y_BOTTOM,
    )
)

out_path = OUTPUT_DIR / 'test_real_frame.png'
frame.save(out_path)
print(f"Saved: {out_path} ({frame.size[0]}x{frame.size[1]})")

# Also verify calibration by printing where each level lands
for lvl in levels:
    ratio = (lvl.price - PRICE_MIN) / (PRICE_MAX - PRICE_MIN)
    y = CHART_Y_TOP + int((1.0 - ratio) * (CHART_Y_BOTTOM - CHART_Y_TOP))
    print(f"  {lvl.price} ({lvl.annotation or 'minor'}) → y={y}")
