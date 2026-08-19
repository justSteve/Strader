#!/usr/bin/env python3
"""coach.py — drive the footprint page through the bridge's coach channel. [st-135m]

The drill bridge (scripts/drill_bridge.py) exposes POST /coach; the page polls
GET /commands and applies each command. This is the operator's hand on that
channel — Steve, 2026-08-18: "seeing the functioning system being controlled by
someone who has already mastered the system"; and on the cursor: "a hover would
allow you to draw my eye to a specific place on the screen … a cursor would be
awesome."

Verbs (all live on the page as of st-135m):

    say   "text"                 caption at the top of the chart
    arm   PRICE                  arm a level line at PRICE
    jump  BAR [--text T]         seek the view to bar index BAR (replay pages)
    pause | play                 replay transport
    point --bar I --price P [--text T] [--pulse] [--hold SECONDS]
                                 the drawn cursor glides to bar I / price P;
                                 label T beside it; --pulse rings the cell;
                                 --hold auto-clears after SECONDS
    point --price P              same, on the newest bar (bar omitted = tip)
    clear                        remove the cursor, label and highlight

Examples:
    tools/coach.py point --bar 66 --price 7730.75 --text "POC of the 730-delta bar" --pulse
    tools/coach.py say "watch the next three bars"
    tools/coach.py clear

Bridge: --bridge (default $STRADER_BRIDGE or http://127.0.0.1:7788). Exit 0 on
{"ok": true}; 1 on any HTTP/JSON failure (message on stderr).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BRIDGE = os.environ.get("STRADER_BRIDGE") or "http://127.0.0.1:7788"


def send(bridge: str, cmd: dict, timeout: float = 3.0) -> dict:
    req = urllib.request.Request(
        bridge.rstrip("/") + "/coach",
        data=json.dumps(cmd).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — loopback bridge
        return json.loads(r.read().decode("utf-8") or "{}")


def build(args: argparse.Namespace) -> dict:
    v = args.verb
    if v == "say":
        return {"type": "say", "text": args.text}
    if v == "arm":
        return {"type": "arm", "price": args.price}
    if v == "jump":
        cmd = {"type": "jump", "bar": args.bar}
        if args.text:
            cmd["text"] = args.text
        return cmd
    if v in ("pause", "play"):
        return {"type": v}
    if v == "point":
        cmd: dict = {"type": "point", "price": args.price}
        if args.bar is not None:
            cmd["bar"] = args.bar
        if args.text:
            cmd["text"] = args.text
        if args.pulse:
            cmd["pulse"] = True
        if args.hold is not None:
            cmd["hold_ms"] = int(args.hold * 1000)
        return cmd
    if v == "clear":
        return {"type": "clear"}
    raise SystemExit(f"unknown verb {v!r}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bridge", default=DEFAULT_BRIDGE)
    sub = ap.add_subparsers(dest="verb", required=True)
    p = sub.add_parser("say"); p.add_argument("text")
    p = sub.add_parser("arm"); p.add_argument("price", type=float)
    p = sub.add_parser("jump"); p.add_argument("bar", type=int); p.add_argument("--text")
    sub.add_parser("pause"); sub.add_parser("play")
    p = sub.add_parser("point")
    p.add_argument("--price", type=float, required=True)
    p.add_argument("--bar", type=int, help="bar index (0-based, as the page counts); omit for the newest bar")
    p.add_argument("--text")
    p.add_argument("--pulse", action="store_true")
    p.add_argument("--hold", type=float, help="seconds until the cursor clears itself")
    sub.add_parser("clear")
    args = ap.parse_args(argv)
    cmd = build(args)
    try:
        out = send(args.bridge, cmd)
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"coach: bridge unreachable or refused ({e}) — {args.bridge}", file=sys.stderr)
        return 1
    if not out.get("ok"):
        print(f"coach: bridge said {out}", file=sys.stderr)
        return 1
    print(f"coach: {cmd['type']} #{out.get('id')} sent to {args.bridge}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
