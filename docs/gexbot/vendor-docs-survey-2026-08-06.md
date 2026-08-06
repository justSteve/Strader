# GexBot Vendor Documentation Survey — Quant Tier

**Compiled** 2026-08-06
**Scope** Everything the vendor publishes that bears on a Quant-tier subscriber: packages, categories, endpoint contracts, entitlements, cadence, and field semantics.

Every claim below carries its source URL. Where the vendor publishes **nothing**, this document says so explicitly rather than filling the gap with inference. Inferences, where they appear at all, are labelled and kept separate from vendor statements.

---

## 1. Where the vendor documentation actually lives

The marketing site is a client-rendered single-page app; `https://www.gexbot.com/` and `https://www.gexbot.com/apidocs` both return an empty shell to any non-browser fetch, so neither is usable as a documentation source. The real, retrievable vendor documentation is on GitHub under the vendor's own org, `nfa-llc`.

| Source | URL | What it carries |
|---|---|---|
| OpenAPI spec repo | https://github.com/nfa-llc/gexbot-openapi | Endpoint table, tier list, auth, worked examples |
| Spec (YAML, source of truth) | https://raw.githubusercontent.com/nfa-llc/gexbot-openapi/master/latest/gexbot.spec3.yaml | Machine-readable contract, v2.3.0 |
| Spec (JSON) | https://raw.githubusercontent.com/nfa-llc/gexbot-openapi/master/latest/gexbot.spec3.json | Same, JSON conversion |
| WebSocket doc | https://raw.githubusercontent.com/nfa-llc/gexbot-openapi/master/docs/websocket.md | Realtime feed, hubs, groups, limits |
| Agent/maintainer notes | https://raw.githubusercontent.com/nfa-llc/gexbot-openapi/master/AGENTS.md | **Rate limits and update cadence** — documented nowhere else |
| Historical downloader | https://github.com/nfa-llc/quant-historical | Reference `/hist` client |
| Downloader source | https://raw.githubusercontent.com/nfa-llc/quant-historical/master/main.py | Package/category roster, auth header form |
| WebSocket client | https://github.com/nfa-llc/quant-python-sockets | Referenced from the spec README; not reviewed here |
| Terms | https://www.gexbot.com/terms-and-conditions | Referenced as `termsOfService` in the spec |

Note the default branch on both repos is `master`, not `main`.

### Finding: our canonical spec copy is one minor version behind

`docs/gexbot/gexbot.spec3.yaml` in this repo is **v2.2.0** (1,015 lines). The vendor is publishing **v2.3.0** (1,734 lines). The repo README classes that file as "immutable until vendor updates" — the vendor has updated.

New in 2.3.0, by schema and path diff:

- **New endpoints**: `/{package}/categories`, `/tickers/quant`, `/options/{ticker}/expiries`, `/research/{ticker}/{metric}`, and `POST`/`PATCH` variants of `/negotiate`.
- **New product**: gexbot research (`gbR`), with its own tier, its own key, and a ~100-value metric enum.
- **New schemas**: `data_category`, `option_expiries_response`, `quant_tickers_response`, `research_metric`, `research_ticker`, and nine `websocket_*` schemas covering the new negotiate flow.
- **Deprecation**: `GET /negotiate` is now marked legacy.

Nothing in the `classic`, `state`, or `orderflow` response schemas changed between 2.2.0 and 2.3.0. Verified by parsing both specs and comparing the resolved schema objects: `basic_response` (15 properties), `orderflow_response` (48), `majors_response` (10), `maxchange_response` (8), and all three `category_*` enums are **structurally identical** across the two versions. **The archive's schema is unaffected by the version gap** — it matters for endpoint discovery and the WebSocket flow, not for stored data.

One live-vs-spec drift worth noting: the `ticker_stock` enum holds 53 symbols in *both* spec versions and does **not** include `SPCX`, which the live `/tickers` endpoint returns. The published enum trails the live roster.

A current copy of the 2.3.0 spec has been saved alongside the canonical one as `gexbot.spec3-2.3.0.yaml` rather than overwriting it, so the canonical-file refresh stays an explicit decision.

---

## 2. Two products, two keys

The vendor sells two distinct products under one API host ([spec README](https://github.com/nfa-llc/gexbot-openapi)):

> - **gexbot** — Options-derived market data including GEX (Gamma Exposure), greeks, and orderflow metrics for enumerated tickers.
> - **gexbot research** (`gbR`) — Chart and analytical data for a broad range of options metrics across any supported ticker, with flexible output formats, views, and filtering.

> Each product requires a dedicated API key — a **gexbot** key for the gexbot endpoints and a **gexbot research** (`gbR`) key for the `/research` endpoints. Keys are not interchangeable between products.

Everything in our archive is the **gexbot** product. Research is a separate purchase.

### Authentication

Bearer token in the `Authorization` header. The vendor is explicit that the gexbot key carries a mandatory prefix ([spec README](https://github.com/nfa-llc/gexbot-openapi)):

> Your gexbot API key must include both the prefix `gexbot_custom_` and your secret key in the `Authorization` header (e.g., `gexbot_custom_your-secret-key`).

Research keys use a `research_` prefix instead. Worth flagging a **contradiction in the vendor's own material**: the spec README shows `Authorization: Bearer gexbot_custom_<key>`, while the vendor's reference downloader `main.py` sends `Authorization: Basic {API_KEY}` ([main.py](https://raw.githubusercontent.com/nfa-llc/quant-historical/master/main.py), `fetch_history_url`). The spec's `securitySchemes` declares `type: http, scheme: bearer`. The vendor has not reconciled these; our poller's working configuration is the authority over either.

`User-Agent` and `Accept: application/json` are **required headers on all requests** — both are declared `required: true` in the spec, and the downloader README states the API rejects requests without a User-Agent.

Two endpoints are unauthenticated (`security: []`): `/tickers` and `/{package}/categories` ([AGENTS.md](https://raw.githubusercontent.com/nfa-llc/gexbot-openapi/master/AGENTS.md)).

---

## 3. Subscription tiers and entitlements

The spec's `tags` block is the authoritative entitlement map — every endpoint lists the tiers that grant it ([gexbot.spec3.yaml](https://raw.githubusercontent.com/nfa-llc/gexbot-openapi/master/latest/gexbot.spec3.yaml), `tags:`):

| Tier | Vendor description |
|---|---|
| Public | "Endpoints that do not require authentication, such as listing available tickers and downloading historical data." |
| Classic | "Available with Classic Subscription" |
| State | "Available with State Subscription" |
| Orderflow | "Available with Orderflow Subscription" |
| Quant | "Available with Quant Subscription" |
| Research | "Available with Research Addon. Provides chart and analytical data for options metrics across various formats and views." |

The README restates this as a purchasing list:

> - **Classic** — Classic GEX data
> - **State** — State greeks data
> - **Orderflow** — Orderflow metrics
> - **Quant** — Full access including historical data and WebSocket feeds
> - **Research** — gexbot research (`gbR`) access

### What Quant specifically unlocks

Quant is a superset tier, not a sibling. Reading the per-endpoint tags: every Classic, State, and Orderflow endpoint also carries the `Quant` tag, and four capabilities carry `Quant` **exclusively** —

1. `/hist/{ticker}/{package}/{category}/{date}` — historical download
2. `/negotiate` (POST/PATCH/GET) — WebSocket realtime feed
3. `/tickers/quant` — the supplemental Quant-only ticker roster
4. `/options/{ticker}/expiries` — expiry discovery for realtime expiry groups

This confirms operationally what we observed: **orderflow entitlement arrives bundled with Quant**, because the orderflow endpoint is tagged `Orderflow, Quant`. It was not a separate purchase and is not an anomaly.

> **Vendor silence:** prices, per-tier request quotas, and concurrent-connection limits (beyond the WebSocket group cap in §7) are not published in any retrievable vendor document. The spec's tier tags describe *access*, never *volume*.

---

## 4. Packages

`package` is a path segment on `/hist` and a prefix on the live REST routes. The spec enumerates exactly three ([`package_in_path`](https://raw.githubusercontent.com/nfa-llc/gexbot-openapi/master/latest/gexbot.spec3.yaml)):

```
* `classic`   - Classic subscription data
* `state`     - State subscription data
* `orderflow` - Orderflow subscription data
```

Those one-line descriptions are the **entirety** of what the OpenAPI spec says about what distinguishes the packages. The substantive distinction is not in the spec — it comes from the vendor principals' own Discord statements, archived in this repo at `canonical/principal_discord.md` (canonical tier: authored by GexBot principals jass and John Kirby):

| Product | Method | What it measures |
|---|---|---|
| **Classic GEX** | Naively increments volume per contract trade → into GEX calculation | Aggregate per-strike gamma exposure assuming naive sign |
| **State GEX** | Classifies each trade as buy or sell using a vol surface → signed volume cumulative through the day → THEN computes GEX exposure | Customer-classified gamma exposure that preserves initiator side |

The vendor's concrete illustration: in State, a strike's volume might be **+50** (50 lots bought by customers) or **−25** (25 lots sold by customers). Classic does not preserve that sign — both register as 75 raw contracts traded with no directional information. The principals state directly that Classic's naive assumption is "baked into the chart shape" and is "a structural artifact of the method, not a real read of positioning."

**Consequence for the archive:** `classic/gex_full`, `classic/gex_zero`, and `classic/gex_one` are the *unsigned* counterparts of their `state` namesakes. They share a response schema and are not redundant with State — they are a methodological control, useful precisely as a contrast.

`orderflow` is a third, structurally different thing: a single flat metrics snapshot rather than a per-strike ladder (see §8.2).

---

## 5. Categories — and what `zero` / `one` / `full` actually mean

This was the item flagged for vendor confirmation rather than inference. The vendor **does** define it, in the `category_classic` schema description:

> Classic GEX data category:
> * `full` or `gex_full` - Full aggregation of GEX (call/put), up to 90 days out
> * `zero` or `gex_zero` - Only next expiry+0 of GEX (call/put), 0dte
> * `one` or `gex_one` - Only next expiry+1 of GEX (call/put)

And in `category_state`:

> * `delta` or `delta_zero` - The delta
> * `gamma` or `gamma_zero` - The gamma (long/short)
> * `vanna` or `vanna_zero` - The vanna
> * `charm` or `charm_zero` - The charm
> * `onedelta` or `delta_one` - 1dte delta
> * `onegamma` or `gamma_one` - 1dte gamma (long/short)
> * `onevanna` or `vanna_one` - 1dte vanna
> * `onecharm` or `charm_one` - 1dte charm

Three things are settled by this:

1. **`full` is a 90-day aggregation**, not "all listed expiries" — bounded, and the bound matches the `/hist` look-back window and the `/options/expiries` horizon.
2. **`zero` and `one` are expiry-ordinal, not day-count.** The vendor's precise phrasing is "next expiry+0" and "next expiry+1" — the *front* listed expiration and the *second* listed expiration. For SPX with Mon/Wed/Fri expirations, "next expiry+1" is the next listed expiry, which is frequently **not** one calendar day out.
3. **The unsuffixed aliases are exact synonyms.** `gamma` ≡ `gamma_zero`, `full` ≡ `gex_full`. Both spellings hit the same data.

> **Vendor inconsistency, flagged not resolved:** `category_classic` describes `one` positionally ("next expiry+1"), while `category_state` describes the same ordinal as "1dte". These cannot both be literally true on a Monday when the second SPX expiry is Wednesday. The vendor does not disambiguate anywhere. **Do not infer which reading is correct — resolve it empirically from the archive**, using the `min_dte` and `sec_min_dte` fields that every `basic_response` carries for exactly this purpose (§8.1). Our 62-day archive can settle this definitively by checking whether `sec_min_dte` is ever ≠ 1.

### Live category roster, confirmed against the API

The `/{package}/categories` endpoint is unauthenticated and returns the current roster. Queried live on 2026-08-06:

```
GET https://api.gex.bot/v2/classic/categories
  ["gex_full","gex_zero","gex_one"]

GET https://api.gex.bot/v2/state/categories
  ["gex_full","gex_zero","gex_one","delta_zero","delta_one",
   "gamma_zero","gamma_one","vanna_zero","vanna_one",
   "charm_zero","charm_one"]

GET https://api.gex.bot/v2/orderflow/categories
  ["orderflow"]
```

**This is an exact match to the 17 combos in our archive.** The archive is complete against the vendor's current published roster for SPX — there is no category we are missing. Note the live roster returns only the canonical spellings, not the `onegamma`-style aliases, so these are the names to build requests and WebSocket groups with.

### Ticker rosters

`GET https://api.gex.bot/v2/tickers` (unauthenticated, live 2026-08-06) returns 54 stocks, 4 indexes (`NDX`, `RUT`, `SPX`, `VIX`), and 2 futures (`ES_SPX`, `NQ_NDX`). One drift note: the live stock list includes `SPCX`, which the `ticker_stock` enum omits in **both** 2.2.0 and 2.3.0 (53 symbols in each). Prefer the live endpoint over the spec enum for ticker validation.

`GET https://api.gex.bot/tickers/quant` (note: **no** `/v2` prefix) returns a further 50 Quant-only stocks and one index, `XSP`. These are **WebSocket-only**; the spec is explicit that they "are not REST chart/history endpoints." They cannot be added to the historical archive.

---

## 6. The `/hist` endpoint contract

`GET /v2/hist/{ticker}/{package}/{category}/{date}` — tagged **Quant only**.

Vendor description, verbatim:

> Generates a pre-signed URL to download historical data (JSON) for a specific date. Data is available for a 90-day look-back window. By default, this endpoint returns a 302 Redirect to the file. To receive a JSON response containing the URL instead, include the `noredirect` query parameter. To receive compressed data, set the `Accept-Encoding` header to gzip.

| Element | Contract |
|---|---|
| `date` | Path segment, pattern `^\d{4}-\d{2}-\d{2}$` |
| Retention | **90-day rolling look-back window** |
| Default behavior | `302` redirect straight to the blob |
| `noredirect` | Query param; returns `{"url": "<pre-signed URL>"}` instead |
| `Accept-Encoding: gzip` | Optional; requests compressed payload |
| `Content-Type` | Declared `required: true`, set to `application/json` |
| Errors | `400`, `401`, `403` — all `{"error": "..."}` |

The reference downloader confirms the practical shape ([main.py](https://raw.githubusercontent.com/nfa-llc/quant-historical/master/main.py)): it sets `noredirect=true` as a persistent session param, sends `Accept-Encoding: gzip`, gets the signed URL, then fetches it in a second request. Its `download_and_decompress` function is instructive about a real vendor quirk the README calls out:

> Some historical responses may be gzip-compressed while others may already be plain JSON. The script checks the response bytes and only decompresses when the payload is actually gzip data.

The vendor's own client therefore **sniffs the gzip magic bytes** (`\x1f\x8b`) rather than trusting `Content-Encoding`. Any hardened client should do the same.

The downloader also confirms the package/category roster we hold is the vendor's own intended matrix — its `ACTIVE_*` lists enumerate exactly `state` × (`gex_full`/`gex_zero`/`gex_one`, `delta|gamma|vanna|charm` × `_zero`/`_one`), `classic` × (`gex_full`/`gex_zero`/`gex_one`), and `orderflow` × `orderflow`.

> **Vendor silence on `/hist` payload shape.** The spec documents only the *envelope* — the response containing the signed URL. It says **nothing** about the structure of the file behind that URL: not whether it is an array or object, not the snapshot interval, not the number of records per day, not the timestamp basis, not session boundaries. `main.py` hints only that it handles both (`isinstance(data, list)` → "records", `isinstance(data, dict)` → "keys"). **The 62-day archive is the only authority on hist file structure.** Nothing published lets us verify our reader against a vendor contract.

---

## 7. Live feeds — REST and WebSocket

### Cadence and rate limits

This is documented in exactly one place, [AGENTS.md](https://raw.githubusercontent.com/nfa-llc/gexbot-openapi/master/AGENTS.md), and nowhere in the spec or README:

> **Rate limiting**: Data is not updated more than once per second. Requests should not exceed one request per second per ticker per metric.
>
> **HTTP client configuration**: Request timeouts should be configured to no more than 1 second.

So the vendor-stated ceiling is **1 Hz per ticker per metric** — both the update cadence and the polling limit. A 1-second client timeout is the vendor's own recommendation, which implies they consider a slow response stale rather than worth waiting for. This corroborates the principals' Discord statement that max-change values "update every second."

### Trading-hours restriction

From [docs/websocket.md](https://raw.githubusercontent.com/nfa-llc/gexbot-openapi/master/docs/websocket.md), stated as a warning at the top of the document:

> ⚠️ Data is only published during New York Stock Exchange cash hours (9:30 AM–4:00 PM ET).

This is written about the WebSocket feed specifically. **The vendor does not state anywhere whether the REST live endpoints follow the same window** — our poller's observed behavior is the only evidence on that point.

### WebSocket architecture (Quant only)

Transport is Azure Web PubSub. Messages are **Zstandard-compressed Protocol Buffers** — the vendor does not publish the `.proto` schema in either repo, so decoding requires either the reference client or reverse-engineering.

Flow: `POST /v2/negotiate` with `{"groups": [...]}` → returns hub URLs with embedded access tokens, and **auto-joins** the requested groups server-side. `PATCH /v2/negotiate` replaces the active group set without reconnecting, and is a **full replacement** — omitted groups are dropped. `GET /negotiate` is deprecated legacy (it returned a `prefix` like `blue` that legacy clients had to prepend to group names).

Six hubs: `classic`, `state_gex`, `state_greeks_zero`, `state_greeks`, `state_greeks_one`, `orderflow`. Group naming is `{ticker}_{package}_{category}`, e.g. `SPX_state_gamma_zero`, `ES_SPX_orderflow_orderflow`.

Limits: **150 active groups** on a standard Quant key; duplicates count once; over-limit requests return `403`. A successful POST negotiate closes existing connections on the same slot.

### Explicit-expiry groups — a live-only capability with no archive equivalent

The most consequential thing in the WebSocket doc for a Quant subscriber. Groups can target a **specific expiration** rather than the front/second ordinal: `SPX_state_gamma_20260717`, `SPX_classic_gex_20260717`, `SPX_orderflow_20260717`. Valid dates come from `GET /v2/options/{ticker}/expiries`, which returns every expiry from today through today+90 days, "including non-Friday expirations where available." Strip the dashes to build the suffix.

The vendor's constraints on these:

> - Explicit expiry groups are realtime WebSocket/PubSub-only; they are **not persisted to REST history**.
> - Explicit expiry groups are published on a lower cadence than standard groups, currently about every 5 seconds.
> - Volume groups are not available on the API WebSocket feed.

**This is the sharpest live-vs-hist asymmetry in the product.** Per-expiry greek surfaces exist only in the realtime feed and are unrecoverable after the fact — no `/hist` call can reconstruct them. If per-expiry granularity ever matters to a study, it has to be captured live, and the 90-day `/hist` window offers no second chance. Their 5-second cadence also means they are not simply a finer-grained version of the 1-second standard groups.

---

## 8. Data dictionary

### 8.1 `basic_response` — classic and state chart endpoints

Returned by `/{ticker}/classic/{category}` and `/{ticker}/state/{category}`. Field list is from the spec; the worked example is from the [spec README](https://github.com/nfa-llc/gexbot-openapi).

| Field | Type | Vendor description |
|---|---|---|
| `timestamp` | int64 | *(none)* — example value `1777492800` is Unix epoch seconds |
| `ticker` | string | *(none)* |
| `min_dte` | int | *(none)* — example `0` |
| `sec_min_dte` | int | *(none)* — example `1` |
| `spot` | double | *(none)* — underlying price |
| `zero_gamma` | float | *(none)* — the gamma flip level; the `majors_response` summary calls it "Zero Gamma" |
| `major_pos_vol` | float | *(none)* — "Major Positive GEX by Volume" per the majors endpoint summary |
| `major_pos_oi` | float | *(none)* — Major Positive GEX by Open Interest |
| `major_neg_vol` | float | *(none)* — Major Negative GEX by Volume |
| `major_neg_oi` | float | *(none)* — Major Negative GEX by Open Interest |
| `strikes` | array of arrays of float | *(none)* |
| `sum_gex_vol` | float | *(none)* |
| `sum_gex_oi` | float | *(none)* |
| `delta_risk_reversal` | float | *(none)* |
| `max_priors` | array of arrays of float | *(none)* |

**Every one of these fields is undescribed in the spec.** The spec declares types only. The `major_*` glosses above are recovered from the `/majors` endpoint's `summary` line — "Returns the key GEX levels (Zero Gamma, Major Positive/Negative GEX by OI and Volume)" — which is the closest the vendor comes to defining them.

Two schema-only fields never appear in any documented response body: `major_long_gamma` and `major_short_gamma` are defined as standalone schemas in both spec versions but are not referenced by `basic_response`, `orderflow_response`, `majors_response`, or `maxchange_response`. Our canonical notes treat `major_short_gamma` as a real field of the `gex_zero` response (`canonical/convexity_ladder.md`). If it is present in live or hist payloads, it is **undocumented in the spec** — worth confirming against the archive.

#### The `strikes` array — structure is NOT documented

The spec types `strikes` as `array of array of float` and stops there. No ordering, no element count, no units. The only evidence the vendor provides is the README's worked example:

```json
"strikes": [
  [6890, -228.01, -86.9, [-240.55, -243.15, -245.22, -221.27, -220.12]],
  [6895,  -48.47,  69.76, [ -49.05,  -46.76,  -45.55,  -45.53,  -42.97]],
  [7380,   44.16,  75.99, [      0,    47.7,    47.3,       0,    40.55]],
  [7385,    5.5,   14.27, [      0,       0,       0,       0,       0]]
]
```

What is **observable** from the example: element 0 ascends monotonically across rows and lands on round 5-point increments against a `spot` of 7138.55, so it is the strike price. Elements 1 and 2 are signed floats that change sign around spot. Element 3 is a nested 5-float array.

What is **not documented**: whether elements 1 and 2 are volume-based and OI-based GEX respectively (plausible given `sum_gex_vol`/`sum_gex_oi` and the `major_*_vol`/`major_*_oi` pairing, and given that the example's element-2 values flip from negative below spot to positive above), and what the 5-element nested array holds. **Treat the ordering as unverified.** Our archive can establish it by checking whether the per-strike element-1 values sum to `sum_gex_vol` and element-2 to `sum_gex_oi` — a one-query test that would convert this from inference to measurement.

The schema also declares the inner arrays as `array of float`, which cannot represent the nested array in the vendor's own example. The published schema is wrong about its own example.

#### `max_priors` — structure is not documented

Typed `array of array of float`; the README example shows six `[strike, value]` pairs. Separately, `maxchange_response` defines exactly six lookback windows — `current`, `one`, `five`, `ten`, `fifteen`, `thirty` — each a 2-element float array, and the principals state in Discord that these "update every second" and "are lookbacks."

The six-and-six correspondence is suggestive but **the vendor never connects them**. Reading `max_priors` as per-lookback `[strike, value]` at the same six intervals is an inference, and it is recorded here as one.

### 8.2 `orderflow_response` — the newly entitled package

Returned by `/{ticker}/orderflow/orderflow`. This is the least documented and most operationally interesting surface, so the full field list follows.

`orderflow_response` declares **48 properties**: it repeats 14 of `basic_response`'s 15 — `timestamp`, `ticker`, `spot`, `min_dte`, `sec_min_dte`, `zero_gamma`, `major_pos_vol`, `major_pos_oi`, `major_neg_vol`, `major_neg_oi`, `strikes`, `sum_gex_vol`, `sum_gex_oi`, `delta_risk_reversal` — and adds **34** orderflow-specific scalars. So an orderflow snapshot carries a full per-strike GEX ladder *plus* the flow metrics. It is not a narrow add-on feed.

The single `basic_response` field orderflow does **not** carry is `max_priors`. The vendor does not explain the omission.

The 34 additional fields, grouped by the naming pattern:

**Gamma classification (4)** — `z_mlgamma`, `z_msgamma`, `o_mlgamma`, `o_msgamma`
**Call/put magnitude (4)** — `zero_mcall`, `zero_mput`, `one_mcall`, `one_mput`
**Ratios (4)** — `zcvr`, `ocvr`, `zgr`, `ogr`
**Higher-order greeks (4)** — `zvanna`, `ovanna`, `zcharm`, `ocharm`
**Aggregate DEX (6)** — `agg_dex`, `agg_call_dex`, `agg_put_dex`, `one_agg_dex`, `one_agg_call_dex`, `one_agg_put_dex`
**Net DEX (6)** — `net_dex`, `net_call_dex`, `net_put_dex`, `one_net_dex`, `one_net_call_dex`, `one_net_put_dex`
**Flow deltas (6)** — `dexoflow`, `gexoflow`, `cvroflow`, `one_dexoflow`, `one_gexoflow`, `one_cvroflow`

> **The vendor publishes no definition for any of these 34 fields.** Not one carries a `description` in either spec version. They are not defined in the README, in `websocket.md`, in `AGENTS.md`, or in the reference downloader. I also searched this repo's existing canonical and community tiers — including the principals' Discord archive and Freddy's orderflow series — and **none of these field names appears anywhere**. The community material discusses orderflow concepts (convexity, the OrderFlow view, spike origination at strikes) but never the API field names.

The naming pattern is legible and worth recording as a **structural observation, not a vendor claim**: the `z_`/`zero_` prefix and the `o_`/`one_` prefix mirror the `_zero`/`_one` category split, so nearly every metric is published as a 0DTE/second-expiry pair. `ml`/`ms` plausibly read as "max long"/"max short" against the principals' documented long-vs-short gamma classification, and `cvr` plausibly as a convexity ratio given the convexity ladder's centrality in the vendor's methodology — but **both are guesses and neither is confirmed by any vendor text**. The types are also internally inconsistent: `orderflow_response` refs these fields to `_float`, while the same names defined as standalone schemas are typed `integer`.

**Practical consequence:** the orderflow archive's semantics have to be established empirically or by asking the vendor directly. There is no document to read. Given the field count and the 0/1 pairing, a distribution-and-correlation pass against the 62-day archive is the fastest route to meaning — and a vendor question is warranted, since this is a paid entitlement shipped with zero field documentation.

### 8.3 `majors_response`

From `/{ticker}/{package}/{category}/majors`. Summary: "Returns the key GEX levels (Zero Gamma, Major Positive/Negative GEX by OI and Volume)."

Fields: `zero_gamma`, `mpos_vol`, `mpos_oi`, `mneg_vol`, `mneg_oi`, `net_gex_vol`, `net_gex_oi`, `timestamp`, `ticker`, `spot`. Note the **abbreviated names** — `mpos_vol` here versus `major_pos_vol` in `basic_response` — and that `net_gex_vol`/`net_gex_oi` appear *only* here, with no `basic_response` equivalent (`sum_gex_*` is the closest, and the vendor does not say whether sum and net are the same quantity). No field descriptions.

### 8.4 `maxchange_response`

From `/{ticker}/{package}/{category}/maxchange`. Summary: "Returns the strikes with the most significant GEX change over various look-back periods."

Fields: `timestamp`, `ticker`, then six lookback windows — `current`, `one`, `five`, `ten`, `fifteen`, `thirty` — each constrained to `minItems: 2, maxItems: 2` floats. The window names are undescribed but the endpoint summary establishes they are look-back periods; the principals' Discord confirms minute units and per-second updates. **Which element of each pair is strike and which is magnitude is not documented**, though the `max_priors` example's `[strike, value]` shape is the obvious parallel.

Neither `/majors` nor `/maxchange` is in our archive — they are live-only REST endpoints with no `/hist` package. Their content appears to be derivable from the `basic_response` ladder we do store, but the vendor never says so.

---

## 9. Live vs. historical — consolidated differences

| Dimension | Live (REST + WS) | Historical (`/hist`) |
|---|---|---|
| Tier | Classic/State/Orderflow per package; WS is Quant-only | **Quant only** |
| Cadence | 1 Hz standard; ~5 s for explicit-expiry WS groups | Not documented |
| Availability | NYSE cash hours 9:30–16:00 ET (stated for WS) | Any date in window |
| Retention | n/a | **90-day rolling** |
| Transport | JSON over HTTPS; zstd-Protobuf over WSS | Pre-signed blob URL, JSON, optionally gzipped |
| Per-expiry granularity | **Yes** — explicit-expiry groups | **No** — "not persisted to REST history" |
| `/majors`, `/maxchange` | Yes | No |
| Quant-only tickers (`XSP`, `SOXL`, …) | WebSocket only | No |
| Payload schema | Documented (fields typed, undescribed) | **Entirely undocumented** |

The 90-day retention against our 62-trading-day archive is the operationally urgent line: 62 trading days is roughly 88 calendar days, so **the earliest archived dates are at or near the edge of the vendor's window**. Anything not yet downloaded from early May is either already gone or about to be.

---

## 10. What the vendor does not document

Recorded plainly so these are not mistaken for things we simply failed to find:

1. **All 34 orderflow field meanings.** Nothing, anywhere, in any tier of source. The largest gap by far, and it sits on a newly-active entitlement.
2. **The `/hist` file structure.** Record shape, snapshot interval, count per day, timestamp basis, session boundaries — all absent.
3. **The `strikes` tuple ordering** and the meaning of its nested 5-element array. The published schema contradicts the vendor's own example.
4. **`max_priors` structure**, and its relationship to the `maxchange` lookback windows.
5. **`zero` vs `one` disambiguation** — "next expiry+1" (classic) versus "1dte" (state) are left contradictory.
6. **`sum_*` vs `net_*`** — whether `sum_gex_vol` and `net_gex_vol` denote the same quantity.
7. **`major_long_gamma` / `major_short_gamma`** — defined as schemas, referenced by no response.
8. **The Protobuf schema** for WebSocket messages. No `.proto` published in either repo.
9. **Whether REST live endpoints honor the cash-hours restriction** stated for WebSocket.
10. **Pricing, request quotas, and historical-download volume limits.**
11. **Units throughout.** No field anywhere states whether GEX is in shares, notional dollars, or contracts-per-1%. `canonical/metrics_math.md` reasons about this from the math, but the API never declares it.
12. **Any changelog.** Neither repo publishes release notes; the only version signal is the `info.version` string in the spec.

---

## 11. Recommended follow-ups

**Answerable from our own archive, no vendor contact needed:**
- Resolve the `strikes` tuple ordering by testing whether per-strike elements sum to `sum_gex_vol` / `sum_gex_oi`.
- Settle the `zero`/`one` question by checking whether `sec_min_dte` is ever ≠ 1 across the 62 days.
- Confirm whether `major_short_gamma` / `major_long_gamma` actually appear in payloads.
- Characterize the 34 orderflow fields by distribution and cross-correlation against the State greeks we hold for the same timestamps.

**Requires the vendor:**
- Ask for orderflow field definitions. This is a paid entitlement with no documentation; it is a reasonable support request, not a favor.
- Ask whether the `.proto` schema can be shared, if the WebSocket feed is ever of interest.

**Operational, time-sensitive:**
- The 90-day window makes early-May archive dates expiring inventory. Verify coverage completeness at the old end before it ages out.
- Refresh the canonical spec to 2.3.0 (saved as a sidecar, not yet promoted) and record the update in the repo's revision log per the canonical-tier contract.

---

## Appendix — endpoint reference (v2.3.0)

Base URL `https://api.gex.bot/v2`, except `/{package}/categories` and `/tickers/quant`, which the spec routes to `https://api.gex.bot` without the `/v2` prefix.

| Endpoint | Tiers | Response |
|---|---|---|
| `/{ticker}/classic/{category}` | Classic, State, Orderflow, Quant | `basic_response` |
| `/{ticker}/state/{category}` | State, Orderflow, Quant | `basic_response` |
| `/{ticker}/orderflow/{category}` | Orderflow, Quant | `orderflow_response` |
| `/{ticker}/classic/{category}/majors` | Classic, State, Orderflow, Quant | `majors_response` |
| `/{ticker}/state/{category}/majors` | State, Orderflow, Quant | `majors_response` |
| `/{ticker}/classic/{category}/maxchange` | Classic, State, Orderflow, Quant | `maxchange_response` |
| `/{ticker}/state/{category}/maxchange` | State, Orderflow, Quant | `maxchange_response` |
| `/tickers` | Public (no auth) | stocks / indexes / futures |
| `/{package}/categories` | Public (no auth) | array of category names |
| `/tickers/quant` | Quant | stocks / indexes (WS-only tickers) |
| `/options/{ticker}/expiries` | Quant | expiries within today+90d |
| `/hist/{ticker}/{package}/{category}/{date}` | **Quant** | pre-signed URL |
| `POST /negotiate` | **Quant** | hub URLs, auto-joined groups |
| `PATCH /negotiate` | **Quant** | group replacement result |
| `GET /negotiate` | **Quant** | deprecated legacy |
| `/research/{ticker}/{metric}` | Research addon (`gbR` key) | chart/data, many formats |

---

## Related repos (2026-08-06)

Two GexBot-adjacent repositories were reviewed by reading their source, not their
READMEs. Both were cloned to a scratchpad, inspected read-only, and **neither was
installed or executed**. Nothing below is derived from running their code.

| Repo | Author | License | Commits | Last commit |
|---|---|---|---|---|
| [nfa-llc/tradingview](https://github.com/nfa-llc/tradingview) | vendor (`jasperSha`) | PolyForm Noncommercial 1.0.0 | 6 | 2026-08-02 |
| [dgnsrekt/gexsync](https://github.com/dgnsrekt/gexsync) | third party (`dgnsrekt`) | MIT | 149 | 2026-08-05 |

### `nfa-llc/tradingview` — the vendor's own desktop integration

A Node.js companion process (~4,900 lines, **zero npm dependencies**, Node 22+)
that drives **TradingView Desktop** over the Chrome DevTools Protocol and draws
GEX/Gamma/Vanna/Charm profiles onto its charts. It is not a browser extension and
not a library — it launches TradingView Desktop with a debugging port, connects,
and injects a settings panel plus profile drawings.

Licensing is materially more restrictive than the spec repo: **PolyForm
Noncommercial 1.0.0, source-available, not open source.** The README explicitly
prohibits use "in connection with any paid product, paid service, subscription
service … market-data service, analytics service," and prohibits "replacing,
adapting, or configuring the integration to operate with a third-party or
competing commercial data feed." Lifting code from this repo into our tooling is a
licensing decision, not merely a technical one.

#### It publishes the Protobuf wire schema this survey listed as undocumented

`app/expiry-protobuf.js` (197 lines) is a hand-rolled Protobuf reader plus
`node:zlib`'s `zstdDecompressSync`. It resolves gap #8 in §10 — the `.proto`
schema is not published as a `.proto`, but the **field numbering and scaling are
now fully readable from vendor code**.

`decodeGex` maps the GEX payload by field number: 1 `timestamp`, 2 `ticker`,
3 `min_dte`, 4 `sec_min_dte`, 5 `spot`, 6 `zero_gamma`, 7–10 the four `major_*`
fields, 11 repeated `strikes`, 12 `sum_gex_vol`, 13 `sum_gex_oi`,
14 `delta_risk_reversal`. Wire values are integers: most are scaled by **100**,
the three sum/risk-reversal fields by **1000**, and signed fields use zigzag
encoding. (This scaling is a wire-format detail — REST JSON already carries
decimals.)

#### It confirms the `strikes` tuple is 4-element and names the fourth "priors"

`decodeStrike` returns exactly four positions: `field1/100`,
`zigzag(field2)/100`, `zigzag(field3)/100`, and a nested repeated array the vendor
names **`priors`**. This upgrades part of §8.1 from "undocumented" to
vendor-confirmed: the 4-element shape is real, elements 1 and 2 are signed, and
the nested array is priors. **The vendor still does not name elements 1 and 2** —
the decoder is positional. The volume-versus-OI reading remains unconfirmed by
vendor material (but see the gexsync corroboration below).

It also confirms the published OpenAPI schema is wrong: the spec types the inner
arrays as flat `array of float`, which cannot represent the nested priors array
that the vendor's own decoder builds.

#### It reveals an undocumented second response schema — and our archive confirms it

`decodeGreek` decodes a payload **structurally different from `basic_response`**:
1 `timestamp`, 2 `ticker`, 3 `spot`, 4 `min_dte`, 5 `sec_min_dte`,
6 `major_positive`, 7 `major_negative`, 8 `major_long_gamma`,
9 `major_short_gamma`, 10 repeated `mini_contracts`.

This corrects §10 items 3 and 7 and a claim in §8.1. `major_long_gamma`,
`major_short_gamma`, and `mini_contracts` are **not** orphan schemas — they are
the fields of the greek response. The OpenAPI spec declares
`/{ticker}/state/{category}` returns `basic_response` for *all* state categories;
**that is incorrect for the greek categories.**

Verified against our own live corpus (`data/corpus/2026-08-05/gexbot.jsonl`,
first record). The four greek routes return exactly the decoder's field set and
nothing else:

```
/SPX/state/gamma_zero -> [major_long_gamma, major_negative, major_positive,
                          major_short_gamma, min_dte, mini_contracts,
                          sec_min_dte, spot, ticker, timestamp]
```

No `strikes`, no `zero_gamma`, no `sum_gex_*`, no `delta_risk_reversal`. The
greek categories and the `gex_*` categories are **different schemas**, and any
reader assuming `basic_response` for `delta_zero`/`gamma_one`/etc. is wrong.

`mini_contracts` is confirmed as a **7-element** tuple, matching
`decodeMiniContract` position for position. From the same corpus record
(84 rows, every row length 7), with `spot` 7741.72:

```
[7685, 0.481, 0.315, -74.42, [-105.57, -103.02, -120.08], 0, null]
[7925, 0.851, 0.989,   2.00, [   1.72,     1.90,    2.07], 0, null]
```

Position 0 is the strike and position 3 is the signed greek exposure; position 4
is a priors array (**3 entries here, versus 5 in the classic `strikes` example** —
prior counts differ by payload type). Positions 1 and 2 are unnamed positive
floats in a ~0.3–1.3 band, position 5 was `0` and position 6 `null` in every
sampled row. **The vendor names none of these positions** — the decoder is
positional and our corpus confirms only the shape. Do not assume positions 1/2
are per-side IV; that is a guess, not a finding.

#### It is a complete, working zstd-Protobuf WebSocket client

This is the capability §7 flagged as the sharpest live-versus-hist asymmetry.
`app/companion.js` implements the full documented flow: `POST /negotiate` with a
group list, `PATCH /negotiate` for group replacement, per-hub `WebSocket`
connections, and message decode. Three details go **beyond** what
`docs/websocket.md` states:

1. The subprotocol is **`json.reliable.webpubsub.azure.v1`**, not the
   `json.webpubsub.azure.v1` shown in the vendor's own `wscat` example.
2. The client must **acknowledge sequence IDs** —
   `socket.send(JSON.stringify({ type: "sequenceAck", sequenceId }))` — which the
   WebSocket doc never mentions. The reliable protocol requires it.
3. Payloads arrive as a base64 `data` field inside a JSON envelope, wrapped in a
   Protobuf `Any` (type URL + value), and only *then* zstd-compressed. The doc's
   "Zstandard-compressed Protobufs" understates the nesting.

It builds explicit-expiry groups directly (`${symbol}_state_${profile}_${compact}`
on the `state_greeks` hub) and enforces the documented 150-group cap client-side.

**Enterprise relevance.** This is a working reference for the one capability we
established is unrecoverable after the fact. It does not duplicate our poller,
backfill, or distiller — it is a charting front-end — but it is the missing piece
for live explicit-expiry capture. Note the licensing constraint above before
adapting any of it.

#### Security posture (vendor repo)

Reviewed because it launches a browser with a debugging port. The posture is
careful:

- Debug port is bound to **`--remote-debugging-address=127.0.0.1`** (loopback,
  not `0.0.0.0`).
- API key lives in a gitignored `api-key.txt`, `chmod 600` enforced in code on
  every read/write; the key is explicitly stripped before config is serialized
  (`delete copy.apiKey`). Runtime/state/config dirs are `chmod 700`.
- Network egress is limited to `api.gex.bot`, `api.gexbot.com`, and localhost.
  No telemetry, no analytics, no third-party hosts.
- The Linux `--no-sandbox` fallback is a **real reduction in Chromium renderer
  isolation**, but it is opt-in, prompted with an explanation, persisted only via
  an explicit consent file, and never runs as root.

It also settles the auth contradiction flagged in §2: the vendor's current code
sends `Authorization: Bearer ${apiKey}`, not the `Basic` its older
`quant-historical` sample uses. **Bearer is correct.**

#### A third key type

The README documents a **`gexbot_tradingview_`** key prefix, created from
https://www.gexbot.com/user/connections. That is a third key type beyond the
`gexbot_custom_` and `research_` prefixes recorded in §2, and it is per-integration.
"A Quant-enabled API key is required for Quant profiles."

**Maturity:** 6 commits, single author, 2026-07-22 to 2026-08-02. No tests, no CI.
New and lightly exercised, but the code is disciplined.

### `dgnsrekt/gexsync` — third-party Chrome extension

A Manifest V3 Chrome extension (~5,300 lines, no build step, **zero npm
dependencies**) that keeps multiple gexbot.com tabs in sync across three modes
(Profiles, Ticker, Replay), and since 1.16.0 draws GEX major levels onto
TradingView web charts. MIT licensed. It is a **UI convenience layer over the
GEXbot web app** — it does not collect, store, or analyze market data.

**Enterprise relevance: essentially none.** It duplicates nothing we built and
obsoletes nothing. It has **no WebSocket client** — its own UI string concedes
"live streaming (WebSocket) will arrive later," and it polls REST on clock marks.
It therefore does **not** unlock explicit-expiry capture. Its GEXbot usage is one
full-chain REST call per ticker/source/category with a 500 ms anti-stampede cache.

Its one genuine value to us is **independent corroboration of two open questions
in this survey**, from a practitioner who reached the same conclusions separately:

- `background.js:145` — "strikes tuple is `[strike, netGEX_vol, netGEX_oi,
  [5 prior vol readings]]`". This matches §8.1's candidate reading exactly. It is
  a **third-party assertion, not vendor documentation**, but it now agrees with
  the vendor decoder's confirmed 4-element structure.
- `background.js:151` — "`gex_zero`=latest (**nearest expiry, not literally 0dte**
  — VIX has its own calendar), `gex_one`=next, `gex_full`=90d". Independent
  agreement with §5 that these are expiry-ordinal, not day-count. The VIX
  observation is a useful concrete case.

#### Trust assessment

Read with deliberate skepticism, since it is third-party code that runs in-browser
on an authenticated session. **Findings are reassuring, with two caveats.**

*Credentials.* All storage is `chrome.storage.local` — 86 call sites, and
**zero uses of `chrome.storage.sync`**, so keys are never uploaded to a Google
account. Keys travel only as `Authorization: Bearer` headers to their own APIs.

*Network reach.* Only 10 network call sites exist in the entire codebase (5 in the
background worker, 4 in TradingView scripts, 1 in the popup). Every absolute URL
resolves to a declared host: `gexbot.com`, `api.gex.bot`, `api.massive.com`,
`apewisdom.io`, plus `w3.org` (an SVG namespace string, not a request). **There is
no analytics, telemetry, beacon, or reporting endpoint of any kind.**

*The two non-vendor hosts are benign and opt-in.* `api.massive.com` is a
market-data API whose paths (`/v3/reference/tickers/`,
`/v2/aggs/ticker/…/range/1/day/…`) are Polygon-shaped — the UI labels it "Massive
(Polygon)". It requires the user's own key and is inert without one. **It is not
the bandwidth-sharing "Massive" proxyware SDK** — no such code exists in the repo.
`apewisdom.io` returns a public Reddit-mention ranking, needs no key, is off by
default, and the ticker match happens locally, so the site is never told which
symbol the user is viewing.

*`netwatch.js` is the highest-risk file by design and is genuinely narrow.* It
runs in the page's MAIN world at `document_start` and monkey-patches `fetch` and
`XMLHttpRequest`. It reads **only `url` and `status`**, filters to
`/gexbot\.com/`, and dispatches a DOM event when it sees a 429 or a 4xx/5xx on
`/hist/`. It never touches request or response **bodies**, never reads headers,
and never sends anything outward. A rate-limit detector, not an interceptor.

*No dynamic code execution.* No `eval`, no `new Function`, no `document.write`, no
`chrome.tabs.executeScript`, no remote script loading. No build step, so the
repository content is what runs. The only CI is a daily job that diffs the
packaged ticker list against GEXbot's `/tickers`; it runs their own two scripts
and nothing else. **No install-time code execution** — it is a load-unpacked
extension with no `npm install`.

**Caveat 1 — their safety doc understates current network reach.**
`knowledge/safety.md` (dated 2026-07-25) lists `host_permissions` as three hosts:
`gexbot.com`, `api.massive.com`, `apewisdom.io`. The shipped `manifest.json` grants
**five**, adding `api.gex.bot` and `api.gexbot.com` — added 2026-08-04 with the
TradingView overlay feature. The document was simply not updated alongside the
manifest, and the added hosts are the vendor's own API. But the practical lesson
stands: **audit the manifest, not the safety write-up.**

**Caveat 2 — minor DOM hygiene.** There are ~19 `innerHTML` assignments. Nearly
all are static icon/layout templates. `popup.js:102` interpolates user-typed
watchlist symbols into an `<option value="${s}">` without escaping. Worst case is
self-inflicted markup inside the extension's own popup — not a meaningful attack
path, since the input is the user's own and never crosses an origin — but it is
the one place unescaped input reaches the DOM.

**Maturity:** genuinely active — 149 commits and 27 tagged releases, last commit
2026-08-05, with five plain-Node test files (`.mjs`, no framework) covering ticker
shape, retry, cycling, and lines. **Bus factor 1**: a single author
(`dgnsrekt@pm.me`) wrote every commit.

*Aside:* the author's `knowledge/` directory is written in **OKF v0.1** with typed
frontmatter and an `index.md` entry point — the same knowledge format this
enterprise uses.

### Net effect on this survey

Three §10 gaps close or narrow, all from the **vendor** repo:

| §10 gap | New status |
|---|---|
| #8 Protobuf schema unpublished | **Closed** — field numbers, zigzag, and scaling readable from `expiry-protobuf.js` |
| #7 `major_long_gamma`/`major_short_gamma` orphaned | **Closed** — they are greek-response fields, confirmed in our corpus |
| #3 `strikes` tuple ordering | **Narrowed** — 4-element shape and "priors" vendor-confirmed; the vol/OI naming of elements 1–2 rests on third-party assertion |

And one gap is **added**: the OpenAPI spec's claim that `/{ticker}/state/{category}`
returns `basic_response` is wrong for the four greek categories, which return an
undocumented schema built on `mini_contracts`. Anything in our pipeline that
assumes one shape across all state categories should be checked against this.
