# /ES Algo Survey: Who Has Published Code-Driven Intraday /ES Trading

*st-cg63 · 2026-09-25 · Groundwork for the Jev-driven SPX Singletons variant (signal from /ES orderflow on ~5-second bars, vehicle SPX 0DTE singles, ~$25 stop, ~$200 target, liberal re-entry, dozens of trades a day). Jev itself is out of scope.*

**Labels.**
- **[measured]**: regulator, academic or audited data.
- **[live-self]**: the author's own live trading, unaudited.
- **[backtest]**: a backtest or simulation.
- **[vendor]**: marketing.
- **[reasoned]**: our arithmetic, not a measurement.

**Coverage gaps.** NexusFi and Reddit could not be fetched. Some Elite Trader threads returned errors.

---

## The short version

1. **Nobody has published an ES scalping bot that survived live trading with a verifiable record.** The credible practitioners who tried at this frequency published failures or refused to trade it:
   - Carver: "It didn't work."
   - Kinlay: "DO NOT TRY TO TRADE THIS STRATEGY LIVE."
   - Databento's own ES example: positive gross, negative net.

   The open-source code on GitHub is plumbing and templates, with no track records.
2. **Orderflow's predictive power in ES is real but short-lived.** Book and trade imbalance predict the *next tick*. That effect is used up in **under one second** (Takahashi 2025, ES-specific, [measured]), and the fastest firms win it by speed rank (Baron et al., E-mini, [measured]). A 5-second bar sees it after the fact.
3. **The backtest traps, all documented:**
   - Same-bar delta "explaining" that same bar's move. That is description, not prediction.
   - Assuming limit fills at bar extremes. 22–47% of Kinlay's trades depended on those fills.
   - Bar data hiding quote flicker that trips tight stops (Ernie Chan).
   - The same bot run on two data feeds made +$10k on one and −$1.2k on the other (Bryant).
4. **Where the literature leaves room:**
   - horizons of tens of seconds to minutes, where orderflow shows up as absorption or persistence across bars, not raw imbalance;
   - context-conditioned setups (the open, the close, news, round-number stop clusters);
   - imbalance used as an **entry-timing filter** inside a slower thesis.
5. **Base rate [measured]:**
   - Brazil: 97% of mini-index day traders who persisted 300+ days lost money.
   - Taiwan: under 1% of day traders are predictably profitable.
   - ES, 2010: small traders lost $3.49 per contract to HFTs.

## Translating the stop to SPX singles [reasoned]

The survey sources price /ES futures. Your vehicle is SPX 0DTE options, and the arithmetic changes.

| | /ES futures, $25 stop | SPX 0DTE single, $25 stop |
|---|---|---|
| Stop in the instrument | 2 ticks (0.5 pt) | $0.25 of premium |
| Index room before the stop | 0.5 pt, about 1.5 of it spent crossing the spread | about 0.5 pt at delta 0.50, about 0.8 pt at delta 0.30, before the option spread |
| Entry friction | 1 tick = $12.50 | the option's bid-ask at entry. **Not yet measured.** A $0.10 spread is $10 of the $25. |
| $200 target in index points | 4 pts (16 ticks) | roughly 3–4 pts at delta 0.50, less as gamma adds up; more at delta 0.30 |
| Where the tight stop could misfire | stop-limit conversion on CME, stop slippage | a stop keyed to the option *mark or bid* can be tripped by quote flicker without the index moving |

**Where SPX is more forgiving:**
- You never sit in a futures queue, so the ES back-of-queue adverse-selection findings don't apply.
- Convexity lets a winner outrun its delta.
- Choosing a lower delta buys more index room for the same $25.

**Where it is not:**
- The target-to-stop ratio in index points is still about 5–8 to 1. With no edge, a random walk reaches the stop first in roughly **83–88%** of trials (stop ÷ (stop + target)).
- The signal has to beat that base rate by a clear margin, after the option spread and fees on every trade.

**On liberal re-entry.** Each re-entry is another draw from the same per-trade distribution. If each trade has positive expected value, re-entry multiplies it; if negative, it multiplies the loss. So the case for re-entry is the same as the case for each trade having positive expected value.

## What to measure on our own tape before building

Our tape is the Databento ES trades plus MBP-1 already collected. These three tests decide whether the $25 stop is "proven otherwise":

1. **Stop survival.** From each candidate entry, how often does /ES move 0.5–0.8 SPX-equivalent points against the entry before it reaches +3 to +4? Run it first with no signal to get the base rate, then with the signal.
2. **Forward signal only.** The correlation of 5-second delta, OFI and absorption features with the move over the *next* 5 seconds to 5 minutes, never the same bar.
3. **Spread at entry.** SPX 0DTE bid-ask at the strikes the code would pick, sampled through the session with the Schwab chain reader. It prices the entry friction the table above leaves blank.

---

## Sources

### Practitioners

| Source | What they did | Result | Lesson |
|---|---|---|---|
| **Rob Carver** (ex-AHL), ["Can I build a scalping bot?" 2025](https://qoppac.blogspot.com/2025/05/can-i-build-scalping-bot-blogpost-with.html) | MES mean-reversion bracket scalper; 5,000 bootstrap simulations | [backtest] Sharpe 28.8 with zero costs, 7.0 once stop slippage is added, −1.98 at his preferred setting. [live-self] **"It didn't work."** | Tight stops need fill precision retail lacks; you only beat costs when filled passively |
| **Jonathan Kinlay**, [ES scalping 2018](https://jonathankinlay.com/2018/09/implementation-of-a-scalping-strategy/), [HF scalping 2019](https://jonathankinlay.com/2019/10/high-frequency-scalping-strategies/) | 1-min ES, 8-tick target with 2-tick stop (regime-switched); 3-min ES at 50–60 trades/day | [backtest] $3.42 per contract, 76% win rate, profit factor 1.24. About $6 net per trade on the 3-min system; 34–47% of trades were fills at the bar's extreme | The real edge is about half a tick, and it depends on fills that backtests overstate |
| **Ernie Chan**, ["Beware of Low Frequency Data" 2015](http://epchan.blogspot.com/2015/04/beware-of-low-frequency-data.html) | Futures momentum system, 1-min bars vs 1-ms quote data | [backtest] Sharpe 1.0 on 1-min bars, far worse on quote data | Test stop logic on tick or quote data; bars hide quote flicker |
| **Celan Bryant**, [Automated Trading Strategies](https://automatedtradingstrategies.substack.com/p/scalping-strategies-501-strategy) | NinjaTrader NQ scalpers | [sim] Same bot over the same days: +$10k on one feed, −$1.2k on another. [live-self] $10k→$30k over Jan–Mar 2024 | The data feed and fill engine can decide the sign of the result |
| [Elite Trader: scalping for a point](https://www.elitetrader.com/et/threads/es-results-are-best-when-scalping-for-a-point.163567/) | Manual ES scalping | Anecdote: 1–2 ticks of stop slippage; years of losses on 1-point scalps | A 4-tick goal "couldn't afford even 1-tick slippage" |
| [Sierra Chart support thread](https://www.sierrachart.com/SupportBoard.php?ThreadID=90540) | CME stop handling | CME converts stops to stop-limits; in a fast move they can fail to fill | A hidden failure mode for tight stops |
| **Zarattini, Aziz & Barbon**, [Intraday Momentum for SPY 2024](https://ssrn.com/abstract=4824172) | About one trade a day with trailing stops | [backtest, costs included] 19.6% a year, Sharpe 1.33, 2007–2024 | The intraday S&P systems that survive trade rarely, with wide stops |

### Microstructure evidence

| Source | Finding | Robustness |
|---|---|---|
| Takahashi 2025, [arXiv 2508.06788](https://arxiv.org/abs/2508.06788), **ES** | Order-flow shocks dissipate within about 1 s; responses beyond one lag are negligible; first-lag reversal in >95% of windows | Direct ES evidence |
| Cont, Kukanov & Stoikov 2014, [arXiv 1011.6402](https://arxiv.org/abs/1011.6402) | Order-flow imbalance explains the *same* 10-s window's move with R² ≥ 50%; it is not a forecast | Robust. It is the source of the same-bar trap |
| Cont, Cucuringu & Zhang 2023, [arXiv 2112.13213](https://arxiv.org/abs/2112.13213) | Lagged imbalance helps forecast, but decays rapidly | Robust |
| Gould & Bonart 2016, [arXiv 1512.03492](https://arxiv.org/abs/1512.03492) | Queue imbalance predicts the next tick well in large-tick instruments | Robust; the horizon is sub-second |
| Kolm, Turiel & Westray 2023, [SSRN 3900141](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3900141) | Deep-learning imbalance models: the useful horizon is about 2 price changes | Robust |
| Stoikov 2018, [micro-price](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2970694) | Imbalance-adjusted mid is the better fair value | Use it for execution and marking |
| Cartea, Donnelly & Jaimungal 2018, [SSRN 2668277](https://www.ssrn.com/abstract=2668277); Lehalle & Mounjid 2017, [arXiv 1610.00261](https://arxiv.org/abs/1610.00261) | Imbalance improves execution by fractions of a tick; latency erodes the gain | Robust |
| [arXiv 2409.12721](https://arxiv.org/html/2409.12721v2), real CME data | 81.5% of simulated passive ES limit fills were adverse | Moderate |
| Moallemi & Yuan 2017, [queue value](https://moallemi.com/ciamac/papers/queue-value-2016.pdf) | Queue position is worth about one spread; the back of the queue is most toxic | Robust |
| Baron, Brogaard & Kirilenko, [HFT profits (CFTC ES data)](https://conference.nber.org/confer/2012/MMf12/Baron_Brogaard_Kirilenko.pdf); Baron et al. 2019 JFQA | Small traders lose $3.49 per contract to aggressive HFTs; latency rank explains profit; new entrants lose and exit | Robust, ES |
| Aquilina, Budish & O'Neill 2022 QJE, [NBER w29011](https://www.nber.org/papers/w29011) | Latency races last 5–10 µs; the top 6 firms win over 80% | Robust (UK equities) |
| Budish, Cramton & Shim 2015, [HFT arms race](https://ericbudish.org/publication/the-high-frequency-trading-arms-race-frequent-batch-auctions-as-a-market-design-response/) | ES–SPY arbitrage lives at millisecond horizons | Robust |
| Easley, López de Prado & O'Hara 2012, "The Volume Clock" | Volume bars give better statistics than time bars; they don't create alpha | Moderate |
| Osler 2005, [NY Fed SR150](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr150.pdf) | Stops cluster past round numbers; moves through those clusters cascade | Robust (FX) |

### Retail outcomes

| Source | Finding |
|---|---|
| Chague, De-Losso & Giovannetti, [SSRN 3423101](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101) | Brazilian mini-index day traders: 97% of those persisting 300+ days lost money; 1.1% earned more than the minimum wage |
| Barber, Lee, Liu & Odean, [SSRN 529063](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=529063) | Taiwan: under 1% of day traders predictably profitable; skill persists in a small top group |
| Kuo & Lin 2013, [SSRN 1944059](https://www.ssrn.com/abstract=1944059) | Taiwan futures day traders: costs were more than half of the average loss |
| Ferko, Mixon & Onur, [CFTC 2024](https://www.cftc.gov/sites/default/files/2024-11/Retail_Traders_Futures_V2_new_ada.pdf) | MES is the most-held retail contract; the median trader loses $100–200 (end-of-day positions only, so it can't see scalping) |

### Code and tools that touch ES

| Project | What it is | Use to us |
|---|---|---|
| [nkaz001/hftbacktest](https://github.com/nkaz001/hftbacktest) | Backtester modelling queue position and latency; its tutorial uses Databento CME order-by-order data | The honest fill simulator if we ever rest orders. For SPX singles, the /ES side is signal-only |
| [Databento: liquidity-taking strategy](https://databento.com/blog/liquidity-taking-strategy) | ES book-skew signal on MBP-1, our schema | Their conclusion: positive gross, negative net after costs and latency |
| [Databento: HFT signals with sklearn](https://databento.com/blog/hft-sklearn-python) | ES book skew and 10-level imbalance | R² about 0.01, a typical size for this kind of signal |
| [nautilus_trader](https://nautilustrader.io/docs/latest/integrations/databento/) | Event-driven engine with a Databento loader | Candidate backbone if we outgrow scripts; no ES results |
| [WaleeTheRobot/order-flow-bot](https://github.com/WaleeTheRobot/order-flow-bot) | NinjaTrader 8 volumetric and stacked-imbalance automation | Feature ideas only; no performance published |
| [PickMyTrade slippage data](https://blog.pickmytrade.io/real-slippage-data-1000-trades-futures-brokers-2026/) | [vendor] 0.7–1.2 ticks of slippage by broker, 3–5 ticks on news | Indicative only; no method given |
