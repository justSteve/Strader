# The GexBot WebSocket wire format, decoded

**`WebSocket Payload Probe` (`st-8qqw`)** · 2026-09-02 · **measured**

Three capture sessions (08-31, 09-01, 09-02), 636 frames, plus exact-timestamp
cross-checks against our own REST collector. The feed is **fully decodable
without the vendor's client**, which reverses the answer this probe was built
to test.

## The shape

```
WebSocket binary frame  (no Azure subprotocol requested)
│
└── protobuf ENVELOPE, 2 fields, uncompressed
    ├── 1  bytes   message type name, ASCII — "proto.greek"
    └── 2  bytes   zstd frame (magic 28b52ffd)
        │          NO content size in the header, so the one-shot zstd API
        │          refuses it — streaming decompression is required
        │
        └── protobuf MESSAGE  ≡  the REST `basic_response`
            ├──  1  varint    timestamp, unix seconds
            ├──  2  bytes     ticker — "SPX"
            ├──  3  varint    spot              × 100
            ├──  4  varint    min_dte
            ├──  5  varint    UNIDENTIFIED — constant 2 (see below)
            ├──  6  varint    major_positive    × 100
            ├──  7  varint    major_negative    × 100
            ├──  8  varint    major_long_gamma  × 100
            ├──  9  varint    major_short_gamma × 100
            └── 10  repeated  strike ladder ≡ REST `mini_contracts`
                ├── 1  varint  strike × 100
                ├── 2  varint  value  × 1000
                ├── 3  varint  value  × 1000
                ├── 4  varint  ZIGZAG-encoded signed × 100
                └── 5  bytes   the [0, 0, 0] triple
```

**Prices are fixed-point integers, not floats.** Scale is ×100 at the message
level and ×1000 for the two per-strike ratios.

**Signed values are zigzag-encoded.** Sub-field 4 read `2743` where REST said
`-13.72`, and `2679` where REST said `-13.4`. Decoding `(n >> 1) ^ -(n & 1)`
gives `-1372` and `-1340` exactly. This is the standard protobuf `sint32`
encoding and it is the detail that would silently produce garbage — read as a
plain varint, a small negative number becomes a large positive one.

## How it was confirmed

Not by inference. On 2026-09-02 the WebSocket probe and the REST collector ran
simultaneously, and the vendor stamps both with the same data timestamp, so
frames and REST bodies can be matched on an **exact second**. Four such matches
landed on `/SPX/state/gamma_zero`; three are shown:

| ts | field | WS raw | decoded | REST |
|---|---|---:|---:|---:|
| 1788355978 | 3 | 764047 | 7640.47 | spot **7640.47** |
| | 6 | 765500 | 7655.00 | major_positive **7655** |
| | 7 | 761500 | 7615.00 | major_negative **7615** |
| | 8 | 765484 | 7654.84 | major_long_gamma **7654.84** |
| | 9 | 766067 | 7660.67 | major_short_gamma **7660.67** |
| | 10 | 107 repeats | — | mini_contracts **107** |
| 1788356056 | 3 | 763878 | 7638.78 | spot **7638.78** |
| 1788356132 | 3 | 763959 | 7639.59 | spot **7639.59** |

Every mapped field matches to the cent, on independent timestamps.

## What is still unknown

**Field 5 is not `sec_min_dte`.** It reads a constant `2` while REST reports
`sec_min_dte: 1` at the same timestamp. It may be a schema version, a category
enum, or something else. **Reported as unidentified rather than guessed** — the
temptation is to call it `sec_min_dte` because the REST schema has a field in
that position, and the exact-timestamp comparison is precisely what refutes it.

The two per-strike ×1000 ratios are confirmed numerically against REST but
their *names* come from the REST array's positional order, which the vendor
does not document.

## The correction this supersedes

Days 1 and 2 reported every frame **"uncompressed"** and I passed that to Steve
as falsifying the vendor's documented "Zstandard-compressed Protocol Buffers."
**The vendor was right and the probe was wrong.** `decompress()` tested only the
frame's leading bytes for the zstd magic, found plain protobuf, and stopped —
the compression sits one level in, exactly where a frame-level check cannot see
it. Fixed 2026-09-01; day 3 reports `{'envelope+zstd': 217}` and a 1.76×
decompression ratio.

**The general lesson, worth more than the fix:** a negative result from a
detector that only looks at offset zero is a statement about the detector until
something has looked inside.

## What this does not settle

- **Whether the extra resolution changes a trade.** The 08-30 brief's finding
  stands. Decodability is not edge.
- **Cadence.** Measured median inter-arrival across the three sessions: 1.51s,
  1.32s, 1.38s — consistently off the vendor's stated 1 Hz ceiling, against our
  REST poller's 2.0s median.
- **Explicit-expiry groups**, which publish at ~5s and never reach `/hist`.

Two capture sessions remain — **09-03 and 09-04** — after which `/negotiate`
lapses with the Quant entitlement and the feed becomes permanently unreadable.
