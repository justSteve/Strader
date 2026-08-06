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
