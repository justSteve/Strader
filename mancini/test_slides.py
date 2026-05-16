"""Test sentence-level slide parsing and multi-frame gallery generation."""
import sys
sys.path.insert(0, '/root/projects/Strader')

from pathlib import Path
from mancini.parser import parse_email, Slide
from mancini.compositor import compose_frame, FrameConfig
from mancini.gallery import generate_gallery

OUTPUT_DIR = Path('/root/projects/Strader/mancini/output/test_gallery')

sample = """View this post on the web at https://example.com

Today, ES took its second breather.
**********Important Housekeeping Notices********
(NEW) Contract Roll: blah
FOR NEW READERS: essential
The Run Down on The Level To Level Approach: What, Why, How
This section is boilerplate...
                                                  On to today: Basic Themes
Heading into today themes blah.
                                                  Trade Recap/Daily Summary
NOTE: The purpose of this trade recap section is to run down examples.
                                                          Thursday Evening
Yesterday, we closed up at the high of day, week, and all time highs. As such, there was nothing for me to do. The first mini-Failed Breakdown was of 7507. I wrote yesterday at 4pm about 7507 being 1st support down and we set a nice 19 point low here at 1:20PM today. By 10pm, ES sold off to that 7496 support. By 10:45pm, ES returned to 7507 and popped above but we were never able to get a long trigger here.
                             Friday Morning And The "Elevator Down" Sell To 7421
When I woke up and checked price at 7:30AM, ES was down at 7450-55. At 4:30AM, ES knifed right through 7450-55 down to 7435. I was asleep for this, but there was no long here since we were fully knifing. The reclaim of 7450-55 however was actionable around 6:45AM for anyone who wanted it. We had quite nice acceptance here. One could also use the non-acceptance protocol here. This triggered at 6:45AM and we popped nicely to 7473 1st up.
                                              The 9:55AM 7435 Failed Breakdown
At 9:50AM we tagged 7421 exact and spiked out nicely. From 4:30AM to 9:30AM ES set a nice shelf of lows at 7435 from which we rallied 35 points. By selling to 7421 at 9:50AM, we lost that shelf of lows. Shortly after at 9:55AM to 10:00AM ES recovered the 7435 shelf and we ripped nicely from there. We rallied nicely off this to 7450-55+ by 10:00AM.
Trade Plan Monday
Supports are: 7442, 7435 (major), 7427, 7421 (major), 7414, 7410, 7398 (major).
Resistances are: 7449, 7458 (major), 7469, 7472 (major).
As always no crystal balls.

Unsubscribe https://example.com/unsub"""

result = parse_email(sample, date="2026-05-15", subject="Test")

print(f"Slides: {len(result.slides)}")
print(f"{'─' * 80}")
for i, slide in enumerate(result.slides):
    print(f"\n  Slide {i+1}: [{slide.section}] @ {slide.time_anchor or '(inherited)'}")
    print(f"  Prices: {slide.price_levels}")
    print(f"  Text: {slide.sentence[:100]}...")

# Generate frames using the real chart as a stand-in for all slides
chart = Path('/mnt/c/myStuff/tvscreen.jpg')
config = FrameConfig(
    overlay_width_pct=0.30,
    chart_y_top=160,
    chart_y_bottom=917,
)

# Combine support + step-specific levels for overlay
all_levels = result.support_levels

frame_paths = []
for i, slide in enumerate(result.slides):
    frame = compose_frame(
        chart_path=chart,
        step=slide,
        levels=all_levels,
        price_min=7400,
        price_max=7530,
        config=config,
    )
    out = OUTPUT_DIR / f"slide_{i+1:02d}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.save(out)
    frame_paths.append(out)

index = generate_gallery(frame_paths, OUTPUT_DIR, title="Mancini Review — May 15")
print(f"\n{'─' * 80}")
print(f"Generated {len(frame_paths)} slides")
print(f"Gallery: {index}")
