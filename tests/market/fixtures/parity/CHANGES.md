# Parity snapshot change log

One entry per deliberate regeneration; commit the entry, the
snapshot, and the motivating change together.

- **2026-07-06 12:36Z** (14 events, base c63c6b0): initial snapshot — harness creation (st-bw9)
- **2026-07-06 18:01Z** (14 events, base 86ec5ea): recognizer INVALIDATE_TICKS 16->60, ENGAGEMENT_WINDOW_BARS 12->40 — st-3vu calibration vs Mancini-labeled days (4 misses flipped, 0 hits lost)
- **2026-07-22 13:21Z** (14 events + 1 absorption, base aa2f20d): st-9vl: absorption snapshot added — AbsorptionTracker over the new gzipped MBP-1 fixture (65s slice of the purchased 2026-07-02 day), production floors
- **2026-07-31 04:44Z** (14 events + 1 absorption, base 7eb5177): SetupRecognition gains fire_index (per-anchor re-fire damping, st-98z item 2); serialize() emits every dataclass field, so the 6 recognizer events gain the key
