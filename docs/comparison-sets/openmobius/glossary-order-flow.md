# Glossary — the term decisions the Order Flow translation was held to

Work order §4: where Mobius's `term_aliases.json` maps a Chinese term to an
English canonical, adopt theirs; **where our register already uses a term, ours
wins**. Their map holds 726 mappings, 349 of which carry a CJK alias.

The Order Flow tranche turned out to need far fewer than the ~60 the order
estimated, because the school is volume-profile vocabulary rather than SMC/ICT
vocabulary. These are the terms that actually appear.

## Ours wins — our register already uses these

| Chinese | rendered | not rendered as | why |
|---|---|---|---|
| 成交量分布 | volume profile | volume distribution | our own instrument list (CLAUDE.md) names Session Volume Profile |
| 高成交量节点 | high-volume node (HVN) | dense volume zone | HVN is the term in `zone-framework-equivalence` |
| 低成交量节点 | low-volume node (LVN) | vacuum zone | ditto; and Carmine's LVN method is canon under that name |
| 价值区高点 / 低点 | value area high / low (VAH/VAL) | value zone top/bottom | Market Profile vocabulary, already on Steve's charts |
| 控制点 | point of control (POC) | control point | ditto |
| 订单块 | order block | order zone | `zone-framework-equivalence` fixes this |
| 失衡区 | imbalance / FVG | disequilibrium zone | FVG where the source says FVG, imbalance where it says 失衡 |
| 流动性缺口 | liquidity gap | liquidity vacuum | matches OFB's usage |
| 级别 | timeframe | level, grade | "level" is already taken by price levels; using it twice would be the error the whole register format exists to prevent |
| 均线 | moving average | mean line | — |
| 散户 | retail | retail investors | matches OFB-03's wording |
| 机构 / 做市商 | institutions / market makers | the smart money | kept distinct: the source uses both and means slightly different actors |

## Theirs adopted

| Chinese | Mobius canonical | note |
|---|---|---|
| 结构破坏 / 结构突破 | Break of Structure | their map, unchanged |
| 平衡价格区间 | Balanced Price Range | their map |
| 看跌公允价值缺口 | Bearish Fair Value Gap | their map |
| 积累-操纵-派发模型 | Accumulation Manipulation Distribution | their map |

## Author-specific terms — kept, with a gloss

Teach-Wuyuan uses named constructions that are his, not standard vocabulary.
Flattening them into generic English would lose the fact that they are *his named
things*, which matters when grading a claim's provenance.

| Chinese | rendered | gloss |
|---|---|---|
| 破土 / 破组 | "breaking ground" / structure break confirmed | his term for a break that is then re-tested before it counts |
| 破底翻 | break-the-low-and-turn | sweep the low, then reverse up |
| 飞机模型 | the aeroplane model | two hidden structures then a large down candle firing off a fast decline |
| 末日战车 | doomsday chariot | a near-vertical daily advance |
| 车针 / 插针 | inducement wick / wick | 插针 is the plain wick; 车针 carries the inducement sense |
| 债务缺口 | debt gap | a gap below the market "owes" |
| 月牙缺口 | crescent gap | — |
| 纵仓 | commit size | a concentrated, committed entry |
| 洗盘 | shakeout | — |
| 支阻互换 | support-resistance flip | — |
| 收线破坏 | a close that breaks | load-bearing: it is the exact thing OFB-23 forbids, so it is never softened to "confirmation" |
| 乖离率 | extension from the moving average | — |
| 套牢盘 | trapped longs | matches OFB-10's "trapped participants" |
| 横有多长竖有多高 | "the longer the base, the higher the rise" | a Chinese market adage, rendered with its sense |
| 下水道 | the sewer | his term for deeply discounted price; kept because it is voice, not analysis |

## One term deliberately NOT harmonised

The source's `vrvp` card lists **`VWAP`** among its aliases. VWAP is a different
indicator. It is carried through verbatim rather than corrected, because
correcting a source's alias map inside a comparison set would hide a defect that
a later automated merge would trust. It is flagged in
`convergence-order-flow.md` instead.

[st-ow3p]
