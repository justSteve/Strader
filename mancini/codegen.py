"""CLI: parse Mancini email or reload saved JSON, emit windowed Pine."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .parser import parse_email
from .persist import save, load
from .pine_emitter import emit


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
    ap.add_argument("--out", required=True, help="Output .pine path")
    ap.add_argument("--save-json", help="When parsing an email, also write the full ManciniEmail JSON here")

    args = ap.parse_args(argv)

    if args.email:
        text = Path(args.email).read_text()
        email = parse_email(text, date=args.date, subject=args.subject)
        if args.save_json:
            save(email, args.save_json)
            print(f"saved full extraction → {args.save_json}", file=sys.stderr)
    else:
        email = load(args.from_json)

    if args.onh is not None and args.onl is not None:
        window_high = args.onh + args.pad
        window_low = args.onl - args.pad
        window_desc = f"pre-filter window {window_low}-{window_high}"
    else:
        window_high = window_low = None
        window_desc = "no pre-filter (Pine controls visibility)"

    pine_src = emit(email, window_low=window_low, window_high=window_high)
    Path(args.out).write_text(pine_src)

    n_total = len(email.support_levels) + len(email.resistance_levels)
    print(
        f"wrote {args.out} ({window_desc}, {n_total} published levels)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
