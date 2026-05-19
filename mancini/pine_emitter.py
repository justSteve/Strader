"""Generate Pine Script v6 source for Mancini's forecast levels.

The emitter bakes ALL daily levels into the source. Visibility is
controlled at runtime by Pine inputs: dynamic radius from price,
visible-range lookback, and session-aware touched-already filter.
A 'key levels' override (parser-extracted from Mancini's bull/bear case
discussion) always renders regardless of the other filters.
"""
from __future__ import annotations

from datetime import datetime
from .parser import ManciniEmail, Level


PINE_TEMPLATE = '''//@version=6
// Mancini Forecast — {forecast_date}
// Source: {subject}
// Generated: {generated_at}
// Pre-window: [{window_low} … {window_high}] (kept {n_kept}/{n_total}; dropped {n_dropped})
// Kept tiers: {n_maj_sup} major sup, {n_min_sup} minor sup, {n_maj_res} major res, {n_min_res} minor res
// Key levels (parser-tagged from bull/bear case): {key_summary}
indicator("Mancini Forecast {forecast_date}", overlay=true, max_lines_count=500, max_labels_count=500)

// === Activation ===
useRadius        = input.bool(true,  "A. Radius from price",        group="Activation", tooltip="Hide levels farther than 'radius' from a smoothed close (SMA reduces flicker at edge)")
radius           = input.float(60,   "Radius (points)",              group="Activation", minval=1, maxval=500, step=5)
radiusSmooth     = input.int(5,      "Centerpoint SMA (bars)",        group="Activation", minval=1, maxval=50, tooltip="Smooths close into the radius centerpoint so edge-of-radius levels don't flicker on every tick")

useVisible       = input.bool(false, "B. Visible-range only",        group="Activation", tooltip="Hide levels outside the lookback bars' high/low")
visibleLookback  = input.int(150,    "Visible lookback (bars)",       group="Activation", minval=10, maxval=2000)

useSessionFilter = input.bool(false, "C. Hide touched-today levels", group="Activation", tooltip="Hide any level that price has crossed during today's session")
touchTolerance   = input.float(2,    "Touch tolerance (points)",      group="Activation", minval=0, step=0.25)

alwaysShowKey    = input.bool(false, "Always show key levels",        group="Activation", tooltip="Mancini's narrative-cited levels render regardless of other filters")
nonKeyAlpha      = input.int(50,    "Non-key transparency (%)",       group="Activation", minval=0, maxval=100, tooltip="Key levels render opaque; non-key levels get this transparency")

// === Display ===
showMajor    = input.bool(true,  "Show major levels", group="Display")
showMinor    = input.bool(true,  "Show minor levels", group="Display")
showLabels   = input.bool(true,  "Show price labels", group="Display")
extendRight  = input.int(10,     "Extend right (bars)", group="Display", minval=0, maxval=500)
historyBack  = input.int(300,    "History back (bars)", group="Display", minval=50, maxval=2000)

// === Colors (base — actual transparency picked per-level from key-ness) ===
cMajSup = input.color(#26a69a, "Major support",    group="Colors")
cMinSup = input.color(#26a69a, "Minor support",    group="Colors")
cMajRes = input.color(#ef5350, "Major resistance", group="Colors")
cMinRes = input.color(#ef5350, "Minor resistance", group="Colors")

// === Level data (codegen) ===
var arrMajSup     = {maj_sup}
var arrMajSupKey  = {maj_sup_key}
var arrMinSup     = {min_sup}
var arrMinSupKey  = {min_sup_key}
var arrMajRes     = {maj_res}
var arrMajResKey  = {maj_res_key}
var arrMinRes     = {min_res}
var arrMinResKey  = {min_res_key}

// === Per-level touched state (session-aware) ===
var arrMajSupT = array.new<bool>(array.size(arrMajSup), false)
var arrMinSupT = array.new<bool>(array.size(arrMinSup), false)
var arrMajResT = array.new<bool>(array.size(arrMajRes), false)
var arrMinResT = array.new<bool>(array.size(arrMinRes), false)

resetTouched(array<bool> arr) =>
    for i = 0 to array.size(arr) - 1
        array.set(arr, i, false)

markTouched(array<float> prices, array<bool> touched, float tol) =>
    for i = 0 to array.size(prices) - 1
        p = array.get(prices, i)
        if low <= p + tol and high >= p - tol
            array.set(touched, i, true)

sessionStart = ta.change(time("D")) != 0
if sessionStart
    resetTouched(arrMajSupT)
    resetTouched(arrMinSupT)
    resetTouched(arrMajResT)
    resetTouched(arrMinResT)

markTouched(arrMajSup, arrMajSupT, touchTolerance)
markTouched(arrMinSup, arrMinSupT, touchTolerance)
markTouched(arrMajRes, arrMajResT, touchTolerance)
markTouched(arrMinRes, arrMinResT, touchTolerance)

// === Visible-range proxy ===
visHigh = ta.highest(high, visibleLookback)
visLow  = ta.lowest(low,  visibleLookback)

// Smoothed centerpoint for radius — avoids flicker when price ticks across a level
centerPrice = ta.sma(close, radiusSmooth)

shouldShow(float price, bool isKey, bool touched) =>
    pass = true
    if useRadius and math.abs(price - centerPrice) > radius
        pass := false
    if useVisible and (price > visHigh or price < visLow)
        pass := false
    if useSessionFilter and touched
        pass := false
    if alwaysShowKey and isKey
        pass := true
    pass

// === Draw (with cleanup so re-evaluation on each tick doesn't stack objects) ===
var array<line>  _lines  = array.new<line>()
var array<label> _labels = array.new<label>()

drawLevels(array<float> prices, array<bool> keys, array<bool> touched, color baseCol, string lineStyle, int lineWidth, string tag) =>
    for i = 0 to array.size(prices) - 1
        p = array.get(prices, i)
        isKey = array.get(keys, i)
        t = array.get(touched, i)
        if shouldShow(p, isKey, t)
            x1 = bar_index - historyBack
            x2 = bar_index + extendRight
            lineCol = color.new(baseCol, isKey ? 0 : nonKeyAlpha)
            array.push(_lines, line.new(x1, p, x2, p, xloc.bar_index, extend.none, lineCol, lineStyle, lineWidth))
            if showLabels
                keyTag = isKey ? "K " : ""
                array.push(_labels, label.new(x2, p, keyTag + str.tostring(p, "#.##") + tag, xloc.bar_index, yloc.price, color.new(color.black, 100), label.style_label_left, baseCol, size.small))

if barstate.islast
    for ln in _lines
        line.delete(ln)
    array.clear(_lines)
    for lb in _labels
        label.delete(lb)
    array.clear(_labels)

    if showMajor
        drawLevels(arrMajSup, arrMajSupKey, arrMajSupT, cMajSup, line.style_solid,  2, " S*")
        drawLevels(arrMajRes, arrMajResKey, arrMajResT, cMajRes, line.style_solid,  2, " R*")
    if showMinor
        drawLevels(arrMinSup, arrMinSupKey, arrMinSupT, cMinSup, line.style_dashed, 1, " S")
        drawLevels(arrMinRes, arrMinResKey, arrMinResT, cMinRes, line.style_dashed, 1, " R")
'''


def _format_floats(values: list[float]) -> str:
    if not values:
        return "array.new<float>()"
    return "array.from(" + ", ".join(f"{v}" for v in values) + ")"


def _format_bools(values: list[bool]) -> str:
    if not values:
        return "array.new<bool>()"
    return "array.from(" + ", ".join("true" if v else "false" for v in values) + ")"


def _in_window(price: float, low: float | None, high: float | None) -> bool:
    if low is not None and price < low:
        return False
    if high is not None and price > high:
        return False
    return True


def emit(
    email: ManciniEmail,
    *,
    window_low: float | None = None,
    window_high: float | None = None,
    generated_at: str | None = None,
) -> str:
    """Render Pine v6 source from a parsed Mancini email.

    window_low/high act as an OPTIONAL pre-filter at codegen time. By
    default no pre-filter — every published level is baked in and Pine
    handles visibility via runtime activation toggles.
    """
    sup_kept = [l for l in email.support_levels if _in_window(l.price, window_low, window_high)]
    res_kept = [l for l in email.resistance_levels if _in_window(l.price, window_low, window_high)]
    n_total = len(email.support_levels) + len(email.resistance_levels)
    n_kept = len(sup_kept) + len(res_kept)

    key_set = set(email.key_levels)

    def split_tier(levels: list[Level], tier: str) -> list[Level]:
        if tier == "major":
            return [l for l in levels if l.annotation == "major"]
        return [l for l in levels if l.annotation != "major"]

    maj_sup = split_tier(sup_kept, "major")
    min_sup = split_tier(sup_kept, "minor")
    maj_res = split_tier(res_kept, "major")
    min_res = split_tier(res_kept, "minor")

    def prices(ls: list[Level]) -> list[float]:
        return [l.price for l in ls]

    def keys(ls: list[Level]) -> list[bool]:
        return [l.price in key_set for l in ls]

    key_in_kept = sorted({p for p in key_set if any(
        p == l.price for l in sup_kept + res_kept
    )})
    key_missing = sorted(key_set - set(key_in_kept))
    key_summary = (
        f"{len(key_in_kept)} matched ({', '.join(str(p) for p in key_in_kept)})"
        + (f"; {len(key_missing)} unmatched ({', '.join(str(p) for p in key_missing)})" if key_missing else "")
    )

    return PINE_TEMPLATE.format(
        forecast_date=email.date or "unknown",
        subject=email.subject or "unknown",
        generated_at=generated_at or datetime.now().isoformat(timespec="seconds"),
        window_low="-inf" if window_low is None else window_low,
        window_high="+inf" if window_high is None else window_high,
        n_kept=n_kept,
        n_total=n_total,
        n_dropped=n_total - n_kept,
        n_maj_sup=len(maj_sup),
        n_min_sup=len(min_sup),
        n_maj_res=len(maj_res),
        n_min_res=len(min_res),
        key_summary=key_summary,
        maj_sup=_format_floats(prices(maj_sup)),
        maj_sup_key=_format_bools(keys(maj_sup)),
        min_sup=_format_floats(prices(min_sup)),
        min_sup_key=_format_bools(keys(min_sup)),
        maj_res=_format_floats(prices(maj_res)),
        maj_res_key=_format_bools(keys(maj_res)),
        min_res=_format_floats(prices(min_res)),
        min_res_key=_format_bools(keys(min_res)),
    )
