"""Generate a test frame with a placeholder chart to validate layout."""
import sys
sys.path.insert(0, '/root/projects/Strader')

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from mancini.parser import ReviewStep, Level
from mancini.compositor import compose_frame, FrameConfig

OUTPUT_DIR = Path('/root/projects/Strader/mancini/output')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def make_placeholder_chart(width=1920, height=1080) -> Path:
    """Create a fake chart image with grid and price-like candlesticks."""
    img = Image.new('RGB', (width, height), (18, 18, 24))
    draw = ImageDraw.Draw(img)

    # Grid lines
    for y in range(0, height, 60):
        draw.line([(0, y), (width, y)], fill=(35, 35, 45), width=1)
    for x in range(0, width, 80):
        draw.line([(x, 0), (x, height)], fill=(35, 35, 45), width=1)

    # Simulated price action — a sell then bounce pattern
    import random
    random.seed(42)
    candle_width = 8
    gap = 4
    x_start = 100
    price = 7460.0
    prices_y = []

    # Simulate: drift down from 7460 to 7421, then rip to 7460
    moves = (
        [random.uniform(-3, 1) for _ in range(40)] +  # slow sell
        [random.uniform(-5, -1) for _ in range(15)] +  # elevator down
        [random.uniform(-1, 6) for _ in range(30)] +  # rip up
        [random.uniform(-2, 2) for _ in range(30)]    # consolidation
    )

    for i, move in enumerate(moves):
        price += move
        price = max(7410, min(7480, price))

        x = x_start + i * (candle_width + gap)
        if x > width - 100:
            break

        open_p = price
        close_p = price + random.uniform(-4, 4)
        high_p = max(open_p, close_p) + random.uniform(0, 3)
        low_p = min(open_p, close_p) - random.uniform(0, 3)

        def p2y(p):
            return int(40 + (1.0 - (p - 7400) / 100) * (height - 80))

        # Wick
        draw.line([(x + candle_width // 2, p2y(high_p)),
                   (x + candle_width // 2, p2y(low_p))],
                  fill=(100, 100, 100), width=1)

        # Body
        color = (38, 166, 91) if close_p >= open_p else (214, 48, 49)
        y1, y2 = p2y(max(open_p, close_p)), p2y(min(open_p, close_p))
        draw.rectangle([x, y1, x + candle_width, y2], fill=color)

    # Price axis on right
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 16)
    except OSError:
        font = ImageFont.load_default()

    for p in range(7410, 7485, 10):
        y = int(40 + (1.0 - (p - 7400) / 100) * (height - 80))
        draw.text((width - 70, y - 8), str(p), fill=(220, 220, 220), font=font)
        draw.line([(width - 80, y), (width - 72, y)], fill=(160, 160, 160), width=2)

    path = OUTPUT_DIR / 'placeholder_chart.png'
    img.save(path)
    return path


# Build test data
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
    Level(price=7460, annotation=""),
    Level(price=7472, annotation="major — range high"),
]

chart_path = make_placeholder_chart()

frame = compose_frame(
    chart_path=chart_path,
    step=step,
    levels=levels,
    price_min=7400,
    price_max=7500,
    config=FrameConfig()
)

out_path = OUTPUT_DIR / 'test_frame.png'
frame.save(out_path)
print(f"Test frame saved: {out_path}")
print(f"Size: {frame.size[0]}x{frame.size[1]}")
