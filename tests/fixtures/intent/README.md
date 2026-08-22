# Intent dialect fixtures

- `constructed-day-read.txt` — the worked example of the 2026-07-25 trade-language survey
  (§4), **constructed from attested vocabulary, not a recorded utterance**. It is the parser's
  fixture only until Steve's real full-day dictation lands (Dictation Specimen Captured,
  st-79z.4), which replaces it as the binding test. Prices are the survey's (the 6300s);
  the grammar does not care about the absolute level.
- `chain-6320.json` — a small SPX chain snapshot around 6320 for pricing the example's fly
  (calls 6280–6360 by 20, puts likewise). Mids are set so the 6300/6320/6340 call fly prices
  at a 0.55 debit: 3.05 − 2 × 1.50 + 0.50.
- `../tos/` — empty until the TOS fixture pass (st-79z.5). While a shape's file is absent,
  `strader.intent.tos` reports that shape's paste string as **inferred**.
