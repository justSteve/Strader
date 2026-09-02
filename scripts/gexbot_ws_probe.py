#!/usr/bin/env python3
"""GexBot WebSocket payload probe — observe the feed we have only ever read about. [st-8qqw]

Every property of this feed in `docs/reports/2026-08-30-gexbot-websocket-and-the-state-move.md`
is DOCUMENTARY: read from the vendor's OpenAPI spec, AGENTS.md and websocket.md.
Verified 2026-08-30 — `negotiate` appears in no other .py or .sh in this repo, the
reference client was never cloned, and nothing in data/ holds a captured frame. This
script is the first time we open the socket.

It answers three questions on observation rather than on the vendor's say-so:

  1. What does a frame actually weigh, compressed and decompressed?
  2. What is the real cadence against the stated 1 Hz ceiling — and against the 62%
     our REST poller captures (measured 2026-08-27: 14,487 polls, median spacing
     2.0s across a ~23,470s session)?
  3. Is the payload decodable without the vendor's client? They publish no .proto in
     either repo, so this walks the protobuf wire format directly and reports which
     field numbers and types are recoverable.

SCOPE — deliberately narrow. Negotiate, join ONE group, capture, analyse, report.
It does not wire a collector, does not decode field semantics, and does not go near
the 150-group cap.

THE WINDOW CLOSES 2026-09-06. `/negotiate` is Quant-only and lapses with `/hist` on
09-07. Unlike the GEX archive there is no backfill argument here, because nothing was
ever captured; after that date the feed is permanently unknowable to us.

RTH ONLY, AND THE USABLE WINDOW IS FIVE SESSIONS WIDE. The vendor publishes only
08:30-15:00 CT ("Data is only published during New York Stock Exchange cash hours"),
so the entitlement's calendar end is not its usable end:

    Mon 2026-08-31 · Tue 09-01 · Wed 09-02 · Thu 09-03 · Fri 09-04

2026-09-05 and 09-06 fall on Saturday and Sunday — inside the entitlement, but the
feed publishes nothing on either. **Friday 2026-09-04 is the last session on which
this probe can ever run.** (`/hist` carries no such restriction, which is why
st-qcj3's hand sweep can and must still fall on that weekend.)

Outside the window the socket opens and stays silent — a true observation, but a
waste of a finite resource — so the probe refuses by default and `--force` is the
deliberate override.

Usage:
    .venv/bin/python3 scripts/gexbot_ws_probe.py                    # 120s, SPX state gamma zero
    .venv/bin/python3 scripts/gexbot_ws_probe.py --duration 300
    .venv/bin/python3 scripts/gexbot_ws_probe.py --group SPX_classic_gex_full
    .venv/bin/python3 scripts/gexbot_ws_probe.py --force            # outside RTH, on purpose

Artifacts land in data/probes/gexbot-ws/<run-id>/:
    negotiate.json   the response, ACCESS TOKENS REDACTED
    frames.bin       length-prefixed raw frames, exactly as they arrived
    frames.jsonl     one index row per frame (seq, wall, offset, opcode, bytes)
    report.md        the analysis
    probe.log        the run log

Exit codes:
    0  captured and analysed
    2  usage / preflight refusal (outside RTH without --force, no key)
    3  negotiate failed (401/403 = key or tier; the tier answer matters after 09-06)
    4  connected but no frames arrived within the window
    5  network / transport failure
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import signal
import statistics
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://api.gex.bot/v2"
USER_AGENT = "Strader-WSProbe/1.0 (st-8qqw)"
PROBE_ROOT = ROOT / "data" / "probes" / "gexbot-ws"

# Matches scripts/gexbot_probe.py: cold TLS handshake plus any IPv6/IPv4 fallback
# does not fit inside the spec's 1s steady-state polling guidance.
HTTP_TIMEOUT_S = 10.0
# WSL on this distro returns ENETUNREACH on IPv6; binding the local socket to the
# IPv4 any-address forces IPv4-only. Carried from scripts/gexbot_probe.py, same cause.
LOCAL_ADDR_V4 = "0.0.0.0"

# The vendor's publish window, in Central. websocket.md states it as NYSE cash hours.
# ZoneInfo rather than a fixed offset: a hardcoded -5 is CDT and silently becomes an
# hour wrong at the November DST boundary. The entitlement dies well before that, but
# a probe that lies about its own clock is worse than one that refuses to run.
CT = ZoneInfo("America/Chicago")
RTH_OPEN = (8, 30)
RTH_CLOSE = (15, 0)

# One group. The default is the front-expiry gamma ladder — the series the 08-30
# brief showed we cannot resolve at our 60s state cadence (major_long_gamma differed
# from its previous sample 50% of the time), so it is the one where a push feed has
# the most to prove.
DEFAULT_GROUP = "SPX_state_gamma_zero"

# Which hub serves which group suffix. From websocket.md's six hubs; the negotiate
# response is authoritative and this is only used to pick one URL out of it.
HUB_FOR_CATEGORY = {
    "gex_full": "classic", "gex_zero": "classic", "gex_one": "classic",
    "gex": "state_gex",
    "orderflow": "orderflow",
}

# Measured on our own REST capture, 2026-08-27 RTH (the 08-30 brief, section 3).
# Carried here so the report can state the comparison without a second lookup.
REST_BASELINE = {
    "session": "2026-08-27",
    "polls": 14487,
    "median_spacing_s": 2.0,
    "mean_spacing_s": 1.62,
    "session_span_s": 23470,
    "capture_fraction": 0.62,
}

TOKEN_RE = re.compile(r"(access_token=)[^&\s\"']+")

log = logging.getLogger("gexbot_ws_probe")


# ---------------------------------------------------------------- helpers ----

def redact(text: str) -> str:
    """Strip access tokens from anything headed for disk or the log.

    The negotiate response embeds a bearer token in every hub URL. Those URLs are
    worth keeping — the token is not, and an artifact directory is not a secret
    store. Redaction is applied at every boundary rather than at the write site,
    so a new print statement cannot leak one by omission.
    """
    return TOKEN_RE.sub(r"\1<REDACTED>", text)


def load_env() -> dict[str, str]:
    """Read KEY=VALUE from .env beside the repo root. Existing environment wins."""
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.split("#", 1)[0].strip()
    return env


def bearer(api_key: str) -> str:
    """Per the spec README the secret carries a `gexbot_custom_` prefix.

    A key dropped into .env with the prefix already attached must not be doubled —
    same guard as scripts/gexbot_probe.py.
    """
    token = api_key if api_key.startswith("gexbot_custom_") else f"gexbot_custom_{api_key}"
    return f"Bearer {token}"


def in_rth(now: datetime) -> bool:
    """Is `now` inside the vendor's publish window (08:30-15:00 CT, weekdays)?

    Deliberately ignores market holidays: the probe's failure mode outside the
    window is silence, which --force already covers, and a holiday calendar that
    goes stale would refuse a run on a day the feed was live.
    """
    local = now.astimezone(CT)
    if local.weekday() >= 5:
        return False
    open_t = local.replace(hour=RTH_OPEN[0], minute=RTH_OPEN[1], second=0, microsecond=0)
    close_t = local.replace(hour=RTH_CLOSE[0], minute=RTH_CLOSE[1], second=0, microsecond=0)
    return open_t <= local <= close_t


def hub_for_group(group: str, available: dict[str, str]) -> tuple[str, str]:
    """Pick the hub URL serving `group` out of the negotiate response.

    Group names are `{ticker}_{package}_{category}` — but tickers themselves contain
    underscores (`ES_SPX_orderflow_orderflow`), so splitting on `_` and counting is
    wrong. Match on the package token instead, which is one of exactly three values.
    """
    parts = group.split("_")
    package = next((p for p in parts if p in ("classic", "state", "orderflow")), None)
    if package is None:
        raise ValueError(
            f"group {group!r} names no package; expected one of classic/state/orderflow"
        )
    idx = parts.index(package)
    category = "_".join(parts[idx + 1:])

    if package == "orderflow":
        hub = "orderflow"
    elif package == "classic":
        hub = "classic"
    else:
        # state: the greeks split across three hubs by expiry ordinal, and the
        # plain gex ladder has its own. Suffix decides.
        if category.endswith("_zero"):
            hub = "state_greeks_zero"
        elif category.endswith("_one"):
            hub = "state_greeks_one"
        elif category.startswith("gex"):
            hub = "state_gex"
        else:
            hub = "state_greeks"

    if hub not in available:
        raise KeyError(
            f"negotiate authorized no {hub!r} hub for this key "
            f"(got {sorted(available)}) — the group may be outside the entitlement"
        )
    return hub, available[hub]


# ------------------------------------------------------------ wire format ----

def read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    """Return (value, new_pos). Raises ValueError on a truncated or overlong varint."""
    result = 0
    shift = 0
    start = pos
    while True:
        if pos >= len(buf):
            raise ValueError(f"truncated varint at offset {start}")
        if shift > 63:
            raise ValueError(f"varint longer than 64 bits at offset {start}")
        byte = buf[pos]
        result |= (byte & 0x7F) << shift
        pos += 1
        if not byte & 0x80:
            return result, pos
        shift += 7


def walk_protobuf(buf: bytes, depth: int = 0, max_depth: int = 3) -> dict[str, Any]:
    """Walk a protobuf message's top level without a schema.

    Protobuf is NOT self-describing — the wire format carries field NUMBERS and
    wire TYPES, never names. So the honest answer this returns is 'the structure is
    recoverable, the semantics are not', and whether that suffices depends on
    whether the recovered field count lines up with a known REST schema.

    Returns {"ok": bool, "fields": {num: {...}}, "error": str|None, "consumed": int}.
    A message that consumes exactly to EOF with only valid wire types is
    well-formed; random bytes essentially never are, which makes this a usable
    detector as well as a describer.

    RECURSES into length-delimited fields. Measured on days 1 and 2 the payload
    is a two-field ENVELOPE — an 11-byte field 1 and a ~1.1 KB field 2 — so a
    top-level-only walk answers "it is a wrapper" and stops exactly where the
    question gets interesting. A nested field that itself walks clean to EOF is
    reported under ``message``; one that does not is a string or a blob, which
    is equally an answer. Depth-capped because a long ASCII string can parse as
    a plausible message by chance, and unbounded recursion on chance matches
    turns a describer into a fiction.
    """
    fields: dict[int, dict[str, Any]] = {}
    pos = 0
    try:
        while pos < len(buf):
            key, pos = read_varint(buf, pos)
            field_no, wire = key >> 3, key & 0x07
            if field_no == 0:
                raise ValueError(f"field number 0 at offset {pos}")
            entry = fields.setdefault(
                field_no, {"wire_type": wire, "count": 0, "bytes": 0}
            )
            entry["count"] += 1
            if wire == 0:
                val, pos = read_varint(buf, pos)
                entry.setdefault("sample", val)
            elif wire == 1:
                if pos + 8 > len(buf):
                    raise ValueError(f"truncated 64-bit field at {pos}")
                entry.setdefault("sample", struct.unpack_from("<d", buf, pos)[0])
                pos += 8
                entry["bytes"] += 8
            elif wire == 2:
                length, pos = read_varint(buf, pos)
                if pos + length > len(buf):
                    raise ValueError(f"length-delimited field overruns buffer at {pos}")
                entry["bytes"] += length
                entry.setdefault("sample_len", length)
                blob = buf[pos:pos + length]
                if "sample_bytes" not in entry:
                    entry["sample_bytes"] = blob[:24].hex()
                    printable = all(32 <= b < 127 for b in blob) if blob else False
                    if printable:
                        entry["sample_text"] = blob.decode("ascii", "replace")
                if depth < max_depth and length and "message" not in entry:
                    inner = walk_protobuf(blob, depth + 1, max_depth)
                    if inner["ok"] and inner["fields"]:
                        entry["message"] = {
                            n: {k: v for k, v in meta.items() if k != "count"}
                            for n, meta in sorted(inner["fields"].items())
                        }
                pos += length
            elif wire == 5:
                if pos + 4 > len(buf):
                    raise ValueError(f"truncated 32-bit field at {pos}")
                entry.setdefault("sample", struct.unpack_from("<f", buf, pos)[0])
                pos += 4
                entry["bytes"] += 4
            else:
                # 3 and 4 are the deprecated group markers; 6 and 7 are invalid.
                raise ValueError(f"unsupported wire type {wire} for field {field_no}")
    except ValueError as exc:
        return {"ok": False, "fields": fields, "error": str(exc), "consumed": pos}
    return {"ok": True, "fields": fields, "error": None, "consumed": pos}


ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


def _unzstd(blob: bytes) -> bytes | None:
    """Decompress a zstd frame, streaming when it carries no content size."""
    import zstandard

    try:
        return zstandard.ZstdDecompressor().decompress(blob)
    except zstandard.ZstdError:
        # GexBot's frames omit the content size in the header, so the one-shot
        # API refuses them. Streaming has no such requirement.
        try:
            return zstandard.ZstdDecompressor().stream_reader(blob).read()
        except zstandard.ZstdError:
            return None


def unwrap(payload: bytes) -> tuple[bytes | None, str, str | None]:
    """Return (message_bytes, how, type_name) for one wire frame.

    CORRECTED 2026-09-01, and the correction matters more than the fix. The
    first version tested only the FRAME's leading bytes for the zstd magic,
    found plain protobuf, and reported "uncompressed" for every frame across
    two sessions — which read as falsifying the vendor's documented
    "Zstandard-compressed Protocol Buffers". The vendor was right and the
    probe was wrong.

    The real shape, measured on 221 frames: the frame is a plain two-field
    protobuf ENVELOPE — field 1 an ASCII type name (``proto.greek``), field 2
    a zstd frame holding the actual message. So the compression is one level
    in, exactly where a frame-level magic check cannot see it.

    Worth stating as a rule: a negative result from a detector that only looks
    at offset zero is a statement about the detector until something has
    looked inside.
    """
    if payload[:4] == ZSTD_MAGIC:
        raw = _unzstd(payload)
        return (raw, "zstd-frame", None) if raw else (None, "zstd-failed", None)

    env = walk_protobuf(payload, max_depth=0)
    if env["ok"] and set(env["fields"]) == {1, 2}:
        name = env["fields"][1].get("sample_text")
        inner = env["fields"][2].get("sample_bytes", "")
        if inner.startswith("28b52ffd"):
            blob = _envelope_field(payload, 2)
            raw = _unzstd(blob) if blob else None
            if raw:
                return raw, "envelope+zstd", name
            return None, "envelope+zstd-failed", name
    return payload, "uncompressed", None


def _envelope_field(payload: bytes, want: int) -> bytes | None:
    """Slice one top-level length-delimited field out of the envelope."""
    pos = 0
    while pos < len(payload):
        try:
            key, pos = read_varint(payload, pos)
            if key & 0x07 != 2:
                return None
            length, pos = read_varint(payload, pos)
        except ValueError:
            return None
        if key >> 3 == want:
            return payload[pos:pos + length]
        pos += length
    return None


def decompress(payload: bytes) -> tuple[bytes | None, str]:
    """Back-compatible shim: the two-value form the analysis loop expects."""
    raw, how, _name = unwrap(payload)
    return raw, how


# ---------------------------------------------------------------- capture ----

class FrameSink:
    """Length-prefixed frame container plus a jsonl index.

    One file per frame would be simplest but produces thousands of inodes across a
    session-length run. Length-prefixing keeps the bytes exactly as they arrived —
    the point of the exercise — while the index stays greppable.
    """

    def __init__(self, out_dir: Path):
        self.bin_path = out_dir / "frames.bin"
        self.idx_path = out_dir / "frames.jsonl"
        self._bin = self.bin_path.open("wb")
        self._idx = self.idx_path.open("w", encoding="utf-8")
        self.offset = 0
        self.seq = 0
        self.records: list[dict[str, Any]] = []

    def write(self, payload: bytes, *, opcode: str, t_wall: datetime, t_mono: float) -> None:
        self.seq += 1
        self._bin.write(struct.pack(">I", len(payload)))
        self._bin.write(payload)
        row = {
            "seq": self.seq,
            "wall_ct": t_wall.astimezone(CT).isoformat(timespec="milliseconds"),
            "t_mono": round(t_mono, 4),
            "opcode": opcode,
            "n_bytes": len(payload),
            "offset": self.offset,
        }
        self.records.append(row)
        self._idx.write(json.dumps(row) + "\n")
        self.offset += 4 + len(payload)

    def close(self) -> None:
        self._bin.close()
        self._idx.close()

    def iter_payloads(self) -> Iterator[bytes]:
        with self.bin_path.open("rb") as fh:
            while True:
                head = fh.read(4)
                if len(head) < 4:
                    return
                (n,) = struct.unpack(">I", head)
                yield fh.read(n)


async def capture(url: str, sink: FrameSink, duration: float, stop: asyncio.Event) -> None:
    """Connect raw and record every frame for `duration` seconds.

    No Azure subprotocol is requested. The vendor's POST flow auto-joins groups
    server-side and says explicitly not to call client-side joinGroup, so the
    simple-client mode is correct: frames arrive as the vendor sent them, which is
    what we are here to look at. Asking for `json.webpubsub.azure.v1` would wrap
    every payload in an envelope and defeat the purpose.
    """
    import websockets

    deadline = time.monotonic() + duration
    async with websockets.connect(
        url,
        open_timeout=20,
        ping_interval=20,
        ping_timeout=20,
        max_size=None,  # never truncate a frame we are trying to measure
    ) as ws:
        log.info("connected; capturing for %.0fs", duration)
        t0 = time.monotonic()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or stop.is_set():
                break
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5.0))
            except asyncio.TimeoutError:
                continue
            now = time.monotonic()
            if isinstance(msg, str):
                payload, opcode = msg.encode("utf-8"), "text"
            else:
                payload, opcode = msg, "binary"
            sink.write(payload, opcode=opcode, t_wall=datetime.now(timezone.utc),
                       t_mono=now - t0)
            if sink.seq % 50 == 0:
                log.info("  %d frames, %d bytes", sink.seq, sink.offset)


# --------------------------------------------------------------- analysis ----

def spacings(records: list[dict[str, Any]]) -> list[float]:
    return [
        round(b["t_mono"] - a["t_mono"], 4)
        for a, b in zip(records, records[1:])
    ]


def analyse(sink: FrameSink, group: str, duration: float) -> dict[str, Any]:
    """Answer the three questions from the captured bytes."""
    rows = sink.records
    sizes = [r["n_bytes"] for r in rows]
    gaps = spacings(rows)

    decomp_ok = 0
    methods: dict[str, int] = {}
    decomp_sizes: list[int] = []
    pb_ok = 0
    pb_fields: dict[int, dict[str, Any]] = {}
    pb_errors: dict[str, int] = {}

    for payload in sink.iter_payloads():
        if not payload:
            continue
        raw, how = decompress(payload)
        methods[how.split(":")[0]] = methods.get(how.split(":")[0], 0) + 1
        if raw is None:
            continue
        decomp_ok += 1
        decomp_sizes.append(len(raw))
        walked = walk_protobuf(raw)
        if walked["ok"]:
            pb_ok += 1
            for num, meta in walked["fields"].items():
                slot = pb_fields.setdefault(
                    num, {"wire_type": meta["wire_type"], "seen": 0}
                )
                slot["seen"] += 1
                if "sample" in meta and "sample" not in slot:
                    slot["sample"] = meta["sample"]
                if "sample_len" in meta and "sample_len" not in slot:
                    slot["sample_len"] = meta["sample_len"]
        else:
            key = walked["error"].split(" at ")[0]
            pb_errors[key] = pb_errors.get(key, 0) + 1

    def stats(xs: list[float]) -> dict[str, float] | None:
        if not xs:
            return None
        return {
            "min": min(xs), "median": statistics.median(xs),
            "mean": round(statistics.fmean(xs), 4), "max": max(xs), "n": len(xs),
        }

    observed_hz = (len(rows) / duration) if duration > 0 else 0.0
    return {
        "group": group,
        "duration_s": duration,
        "frames": len(rows),
        "observed_hz": round(observed_hz, 3),
        "total_bytes": sink.offset,
        "frame_bytes": stats([float(s) for s in sizes]),
        "spacing_s": stats(gaps),
        "spacing_histogram": _histogram(gaps),
        "decompression": {
            "attempted": len(rows), "succeeded": decomp_ok, "methods": methods,
            "decompressed_bytes": stats([float(s) for s in decomp_sizes]),
            "ratio": (
                round(statistics.fmean(decomp_sizes) / statistics.fmean(sizes), 2)
                if decomp_sizes and sizes else None
            ),
        },
        "protobuf": {
            "well_formed": pb_ok, "of": decomp_ok,
            "top_level_fields": dict(sorted(pb_fields.items())),
            "errors": pb_errors,
        },
        "rest_baseline": REST_BASELINE,
    }


def _histogram(gaps: list[float]) -> dict[str, int]:
    """Bucket inter-arrivals to whole seconds, matching the 08-30 brief's table."""
    hist: dict[str, int] = {}
    for g in gaps:
        key = f"{int(g)}s" if g >= 1 else "<1s"
        hist[key] = hist.get(key, 0) + 1
    return dict(sorted(hist.items(), key=lambda kv: (kv[0] != "<1s", kv[0])))


def render_report(result: dict[str, Any], run_dir: Path, negotiated: dict[str, Any]) -> str:
    """Markdown for docs/reports/, written to answer the three questions in order."""
    fb, sp, dc, pb = (result["frame_bytes"], result["spacing_s"],
                      result["decompression"], result["protobuf"])
    base = result["rest_baseline"]
    L = [
        "# GexBot WebSocket — what the payload actually is",
        "",
        f"Probe `st-8qqw`, run `{run_dir.name}`. Group `{result['group']}`, "
        f"{result['duration_s']:.0f}s capture. **Measured, not documentary.** "
        "Wire format decoded and confirmed against simultaneous REST polls: "
        "`docs/measurement/gexbot-websocket-wire-format-2026-09-02.md`.",
        "",
        f"Artifacts: `{run_dir}` (frames.bin, frames.jsonl, negotiate.json, probe.log).",
        "",
        "## The three questions",
        "",
        "### 1. What does a frame weigh?",
        "",
    ]
    if fb:
        L += [
            f"**{result['frames']} frames, {result['total_bytes']:,} bytes on the wire.** "
            f"Per frame: min {fb['min']:.0f} B, median {fb['median']:.0f} B, "
            f"max {fb['max']:.0f} B.",
            "",
        ]
        if dc["decompressed_bytes"]:
            db = dc["decompressed_bytes"]
            L += [
                f"Decompressed: median {db['median']:.0f} B, max {db['max']:.0f} B — "
                f"a ratio of about **{dc['ratio']}x**. Compression methods seen: "
                f"{dc['methods']}.",
                "",
            ]
    else:
        L += ["No frames captured.", ""]

    L += ["### 2. What is the real cadence?", ""]
    if sp:
        L += [
            f"**{result['observed_hz']} frames/second observed** against the vendor's "
            f"stated 1 Hz ceiling. Inter-arrival: min {sp['min']:.2f}s, "
            f"median {sp['median']:.2f}s, mean {sp['mean']:.2f}s, max {sp['max']:.2f}s "
            f"over {sp['n']} intervals.",
            "",
            f"Distribution: `{result['spacing_histogram']}`",
            "",
            f"**Against our REST poller** ({base['session']}, the 08-30 brief §3): "
            f"{base['polls']:,} polls, median spacing {base['median_spacing_s']}s, "
            f"estimated {base['capture_fraction']:.0%} of published updates captured. "
            "The gap this feed would close is the round trip, not the recompute "
            "interval — read the median spacing above against that 2.0s to see how "
            "much of the missing 38% is real.",
            "",
        ]
    else:
        L += ["Too few frames to measure spacing.", ""]

    L += ["### 3. Is it decodable without the vendor's client?", ""]
    if pb["of"]:
        L += [
            f"**{pb['well_formed']} of {pb['of']} decompressed payloads walk cleanly "
            "as protobuf to EOF.** Protobuf is not self-describing: the wire format "
            "carries field NUMBERS and TYPES, never names. So structure is "
            "recoverable and semantics are not — the question is whether the "
            "recovered shape lines up with a known REST schema "
            "(`orderflow_response` has 48 properties, `basic_response` 15).",
            "",
            f"**{len(pb['top_level_fields'])} distinct top-level fields recovered:**",
            "",
            "| field | wire type | frames seen in | sample |",
            "|---:|---|---:|---|",
        ]
        wire_names = {0: "varint", 1: "64-bit", 2: "length-delim", 5: "32-bit"}
        for num, meta in pb["top_level_fields"].items():
            sample = meta.get("sample", meta.get("sample_len"))
            if isinstance(sample, float):
                sample = f"{sample:.4g}"
            elif "sample_len" in meta and "sample" not in meta:
                sample = f"{meta['sample_len']} B"
            L.append(
                f"| {num} | {wire_names.get(meta['wire_type'], meta['wire_type'])} "
                f"| {meta['seen']} | {sample} |"
            )
        L.append("")
        if pb["errors"]:
            L += [f"Walk failures: `{pb['errors']}`", ""]
    else:
        L += ["Nothing decompressed, so nothing to walk.", ""]

    L += [
        "## Negotiate",
        "",
        f"Hubs authorized for this key: **{', '.join(sorted(negotiated))}**.",
        "",
        "## What this does not answer",
        "",
        "- **Field semantics.** Numbers and types only; mapping them to `spot`, "
        "`zero_gamma` and the rest needs the vendor's `.proto` or a correlation "
        "study against a simultaneous REST poll.",
        "- **Whether the extra resolution changes a trade.** The 08-30 brief's "
        "finding stands until something measures it, and one probe window cannot.",
        "- **Explicit-expiry groups.** Out of scope here; they publish at ~5s and "
        "are never persisted to `/hist`.",
        "",
    ]
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------- main ----

async def run(args: argparse.Namespace) -> int:
    import httpx

    env = load_env()
    api_key = env.get("GEXBOT_API_KEY")
    if not api_key:
        log.error("GEXBOT_API_KEY not in .env — nothing to negotiate with")
        return 2

    now = datetime.now(timezone.utc)
    if not in_rth(now) and not args.force:
        log.error(
            "outside the vendor's publish window (08:30-15:00 CT weekdays); it is %s. "
            "The socket would open and stay silent. Re-run inside RTH, or --force to "
            "observe the silence deliberately.",
            now.astimezone(CT).strftime("%a %Y-%m-%d %H:%M CT"),
        )
        return 2

    run_dir = PROBE_ROOT / now.astimezone(CT).strftime("%Y%m%dT%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(run_dir / "probe.log")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(fh)
    log.info("run dir %s", run_dir)
    log.info("group %s, duration %.0fs, rth=%s force=%s",
             args.group, args.duration, in_rth(now), args.force)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Authorization": bearer(api_key),
    }
    transport = httpx.HTTPTransport(local_address=LOCAL_ADDR_V4)
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT_S, transport=transport) as client:
            resp = client.post(
                f"{BASE_URL}/negotiate", headers=headers, json={"groups": [args.group]}
            )
    except httpx.HTTPError as exc:
        log.error("negotiate transport failure: %s", exc)
        return 5

    if resp.status_code != 200:
        # 401 is the key; 403 is the tier or the group cap. After 2026-09-06 a 403
        # here IS the expected answer and is itself the measurement.
        log.error("negotiate returned %d: %s", resp.status_code, redact(resp.text[:400]))
        return 3

    body = resp.json()
    urls = body.get("websocket_urls") or {}
    (run_dir / "negotiate.json").write_text(redact(json.dumps(body, indent=2)))
    log.info("negotiate ok; hubs authorized: %s", sorted(urls))

    try:
        hub, url = hub_for_group(args.group, urls)
    except (ValueError, KeyError) as exc:
        log.error("%s", exc)
        return 3
    log.info("hub %s selected for group %s", hub, args.group)

    sink = FrameSink(run_dir)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        # Ctrl-C must still produce a report over whatever was captured — an
        # interrupted probe inside a closing window is worth more than nothing.
        loop.add_signal_handler(sig, stop.set)

    try:
        await capture(url, sink, args.duration, stop)
    except Exception as exc:  # noqa: BLE001 — transport zoo; the report matters more
        log.error("capture failed after %d frames: %s: %s",
                  sink.seq, type(exc).__name__, redact(str(exc)))
        if sink.seq == 0:
            sink.close()
            return 5
    finally:
        sink.close()

    if sink.seq == 0:
        log.error(
            "connected but no frames arrived in %.0fs. Inside RTH that is a finding; "
            "outside it, expected.", args.duration
        )
        return 4

    result = analyse(sink, args.group, args.duration)
    (run_dir / "analysis.json").write_text(json.dumps(result, indent=2, default=str))
    report = render_report(result, run_dir, urls)
    (run_dir / "report.md").write_text(report)
    print(report)
    log.info("done: %d frames, %d bytes, report at %s",
             sink.seq, sink.offset, run_dir / "report.md")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--group", default=DEFAULT_GROUP,
                    help=f"single websocket group to join (default {DEFAULT_GROUP})")
    ap.add_argument("--duration", type=float, default=120.0,
                    help="capture seconds (default 120)")
    ap.add_argument("--force", action="store_true",
                    help="run outside the vendor's 08:30-15:00 CT publish window")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    if args.duration <= 0:
        log.error("--duration must be positive")
        return 2
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        log.warning("interrupted before capture began")
        return 2


if __name__ == "__main__":
    sys.exit(main())
