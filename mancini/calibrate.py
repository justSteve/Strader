"""
Calibrate price-to-Y mapping from a real TradingView screenshot.

Reads the right-side price axis to find known price/Y-pixel pairs,
then derives the linear mapping for level overlay.
"""
import sys
sys.path.insert(0, '/root/projects/Strader')

from PIL import Image, ImageDraw
from pathlib import Path

img = Image.open('/mnt/c/myStuff/tvscreen.jpg')
w, h = img.size

# Sample a vertical strip from the price axis area (right ~80px)
# The price labels sit roughly at x=890-940 in this 1920px image
# Let's scan for the bright text pixels in the axis region
axis_x_start = w - 80
axis_x_end = w - 10

# Scan each row for bright pixels in the axis zone
# Price text is typically white/light on dark background
bright_rows = []
for y in range(0, h):
    row_brightness = 0
    count = 0
    for x in range(axis_x_start, axis_x_end):
        r, g, b = img.getpixel((x, y))[:3]
        if r > 150 and g > 150 and b > 150:
            row_brightness += r + g + b
            count += 1
    if count > 5:
        bright_rows.append((y, count, row_brightness))

# Cluster bright rows into label regions
if bright_rows:
    print(f"Found {len(bright_rows)} bright rows in price axis region")
    print(f"Price axis X range: {axis_x_start}-{axis_x_end}")
    print(f"\nTop 30 brightest rows (y, pixel_count, total_brightness):")
    sorted_rows = sorted(bright_rows, key=lambda x: x[2], reverse=True)
    for y, count, bright in sorted_rows[:30]:
        print(f"  y={y:4d}  pixels={count:3d}  brightness={bright:6d}")

# Also extract a thin vertical strip to visualize the axis
strip = img.crop((axis_x_start, 0, axis_x_end, h))
strip_path = Path('/root/projects/Strader/mancini/output/price_axis_strip.png')
strip.save(strip_path)
print(f"\nPrice axis strip saved to {strip_path}")

# Save a wider strip for visual inspection
wide_strip = img.crop((w - 120, 40, w, h - 40))
wide_path = Path('/root/projects/Strader/mancini/output/price_axis_wide.png')
wide_strip.save(wide_path)
print(f"Wide axis strip saved to {wide_path}")
