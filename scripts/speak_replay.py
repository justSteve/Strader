#!/usr/bin/env python3
"""Render a stored replay signal stream as speech — read it, or hear it.

The phrasebook (``present/speech.py``, st-mhkp) is a pure function. This script
is how you judge it: point it at a day the recognizer already replayed and see
the sentences it would have spoken, in order, against real signals rather than
invented examples.

    # read the day
    python scripts/speak_replay.py data/measurement/replay/signals_2026-07-24.jsonl

    # only the calls that would actually interrupt you
    python scripts/speak_replay.py <file> --confirmed-only

    # hear it
    python scripts/speak_replay.py <file> --confirmed-only --wav /var/moo/drill.wav

Deliberately offline: it reads stored records and never touches a live feed.
Nothing consumes signals in a live loop today, and replay is where the wording
should be argued out anyway — before there is money on the outcome.

Bead: st-mhkp. Audio substrate proven under COO co-fsg5p.
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market.signals.types import Bias, Regime, Level, Alert, Action  # noqa: E402
from market.signals.orderflow import (  # noqa: E402
    SweepPrint, DeltaDivergence, ImbalanceStack, AbsorptionRead, SetupRecognition,
)
from present.speech import speak  # noqa: E402

log = logging.getLogger("speak_replay")

# Record "type" field -> dataclass. Types absent here (RunMeta, DayType) are
# run bookkeeping, not signals, and are skipped rather than guessed at.
_TYPES = {
    "SweepPrint": SweepPrint,
    "DeltaDivergence": DeltaDivergence,
    "ImbalanceStack": ImbalanceStack,
    "AbsorptionRead": AbsorptionRead,
    "SetupRecognition": SetupRecognition,
    "Level": Level,
    "Bias": Bias,
    "Regime": Regime,
    "Alert": Alert,
    "Action": Action,
}

_SKIP = {"RunMeta", "DayType"}

# Fields carried in the record for provenance/debugging that are not part of
# the frozen Signal contract.
_NON_FIELDS = {"run", "n", "type", "bar_i"}


def _build(record: dict):
    """Reconstruct a Signal from one JSONL record, or None if it is not one."""
    kind = record.get("type")
    if kind in _SKIP or kind is None:
        return None

    cls = _TYPES.get(kind)
    if cls is None:
        log.warning("unknown record type %r at n=%s — skipped", kind, record.get("n"))
        return None

    fields = {k: v for k, v in record.items() if k not in _NON_FIELDS}
    try:
        fields["timestamp"] = datetime.fromisoformat(fields["timestamp"])
    except (KeyError, ValueError) as exc:
        log.warning("record n=%s has no usable timestamp (%s) — skipped",
                    record.get("n"), exc)
        return None

    # Tuple-typed fields arrive from JSON as lists; the dataclasses are frozen
    # and declare tuples.
    for key in ("beats", "prices", "ratios"):
        if isinstance(fields.get(key), list):
            fields[key] = tuple(fields[key])

    try:
        return cls(**fields)
    except TypeError as exc:
        log.warning("record n=%s does not fit %s (%s) — skipped",
                    record.get("n"), kind, exc)
        return None


def derive_fire_index(signals: list) -> list:
    """Fill in ``fire_index`` on confirmed setups that were serialized without it.

    Older replay streams predate the field [st-98z], and ``SetupRecognition``
    defaults it to 1. Left alone, that default makes the *third* confirm at a
    level speak exactly like the first — the specific misleading-voice failure
    the phrasing rule exists to prevent, and one that is invisible because a
    plausible sentence still comes out.

    Derivation matches ``scripts/acuity_run2.py``: per-anchor confirm sequence,
    counted in chronological confirm order, keyed on ``anchor_price``. Where the
    recognizer supplied the field it stays authoritative and is not touched.
    """
    counts: dict[float, int] = {}
    out = []
    for sig in signals:
        if isinstance(sig, SetupRecognition) and sig.state == "confirmed":
            counts[sig.anchor_price] = counts.get(sig.anchor_price, 0) + 1
            if getattr(sig, "_fire_index_absent", False):
                sig = replace(sig, fire_index=counts[sig.anchor_price])
        out.append(sig)
    return out


def load(path: Path) -> list:
    """Read a replay JSONL into Signal objects, skipping what is not one."""
    signals, derived = [], 0
    with path.open() as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                log.warning("%s:%d is not JSON (%s) — skipped", path.name, lineno, exc)
                continue
            sig = _build(record)
            if sig is None:
                continue
            if isinstance(sig, SetupRecognition) and "fire_index" not in record:
                object.__setattr__(sig, "_fire_index_absent", True)
                derived += 1
            signals.append(sig)

    signals = derive_fire_index(signals)
    if derived:
        log.warning(
            "%s did not serialize fire_index on %d setup(s) — derived it from "
            "confirm order per anchor. Without this the third fire at a level "
            "would have been spoken as if it were the first.",
            path.name, derived,
        )
    return signals


def synthesize(lines: list[str], wav: Path, voice: str, words_per_minute: int) -> bool:
    """Render spoken lines to a wav via espeak-ng. Returns False if unavailable."""
    engine = shutil.which("espeak-ng") or shutil.which("espeak")
    if engine is None:
        log.error("no espeak-ng on PATH — install it or drop --wav")
        return False

    # One blank line between utterances gives espeak a sentence break, which
    # is the difference between a list and a monologue.
    script = "\n\n".join(lines)
    wav.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [engine, "-v", voice, "-s", str(words_per_minute), "-w", str(wav)],
            input=script, text=True, check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        log.error("%s failed (rc=%s): %s", engine, exc.returncode, exc.stderr.strip())
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("jsonl", type=Path, help="a replay signal stream")
    ap.add_argument("--confirmed-only", action="store_true",
                    help="only confirmed setups — the calls that would interrupt you")
    ap.add_argument("--wav", type=Path, help="also synthesize to this wav")
    ap.add_argument("--voice", default="en-us")
    ap.add_argument("--wpm", type=int, default=160,
                    help="speaking rate; 160 is brisk but intelligible (default)")
    ap.add_argument("--limit", type=int, help="stop after N spoken lines")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(message)s",
    )

    if not args.jsonl.is_file():
        log.error("no such file: %s", args.jsonl)
        return 2

    signals = load(args.jsonl)
    if not signals:
        log.error("%s held no signals this script understands", args.jsonl)
        return 1

    if args.confirmed_only:
        signals = [s for s in signals
                   if isinstance(s, SetupRecognition) and s.state == "confirmed"]

    spoken, silent = [], 0
    for sig in signals:
        line = speak(sig)
        if line is None:
            silent += 1
            continue
        print(f"  {sig.timestamp:%H:%M:%S}  {line}")
        spoken.append(line)
        if args.limit and len(spoken) >= args.limit:
            break

    print()
    log.info("%d spoken, %d left silent (no phrasing), from %s",
             len(spoken), silent, args.jsonl.name)

    if args.wav:
        if not spoken:
            log.error("nothing to synthesize")
            return 1
        if not synthesize(spoken, args.wav, args.voice, args.wpm):
            return 1
        log.info("wrote %s (%.1f KB)", args.wav, args.wav.stat().st_size / 1024)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
