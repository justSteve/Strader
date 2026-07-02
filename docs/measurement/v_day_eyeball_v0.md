# V-Day Eyeball Validation — v0 (params: DEPTH=0.6×LATR, RECOVERY=50%, LANDING=0.3×LATR)

**How to use:** click each date link to open the pre-annotated chart (local HTML, file:// URL — opens in browser). The chart shows ES 5m bars over [13:00, 15:00) CT with the detector's trough/peak markers and a dashed line at VWAP_p. Mark `Eye` column:

- **V** = clear V pattern matching the detector
- **~** = borderline / not obvious
- **X** = does NOT look like a V
- **?** = can't tell from chart

**Targets:**
- V-DOWN / V-UP rows should mostly score V
- MISS-BY-1 rows: detector said no (landing too far) — expect mostly X or ~
- NONE CONTROL rows should score X

---

## V-DOWN flagged (n=16) — should look like late-day drops with snap-back

| Date | Trough@ | VWAP_p | Trough_p | Close_p | Depth | Reco | Land | d/LATR | Eye |
|------|---------|--------|----------|---------|-------|------|------|--------|-----|
| [2025-09-10](file:///root/projects/Strader/data/measurement/charts/2025-09-10_1300-1500.html) | 14:21 | 6535.24 | 6522.50 | 6539.25 | 12.74 | 16.75 | 4.01 | 0.64 | _ |
| [2025-09-17](file:///root/projects/Strader/data/measurement/charts/2025-09-17_1300-1500.html) | 13:54 | 6607.61 | 6554.00 | 6602.75 | 53.61 | 48.75 | 4.86 | 2.67 | _ |
| [2025-09-29](file:///root/projects/Strader/data/measurement/charts/2025-09-29_1300-1500.html) | 14:15 | 6710.35 | 6696.25 | 6714.25 | 14.10 | 18.00 | 3.90 | 0.64 | _ |
| [2025-10-13](file:///root/projects/Strader/data/measurement/charts/2025-10-13_1300-1500.html) | 14:01 | 6700.70 | 6681.50 | 6694.50 | 19.20 | 13.00 | 6.20 | 0.80 | _ |
| [2025-10-29](file:///root/projects/Strader/data/measurement/charts/2025-10-29_1300-1500.html) | 13:41 | 6933.99 | 6882.25 | 6928.00 | 51.74 | 45.75 | 5.99 | 2.06 | _ |
| [2025-11-13](file:///root/projects/Strader/data/measurement/charts/2025-11-13_1300-1500.html) | 13:55 | 6764.45 | 6746.00 | 6762.00 | 18.45 | 16.00 | 2.45 | 0.62 | _ |
| [2025-11-17](file:///root/projects/Strader/data/measurement/charts/2025-11-17_1300-1500.html) | 14:03 | 6696.67 | 6658.50 | 6693.75 | 38.17 | 35.25 | 2.92 | 1.30 | _ |
| [2025-12-18](file:///root/projects/Strader/data/measurement/charts/2025-12-18_1300-1500.html) | 13:58 | 6783.78 | 6764.00 | 6776.25 | 19.78 | 12.25 | 7.53 | 0.60 | _ |
| [2026-01-30](file:///root/projects/Strader/data/measurement/charts/2026-01-30_1300-1500.html) | 14:22 | 6968.25 | 6940.75 | 6968.00 | 27.50 | 27.25 | 0.25 | 0.97 | _ |
| [2026-02-18](file:///root/projects/Strader/data/measurement/charts/2026-02-18_1300-1500.html) | 14:16 | 6900.37 | 6872.50 | 6895.50 | 27.87 | 23.00 | 4.87 | 0.77 | _ |
| [2026-03-02](file:///root/projects/Strader/data/measurement/charts/2026-03-02_1300-1500.html) | 14:15 | 6895.80 | 6872.75 | 6887.25 | 23.05 | 14.50 | 8.55 | 0.69 | _ |
| [2026-03-30](file:///root/projects/Strader/data/measurement/charts/2026-03-30_1300-1500.html) | 14:29 | 6398.10 | 6359.50 | 6387.75 | 38.60 | 28.25 | 10.35 | 0.88 | _ |
| [2026-04-08](file:///root/projects/Strader/data/measurement/charts/2026-04-08_1300-1500.html) | 14:01 | 6819.75 | 6792.50 | 6823.50 | 27.25 | 31.00 | 3.75 | 0.62 | _ |
| [2026-05-07](file:///root/projects/Strader/data/measurement/charts/2026-05-07_1300-1500.html) | 13:45 | 7364.50 | 7345.50 | 7364.25 | 19.00 | 18.75 | 0.25 | 0.78 | _ |
| [2026-05-08](file:///root/projects/Strader/data/measurement/charts/2026-05-08_1300-1500.html) | 13:55 | 7423.46 | 7407.50 | 7421.00 | 15.96 | 13.50 | 2.46 | 0.65 | _ |
| [2026-05-21](file:///root/projects/Strader/data/measurement/charts/2026-05-21_1300-1500.html) | 13:55 | 7470.08 | 7438.00 | 7465.25 | 32.08 | 27.25 | 4.83 | 1.17 | _ |

## V-UP flagged (n=6) — should look like late-day rallies with fade

| Date | Peak@ | VWAP_p | Peak_p | Close_p | Depth | Reco | Land | d/LATR | Eye |
|------|-------|--------|--------|---------|-------|------|------|--------|-----|
| [2025-07-22](file:///root/projects/Strader/data/measurement/charts/2025-07-22_1300-1500.html) | 14:57 | 6340.50 | 6353.75 | 6345.50 | 13.25 | 8.25 | 5.00 | 0.61 | _ |
| [2025-10-17](file:///root/projects/Strader/data/measurement/charts/2025-10-17_1300-1500.html) | 14:21 | 6700.23 | 6718.00 | 6703.75 | 17.77 | 14.25 | 3.52 | 0.70 | _ |
| [2025-10-31](file:///root/projects/Strader/data/measurement/charts/2025-10-31_1300-1500.html) | 14:35 | 6870.08 | 6900.00 | 6872.00 | 29.92 | 28.00 | 1.92 | 1.02 | _ |
| [2026-03-16](file:///root/projects/Strader/data/measurement/charts/2026-03-16_1300-1500.html) | 14:10 | 6708.92 | 6734.25 | 6703.00 | 25.33 | 31.25 | 5.92 | 0.67 | _ |
| [2026-03-24](file:///root/projects/Strader/data/measurement/charts/2026-03-24_1300-1500.html) | 13:39 | 6616.21 | 6641.75 | 6607.00 | 25.54 | 34.75 | 9.21 | 0.62 | _ |
| [2026-04-30](file:///root/projects/Strader/data/measurement/charts/2026-04-30_1300-1500.html) | 14:59 | 7231.20 | 7251.75 | 7238.25 | 20.55 | 13.50 | 7.05 | 0.73 | _ |

## MISS-BY-1 (n=8) — drop + recovery present, but close didn't land near VWAP_p

| Date | Trough@ | VWAP_p | Trough_p | Close_p | Depth | Reco | Land | d/LATR | Eye |
|------|---------|--------|----------|---------|-------|------|------|--------|-----|
| [2025-07-30](file:///root/projects/Strader/data/measurement/charts/2025-07-30_1300-1500.html) | 14:06 | 6417.32 | 6366.75 | 6397.50 | 50.57 | 30.75 | 19.82 | 2.65 | _ |
| [2025-07-31](file:///root/projects/Strader/data/measurement/charts/2025-07-31_1300-1500.html) | 14:55 | 6381.79 | 6358.25 | 6371.00 | 23.54 | 12.75 | 10.79 | 1.16 | _ |
| [2025-06-27](file:///root/projects/Strader/data/measurement/charts/2025-06-27_1300-1500.html) | 13:52 | 6209.28 | 6183.25 | 6223.25 | 26.03 | 40.00 | 13.97 | 0.94 | _ |
| [2026-04-21](file:///root/projects/Strader/data/measurement/charts/2026-04-21_1300-1500.html) | 14:44 | 7114.71 | 7085.00 | 7100.50 | 29.71 | 15.50 | 14.21 | 0.91 | _ |
| [2026-05-11](file:///root/projects/Strader/data/measurement/charts/2026-05-11_1300-1500.html) | 14:22 | 7449.98 | 7427.50 | 7438.75 | 22.48 | 11.25 | 11.23 | 0.90 | _ |
| [2025-08-11](file:///root/projects/Strader/data/measurement/charts/2025-08-11_1300-1500.html) | 14:56 | 6407.05 | 6387.50 | 6400.00 | 19.55 | 12.50 | 7.05 | 0.85 | _ |
| [2026-01-20](file:///root/projects/Strader/data/measurement/charts/2026-01-20_1300-1500.html) | 14:59 | 6840.75 | 6822.25 | 6833.75 | 18.50 | 11.50 | 7.00 | 0.81 | _ |
| [2025-10-16](file:///root/projects/Strader/data/measurement/charts/2025-10-16_1300-1500.html) | 13:34 | 6651.24 | 6632.00 | 6668.50 | 19.24 | 36.50 | 17.26 | 0.72 | _ |

## NONE CONTROL (n=5, random sample) — detector says clearly not a V

| Date | VWAP_p | Trough_p | Peak_p | Close_p | LATR | Eye |
|------|--------|----------|--------|---------|------|-----|
| [2025-07-09](file:///root/projects/Strader/data/measurement/charts/2025-07-09_1300-1500.html) | 6297.19 | 6295.50 | 6309.50 | 6307.00 | 25.96 | _ |
| [2025-08-14](file:///root/projects/Strader/data/measurement/charts/2025-08-14_1300-1500.html) | 6483.14 | 6479.00 | 6496.00 | 6488.75 | 22.73 | _ |
| [2025-10-23](file:///root/projects/Strader/data/measurement/charts/2025-10-23_1300-1500.html) | 6781.10 | 6771.50 | 6785.75 | 6774.75 | 27.43 | _ |
| [2026-04-01](file:///root/projects/Strader/data/measurement/charts/2026-04-01_1300-1500.html) | 6621.68 | 6604.00 | 6634.75 | 6619.50 | 44.98 | _ |
| [2026-05-18](file:///root/projects/Strader/data/measurement/charts/2026-05-18_1300-1500.html) | 7389.50 | 7373.50 | 7428.00 | 7426.25 | 25.75 | _ |

---

## Tally (fill after completion)

| Section | V (agree) | ~ (borderline) | X (disagree) | ? (skip) | n |
|---------|-----------|----------------|--------------|----------|---|
| V-DOWN flagged | _ | _ | _ | _ | 16 |
| V-UP flagged | _ | _ | _ | _ | 6 |
| MISS-BY-1 | (X expected) | _ | _ | _ | 8 |
| NONE control | (X expected) | _ | _ | _ | 5 |

**Agreement metric:** (V on flagged) + (X on miss-by-1+control) / total scored.
Target ≥ 80%. Below = retune. Above = freeze v0 params and move to greek correlation.
