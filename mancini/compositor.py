"""
Composite Mancini review frames: full-frame chart + level overlays + text inset.

Layout:
- Chart image fills entire frame
- Mancini's levels drawn as horizontal lines with left-aligned labels
- Commentary box overlays upper-left, 30% width, semi-transparent background
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from dataclasses import dataclass

from .parser import ReviewStep, Slide, Level


@dataclass
class FrameConfig:
    overlay_width_pct: float = 0.30
    overlay_padding: int = 16
    overlay_bg_color: tuple = (10, 10, 10, 230)  # near-opaque dark
    overlay_text_color: tuple = (255, 255, 255, 255)
    level_line_color_major: tuple = (255, 180, 0, 190)  # amber, 75%
    level_line_color_minor: tuple = (180, 180, 180, 190)  # gray, 75%
    level_label_size: int = 18
    overlay_title_size: int = 28
    overlay_body_size: int = 20
    level_line_width_major: int = 3
    level_line_width_minor: int = 2
    chart_y_top: int = 0
    chart_y_bottom: int = 0


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """Try to load a monospace font, fall back to default."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def price_to_y(price: float, price_min: float, price_max: float,
               img_height: int, chart_y_top: int = 0, chart_y_bottom: int = 0) -> int:
    """Map a price to a Y pixel coordinate. Higher price = lower Y (chart convention).

    chart_y_top/chart_y_bottom define the pixel bounds of the chart's price range.
    If not set, defaults to 40px margins.
    """
    if chart_y_top == 0 and chart_y_bottom == 0:
        chart_y_top = 40
        chart_y_bottom = img_height - 40
    usable_height = chart_y_bottom - chart_y_top
    if price_max == price_min:
        return img_height // 2
    ratio = (price - price_min) / (price_max - price_min)
    return chart_y_top + int((1.0 - ratio) * usable_height)


def draw_levels(img: Image.Image, levels: list[Level],
                price_min: float, price_max: float,
                config: FrameConfig = FrameConfig()) -> Image.Image:
    """Draw horizontal level lines with left-aligned labels on the chart image."""
    draw = ImageDraw.Draw(img, 'RGBA')
    font = _get_font(config.level_label_size)
    label_x = 8

    for level in levels:
        if not (price_min <= level.price <= price_max):
            continue

        y = price_to_y(level.price, price_min, price_max, img.height,
                      config.chart_y_top, config.chart_y_bottom)
        is_major = "major" in level.annotation.lower() if level.annotation else False
        color = config.level_line_color_major if is_major else config.level_line_color_minor
        width = config.level_line_width_major if is_major else config.level_line_width_minor

        draw.line([(0, y), (img.width, y)], fill=color, width=width)

        label = f"{int(level.price)}"
        if level.annotation:
            label += f" ({level.annotation})"
        bbox = font.getbbox(label)
        text_h = bbox[3] - bbox[1]
        draw.rectangle(
            [label_x - 2, y - text_h - 6, label_x + bbox[2] - bbox[0] + 6, y + 2],
            fill=(10, 10, 10, 240)
        )
        draw.text((label_x, y - text_h - 3), label, fill=color, font=font)

    return img


def draw_overlay(img: Image.Image, step: ReviewStep | Slide,
                 config: FrameConfig = FrameConfig()) -> Image.Image:
    """Draw the commentary overlay box in upper-left corner."""
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    box_width = int(img.width * config.overlay_width_pct)
    pad = config.overlay_padding

    title_font = _get_font(config.overlay_title_size)
    body_font = _get_font(config.overlay_body_size)

    if isinstance(step, Slide):
        title_text = step.section
        if step.time_anchor:
            title_text += f"  [{step.time_anchor}]"
        body_source = step.sentence
    else:
        title_text = step.title
        if step.time_anchor:
            title_text += f"  [{step.time_anchor}]"
        body_source = step.text_excerpt

    body_text = _wrap_text(body_source, body_font, box_width - 2 * pad)

    title_bbox = title_font.getbbox(title_text)
    title_h = title_bbox[3] - title_bbox[1] + 8

    lines = body_text.split('\n')
    line_h = body_font.getbbox("Ag")[3] - body_font.getbbox("Ag")[1] + 4
    body_h = line_h * min(len(lines), 20)  # cap at 20 lines

    box_height = pad + title_h + 8 + body_h + pad
    box_x, box_y = 12, 12

    draw.rounded_rectangle(
        [box_x, box_y, box_x + box_width, box_y + box_height],
        radius=8,
        fill=config.overlay_bg_color
    )

    draw.text(
        (box_x + pad, box_y + pad),
        title_text,
        fill=(255, 220, 100, 255),
        font=title_font
    )

    y_cursor = box_y + pad + title_h + 8
    for i, line in enumerate(lines[:20]):
        draw.text(
            (box_x + pad, y_cursor + i * line_h),
            line,
            fill=config.overlay_text_color,
            font=body_font
        )

    return Image.alpha_composite(img.convert('RGBA'), overlay)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test = f"{current_line} {word}".strip()
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)
    return '\n'.join(lines)


def compose_frame(chart_path: Path, step: ReviewStep | Slide,
                  levels: list[Level], price_min: float, price_max: float,
                  config: FrameConfig = FrameConfig()) -> Image.Image:
    """Compose a single review frame: chart + levels + overlay."""
    img = Image.open(chart_path).convert('RGBA')
    img = draw_levels(img, levels, price_min, price_max, config)
    img = draw_overlay(img, step, config)
    return img.convert('RGB')
