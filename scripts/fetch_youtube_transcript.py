#!/usr/bin/env python3
"""Fetch a YouTube auto-caption transcript and write it as .json + timestamped .txt.

Usage:
    fetch_youtube_transcript.py <video_url_or_id> <output_basename>

Output:
    <basename>.json — raw {start, duration, text} entries
    <basename>.txt  — readable transcript with [MM:SS] markers every ~60s

Exit codes:
    0 success, 2 bad args, 3 transcript unavailable, 4 network/IO error.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)


def extract_video_id(s: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    u = urlparse(s)
    if u.netloc.endswith("youtu.be"):
        return u.path.lstrip("/").split("/")[0]
    q = parse_qs(u.query)
    if "v" in q:
        return q["v"][0]
    m = re.search(r"/(?:embed|shorts)/([A-Za-z0-9_-]{11})", u.path)
    if m:
        return m.group(1)
    raise ValueError(f"could not extract video id from: {s!r}")


def fetch(video_id: str) -> list[dict]:
    api = YouTubeTranscriptApi()
    fetched = api.fetch(video_id)
    return [
        {"start": s.start, "duration": s.duration, "text": s.text}
        for s in fetched.snippets
    ]


def format_timestamped_text(snippets: list[dict], stride_seconds: int = 60) -> str:
    """One paragraph per `stride_seconds` block; [MM:SS] marker at start of each."""
    if not snippets:
        return ""
    out_lines: list[str] = []
    current_block: list[str] = []
    current_marker = 0
    next_threshold = stride_seconds

    for snip in snippets:
        start = snip["start"]
        text = snip["text"].strip().replace("\n", " ")
        if start >= next_threshold and current_block:
            mm, ss = divmod(int(current_marker), 60)
            out_lines.append(f"[{mm:02d}:{ss:02d}] " + " ".join(current_block))
            current_block = []
            current_marker = next_threshold
            while start >= next_threshold:
                next_threshold += stride_seconds
        if not current_block:
            current_marker = max(current_marker, int(start) // stride_seconds * stride_seconds)
        current_block.append(text)

    if current_block:
        mm, ss = divmod(int(current_marker), 60)
        out_lines.append(f"[{mm:02d}:{ss:02d}] " + " ".join(current_block))

    return "\n\n".join(out_lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    src, basename = argv[1], argv[2]
    try:
        vid = extract_video_id(src)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    try:
        snippets = fetch(vid)
    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as e:
        print(f"transcript unavailable for {vid}: {type(e).__name__}", file=sys.stderr)
        return 3
    except Exception as e:
        print(f"fetch failed for {vid}: {e}", file=sys.stderr)
        return 4

    out_base = Path(basename)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    out_base.with_suffix(".json").write_text(
        json.dumps(snippets, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    out_base.with_suffix(".txt").write_text(
        format_timestamped_text(snippets), encoding="utf-8"
    )
    duration = snippets[-1]["start"] + snippets[-1]["duration"] if snippets else 0
    mm, ss = divmod(int(duration), 60)
    print(f"wrote {out_base.with_suffix('.json')}")
    print(f"wrote {out_base.with_suffix('.txt')}")
    print(f"video {vid}: {len(snippets)} snippets, ~{mm:02d}:{ss:02d} duration")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
