# Hybrid Control Survey: Human Judgement, Code Speed and Endurance

*st-t4nm · 2026-09-26 · Broadens the ES Algo Survey (st-cg63) to hybrid control: the human supplies judgement (setups, context, when to be active, veto) and code supplies speed and endurance (watching 5-second tape all session, firing inside armed parameters, managing break-even and ATR-trail exits, re-entries).*

**Labels:**
- **[measured]**: data or an experiment
- **[live-self]**: the author trading their own money, unaudited
- **[backtest]**
- **[vendor]**
- **[opinion]**
- **(memory)**: not re-checked this session

**Coverage gaps:** NexusFi, Forex Factory and Reddit could not be fetched.

---

## The short version

1. **The angle has support. Nobody has published results for your exact design.**
   - Your design: you arm the setup, code fires on an orderflow confirmation and manages the exit, trading /ES into SPX long premium.
   - The pieces all exist separately:
     - orderflow-conditioned triggers (Jigsaw's Volume Stop, the open-source OrderFlowBot)
     - arm/disarm with a kill switch (an open-source SPX 0DTE framework on IBKR)
     - managed exits (Sierra Chart, NinjaTrader)
   - No practitioner found publishes numbers from the combination.
2. **The strongest evidence is on exits.**
   - On Nasdaq Copenhagen, human day traders took 35% of their gains but only 20% of their losses, and it cost them. Algorithmic traders took 32% of each (Liaudinskas 2019, [measured]).
   - In a lab experiment, **automatic** stops and take-profits removed that bias. A reminder that the limit had been hit did not (Fischbacher et al. 2017, *RFS*, [measured]).
   - Your break-even and ATR-trail rules executed by code are on the right side of both results.
3. **Where hybrids win.** Each side does what it is actually better at:
   - The human reads context and regime changes. Discretionary funds beat quant funds in recessions (Abis 2020). Human overrides helped only for new or changing products (Kesavan & Kushwaha 2020).
   - Code does vigilance and consistency. Human detection falls 10–15% within 30 minutes of monitoring (Warm et al.). The same person prices identical cases differently, a median 55% apart in one audit (*Noise*).
4. **Where hybrids lose.**
   - Free, in-the-moment overrides:

     | Forecasting method | Error (lower is better) |
     |---|---|
     | Human could adjust the model's forecast by a small, capped amount | 17.90 |
     | Model alone | 18.20 |
     | Human could adjust the model's forecast freely | 20.25 |

     (Dietvorst 2018.) A 12-month field experiment found overrides cut profit by 5.77% (Kesavan).
   - On average across 106 experiments, human-plus-AI *decisions* did worse than the better of the two alone. The combination gained only when the human was the stronger party (Vaccaro 2024, *Nature Human Behaviour*).
   - A hybrid is not better by default. It is better when the human's part is a real edge.
5. **Where practitioners draw the line.**
   - **Rob Carver** (ex-AHL): the human decides *what* and *when*; code owns size, stop and exit, with no overrides. Judgement belongs only in a decision where you have a statistically significant record.
   - **Bill Eckhardt** ran a mechanical account next to a discretionary one. The mechanical account won "year in, year out"; his sizing drifted with "optimism, pessimism and recent mistakes."
   - **Kevin Davey**: "The urge to overrule the algorithm is sometimes huge." Any filter must be pre-tested and rules-based.
   - **Linda Raschke**: "a human can identify these context changes much faster than a model can."

## What the human keeps and what the code owns

This is the consensus across the sources. The trading decisions stay yours; this is the split the published designs use.

| Human | Code |
|---|---|
| Which setups are live today; the regime read (trend vs range, catalyst day) | Watching the tape every 5 seconds, all session |
| Arm and disarm, **between** signals | Firing inside the armed parameters without hesitation |
| Veto *before* entry | Initial stop, break-even move, ATR trail, scale-outs |
| Sizing: yours. Eckhardt and Carver would hand it to code first. | Re-entry and duplicate guards, budget checks |
| Kill switch | Alerts on exceptions, including its own health (dead feed, stale quote, rejected order) |

**On session loss caps.** The evidence leans toward a daily cap enforced in code: floor traders with morning losses were 16% more likely to take above-average afternoon risk (Coval & Shumway 2005), and Raschke flattens at her equity target. You removed execd's loss ceiling on 09-25 (co-8mb1z). That stands; this is reported, not recommended.

## Design rules the evidence supports

1. **Overrides only at set points.** Arm, disarm and veto happen before entry. Once a position is open, the human may tighten or flatten, not loosen (Fischbacher; Davey).
2. **Bound any live adjustment.** A capped nudge keeps you engaged and costs almost nothing. Unbounded adjustment costs accuracy (Dietvorst 2018).
3. **Log every override against the system's shadow result.** Record what the code would have done, and keep the override right only while its running record beats the system. This is the only measurement of *your* edge. It is also the defence against losing faith after a visible loss: people abandon a model faster than a human after seeing the same error (Dietvorst 2015).
4. **Grade the context before seeing the signal.** Human and model inputs combine best when they are independent and mechanically blended. An equal model-and-manager blend beat either one alone in all 5 settings (Blattberg & Hoch). A model that took analysts' forecasts as an input beat them every year (Cao et al.).
5. **Active decisions and specific alerts, not six hours of watching.** Full automation erodes situation awareness and slows recovery when it fails (Endsley & Kiris). The higher the automation, the harder the fall when it breaks (Onnasch 2014).
6. **Code owns the trigger and the order, not just an alert.** Alert-then-click cost "several ticks or even a few points" and bred laziness (Elite Trader, [live-self]).
7. **Hard kill switch and limits in code** (Knight Capital, $440M in 45 minutes, (memory)).
8. **Re-measure the human edge.** Human-plus-engine chess teams beat engines alone around 2005–08. By about 2013 engines had caught up, and by 2017 engines won outright.

**Mechanics failures reported:**
- NinjaTrader users report the break-even and trail triggers conflicting when both are set at the same profit level.
- Sierra Chart holds attached orders on the client until the parent fills, so they die if the PC does.
- Sierra's documentation warns an exit can fail to cancel its sibling orders, reversing the position.
- Several sources caution against moving to break-even too early (before about 1R). That is opinion only; I found no measured study.

---

## Sources

### Practitioners

| Source | Human | Code | Evidence |
|---|---|---|---|
| **Rob Carver**, [semi-automatic trader](https://qoppac.blogspot.com/2016/01/computers-vs-humans-considering-median.html), [*Leveraged Trading*](https://www.systematicmoney.org/leveraged-trading-information), [TTU 2026-09-12](https://www.toptradersunplugged.com/podcast/what-happens-when-ai-starts-trading-the-markets-ft-rob-carver) | what and when | size (volatility-targeted), stop (volatility multiple), exit | [opinion], highly credible. Expects Sharpe 0.2–0.5. Overriding the systematic parts is "just plain stupid" |
| **Bill Eckhardt**, [Hedge Fund Journal](https://thehedgefundjournal.com/eckhardt-trading-company/) | one account | one account | [live-self] The mechanical account beat the discretionary one every year; sizing was the leak |
| **Linda Raschke**, [Better System Trader ep. 49](https://bettersystemtrader.com/049-linda-raschke/) | context changes, trend vs range, daily flatten | directional bias; exits tested per setup type | [live-self] About $3.5M on automation: "it's not trading. It's a different type of business" |
| **Kevin Davey**, [Crudele podcast 293](https://futures.anthonycrudele.com/podcast/293/), [Desire to Trade](https://www.desiretotrade.com/197-confessions-of-a-champion-algo-trader-kevin-davey/) | none live | everything | [live-self] Lost 60% of an early account, partly by flipping a system's signal on a whim |
| **Brett Steenbarger**, [TraderFeed](http://traderfeed.blogspot.com/2016/07/a-systematic-approach-to-discretionary.html) | intraday navigation | six-model "committee" as signposts | [opinion]/[backtest] |
| **Peter Davies** (Jigsaw founder), [interview](https://www.cannontrading.com/traders-interview/peter-davies) | the entire read | order mechanics only | [live-self] "too nuanced" to hand to a computer |
| **Dave Mabe** (ex-Trade-Ideas CTO), [blog](https://davemabe.com/how-discretionary-traders-can-add-automated-strategies), [Chat With Traders 318](https://chatwithtraders.com/episode/318-dave-mabe) | none | rules | [live-self] His rules beat his discretion. Build for automation rather than cloning discretion. "Visual backtesting is not real backtesting" |
| **John Sandvand**, [Theta Profits](https://www.thetaprofits.com/my-most-profitable-options-trading-strategy-0dte-breakeven-iron-condor/) | entries, stop tightening | broker OCO stops | [live-self] 9,100 0DTE trades, 49 of 57 months profitable. Short premium, but real money and well documented |
| **Elite Trader**: [manual vs automated](https://www.elitetrader.com/et/threads/manual-trading-and-profitable.372063/page-4), [semi-automated how-to](https://www.elitetrader.com/et/threads/semi-automated-trading-how-to.170922/) | varies | varies | [live-self] One trader went from 99% automated to keeping two systems. Alert-only setups cost ticks |
| SMB Capital, [blog](https://www.smbtraining.com/blog/we-want-to-back-your-automated-trading-strategies); Axia Futures, [blog](https://axiafutures.com/blog/order-flow-with-alex-haywood-and-jigsaw-trading/) | | | [vendor]/[opinion] SMB backs "bionic" hybrid traders; Axia publishes nothing on semi-automation |

### Tools and code

| Tool | Pattern | Notes |
|---|---|---|
| [tony3641 SPX 0DTE framework (IBKR)](https://github.com/tony3641/spx_0dte_option_trading_framework_ib) | **arm/disarm per strategy**, global kill switch, auto-execute flag, one-shot re-entry guards, idempotent take-profit loops | The closest control architecture to yours. Built for credit spreads; no results |
| [OrderFlowBot](https://github.com/WaleeTheRobot/order-flow-bot) (NinjaTrader) | the human toggles live footprint strategies; the bot fires and hands the position to a chosen exit manager | **Human arms, code fires on orderflow.** Hobbyist, no results |
| [Jigsaw exit automation](https://www.jigsawtrading.com/blog/trade-exit-automation-pt-2-advanced-features/) | multi-leg exits, trailing on best bid/offer; **Volume Stop** fires only when resting size thins | An orderflow-conditioned trigger. Volume Stops run on the client |
| [Sierra Chart attached orders](https://www.sierrachart.com/index.php?page=doc%2FAttachedOrders.html), [Trade Management by Study](https://www.sierrachart.com/SupportBoard.php?ThreadID=73944) | five break-even modes; a stop that follows any study line (for example an ATR band) | Client-held until the parent fills; exits can fail to cancel siblings |
| [NinjaTrader ATM](https://ninjatrader.com/support/helpguides/nt8/auto_breakeven.htm) | auto break-even and auto trail after a manual entry | Break-even and trail at the same trigger conflict. Often the only automation prop firms allow |
| [Bookmap API](https://bookmap.com/knowledgebase/docs/API) | intercepts orders the user sends; a risk module can override the human | Code vetoing the human |
| [Option Alpha](https://docs.optionalpha.com/tools/bots/automations) | "Buttons": the human fires a scanner, the bot builds and manages the order | 1-minute granularity at best; heavy on backtests |
| [Trade Automation Toolbox](https://tradeautomationtoolbox.com/) | SPX 0DTE stops, break-even at a profit %, stop re-placement | Short premium; affiliate-promoted |
| [TT ADL](https://tradingtechnologies.com/trading/algo-trading/adl/) | point-and-click algos for professional desks | The institutional version |

### Evidence

| Source | Finding |
|---|---|
| Liaudinskas 2019, [BSE WP 1133](https://bse.eu/sites/default/files/working_paper_pdfs/1133.pdf) | Humans took 35% of gains vs 20% of losses; algorithms 32% vs 32%. The disposition effect hurts the humans |
| Fischbacher, Hoffmann & Schudy 2017, [*RFS*](https://www.twi-kreuzlingen.ch/wp-content/uploads/2017/12/twi-rps-089-fischbacher-hoffmann-schudy.pdf) | Automatic stops and take-profits causally reduce the disposition effect; reminders don't |
| Richards et al. 2017, [SSRN 2612898](https://ssrn.com/abstract=2612898) | UK brokerage data: stop-losses protect against the disposition effect |
| Coval & Shumway 2005, *JF* | CBOT floor traders with morning losses were 16% more likely to take above-average afternoon risk |
| Locke & Mann 2005, *JFE* | More disciplined futures traders are more successful |
| Harvey et al. 2017, [Man vs Machine](https://people.duke.edu/~charvey/Research/Published_Papers/P130_Man_vs_machine.pdf) | Systematic and discretionary hedge funds are similar after risk adjustment (the authors are Man Group) |
| Abis 2020, [paper](https://www.anderson.ucla.edu/documents/areas/fac/finance/Simona_Abis_Job_Market_Paper.pdf) | Quant funds win on breadth; discretionary funds adapt and beat them in recessions |
| Cao et al. 2024, *JFE*, [NBER w28800](https://www.nber.org/system/files/working_papers/w28800/w28800.pdf) | AI beats 54.5% of analyst forecasts; AI that takes the human forecast as an input beats 57.3%, every year |
| Grove et al. 2000, [meta-analysis](http://zaldlab.psy.vanderbilt.edu/resources/wmg00pa.pdf) | Over 136 studies, mechanical prediction is about 10% more accurate; clinical judgement is clearly better in only 6–16% |
| Dietvorst et al. [2015](https://marketing.wharton.upenn.edu/wp-content/uploads/2016/10/Dietvorst-Simmons-Massey-2014.pdf), [2018](https://faculty.wharton.upenn.edu/wp-content/uploads/2016/08/Dietvorst-Simmons-Massey-2018.pdf) | People abandon a model after seeing it err. A capped override brings them back at no cost; a free override costs accuracy |
| Blattberg & Hoch 1990, *Mgmt Sci* | An equal model-and-manager blend beat either one alone in all 5 settings (+16% R²) |
| Kesavan & Kushwaha 2020, [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3619085) | Field experiment: overrides cut profit 5.77%, and helped only for growth-stage products |
| Hoffman, Kahn & Li 2018, *QJE* | Managers who hired against the test recommendation got worse hires |
| Vaccaro et al. 2024, [*Nat Hum Behav*](https://arxiv.org/abs/2405.06087) | Across 106 experiments, human-plus-AI decisions are on average worse than the best of the two alone; they gain when the human is stronger |
| Regan, [freestyle chess](https://cse.buffalo.edu/~regan/chess/fidelity/FreestyleStudy.html); Cowen, [MR 2024](https://marginalrevolution.com/marginalrevolution/2024/02/centaur-chess-is-now-run-by-computers.html) | The centaur edge was real, then faded as engines caught up |
| Bainbridge 1983; Endsley & Kiris 1995; Onnasch et al. 2014; Parasuraman & Manzey 2010; Skitka et al. 1999 | Ironies of automation; lost situation awareness; the "lumberjack effect"; complacency; automation bias, reduced by accountability |
| Warm, Parasuraman & Matthews 2008, *Human Factors* | Detection falls 10–15% within 30 minutes of monitoring |
| Lo, Repin & Steenbarger 2005, *AER* | Day traders who reacted more emotionally to gains and losses had worse P&L |
| Kahneman, Sibony & Sunstein 2021, *Noise* | Identical cases were priced a median 55% apart |
| SEBI 2024, [press release](https://www.sebi.gov.in/media-and-notifications/press-releases/sep-2024/updated-sebi-study-reveals-93-of-individual-traders-incurred-losses-in-equity-fando-between-fy22-and-fy24-aggregate-losses-exceed-1-8-lakh-crores-over-three-years_86906.html) | 93% of individual Indian F&O traders lost money; 96–97% of prop and foreign-investor profits came from algorithms |

**Gap:** no published broker-data study compares bracket, OCO or trailing-stop use with P&L. Your own override and shadow log would be the first dataset.
