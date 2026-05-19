"""CLI: parse Mancini email, emit Pine, compose visual slides, archive daily artifacts."""
from __future__ import annotations

import argparse
import sys
from datetime import date as _date
from pathlib import Path

from .parser import parse_email, match_captures
from .persist import save, load
from .pine_emitter import emit
from .replay import render_replay
from .post_mortem import render_post_mortem
from .compositor import compose_frame, FrameConfig
from .gallery import generate_gallery

ARCHIVE_ROOT = Path(__file__).parent / "archive"


def _archive_dir(date_str: str) -> Path:
    d = ARCHIVE_ROOT / date_str
    d.mkdir(parents=True, exist_ok=True)
    return d


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mancini forecast → windowed Pine codegen")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--email", help="Path to plaintext email body")
    src.add_argument("--from-json", help="Path to saved ManciniEmail JSON (intraday re-emit)")

    ap.add_argument("--date", default="", help="Forecast date (YYYY-MM-DD) — used when parsing email")
    ap.add_argument("--subject", default="", help="Email subject — used when parsing email")
    ap.add_argument("--onh", type=float, help="Overnight high (ES). Optional: when set with --onl, applies a hard pre-filter; otherwise Pine handles visibility at runtime via activation toggles.")
    ap.add_argument("--onl", type=float, help="Overnight low (ES). Pair with --onh to enable pre-filter.")
    ap.add_argument("--pad", type=float, default=40.0, help="Points to extend above ONH / below ONL when pre-filtering (default 40)")
    ap.add_argument("--out", help="Output .pine path (default: archive/<date>/forecast_<date>.pine)")
    ap.add_argument("--save-json", help="Write ManciniEmail JSON (default: archive/<date>/forecast_<date>.json when parsing email)")
    ap.add_argument("--no-archive", action="store_true", help="Skip auto-archiving JSON alongside Pine output")
    ap.add_argument("--replay", action="store_true", help="Generate session replay from trade recap slides")
    ap.add_argument("--replay-all", action="store_true", help="Include methodology/teaching slides in replay")
    ap.add_argument("--post-mortem", help="Path to prior day's forecast JSON — generates post-mortem slides comparing forecast vs actual")
    ap.add_argument("--slides", action="store_true", help="Compose visual PNG slides from trade recap + chart screenshots")
    ap.add_argument("--captures", help="Directory of chart screenshots (ES_HHMM.png or YYYYMMDD_HHMM.png)")
    ap.add_argument("--price-min", type=float, help="Chart price axis minimum (for level overlay calibration)")
    ap.add_argument("--price-max", type=float, help="Chart price axis maximum")
    ap.add_argument("--chart-y-top", type=int, default=0, help="Pixel Y of highest price on chart screenshots")
    ap.add_argument("--chart-y-bottom", type=int, default=0, help="Pixel Y of lowest price on chart screenshots")

    args = ap.parse_args(argv)

    forecast_date = args.date or str(_date.today())

    if args.email:
        text = Path(args.email).read_text()
        email = parse_email(text, date=forecast_date, subject=args.subject)

        json_path = args.save_json
        if not json_path and not args.no_archive:
            json_path = str(_archive_dir(forecast_date) / f"forecast_{forecast_date}.json")
        if json_path:
            Path(json_path).parent.mkdir(parents=True, exist_ok=True)
            save(email, json_path)
            print(f"saved extraction → {json_path}", file=sys.stderr)
    else:
        email = load(args.from_json)
        forecast_date = email.date or forecast_date

    if args.onh is not None and args.onl is not None:
        window_high = args.onh + args.pad
        window_low = args.onl - args.pad
        window_desc = f"pre-filter window {window_low}-{window_high}"
    else:
        window_high = window_low = None
        window_desc = "no pre-filter (Pine controls visibility)"

    out_path = args.out or str(_archive_dir(forecast_date) / f"forecast_{forecast_date}.pine")
    pine_src = emit(email, window_low=window_low, window_high=window_high)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(pine_src)

    n_total = len(email.support_levels) + len(email.resistance_levels)
    print(
        f"wrote {out_path} ({window_desc}, {n_total} published levels)",
        file=sys.stderr,
    )

    if args.replay or args.replay_all:
        replay_text = render_replay(email, action_only=not args.replay_all)
        replay_path = _archive_dir(forecast_date) / f"replay_{forecast_date}.md"
        replay_path.write_text(replay_text)
        print(f"wrote {replay_path} ({len(email.slides)} slides)", file=sys.stderr)

    if args.post_mortem:
        prior = load(args.post_mortem)
        pm_text = render_post_mortem(prior, email)
        pm_path = _archive_dir(forecast_date) / f"post_mortem_{forecast_date}.md"
        pm_path.write_text(pm_text)
        n_prior = len(prior.support_levels) + len(prior.resistance_levels)
        print(f"wrote {pm_path} (prior: {n_prior} levels)", file=sys.stderr)

    if args.slides:
        if not args.captures:
            print("error: --slides requires --captures <dir>", file=sys.stderr)
            return 1
        if not args.price_min or not args.price_max:
            print("error: --slides requires --price-min and --price-max", file=sys.stderr)
            return 1

        slides = match_captures(email.slides, args.captures, date=forecast_date)
        action_slides = [s for s in slides if s.price_levels or s.direction in ("sell", "rip")]
        if not action_slides:
            action_slides = slides

        all_levels = email.support_levels + email.resistance_levels
        config = FrameConfig(
            overlay_width_pct=0.30,
            chart_y_top=args.chart_y_top,
            chart_y_bottom=args.chart_y_bottom,
        )

        slides_dir = _archive_dir(forecast_date) / "slides"
        slides_dir.mkdir(parents=True, exist_ok=True)

        frame_paths = []
        skipped = 0
        for i, slide in enumerate(action_slides):
            if not slide.capture_file or not Path(slide.capture_file).exists():
                skipped += 1
                continue
            frame = compose_frame(
                chart_path=Path(slide.capture_file),
                step=slide,
                levels=all_levels,
                price_min=args.price_min,
                price_max=args.price_max,
                config=config,
            )
            out = slides_dir / f"slide_{i + 1:03d}.png"
            frame.save(out)
            frame_paths.append(out)

        if frame_paths:
            gallery_path = generate_gallery(frame_paths, slides_dir, title=f"Mancini Review — {forecast_date}")
            print(f"wrote {len(frame_paths)} slide PNGs → {slides_dir}/ (skipped {skipped} without captures)", file=sys.stderr)
            print(f"gallery → {gallery_path}", file=sys.stderr)
        else:
            print(f"no slides generated (0 captures matched, {skipped} skipped)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
