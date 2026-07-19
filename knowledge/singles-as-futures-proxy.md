---
type: playbook
title: "Singles as Futures Proxy"
description: "Steve trades 0DTE long singles as a proxy for futures strategies — \"an option single is a futures contract on its last day\""
timestamp: 2026-06-24T17:05:20-05:00
metadata:
  originSessionId: 68c135db-a2bc-49ae-8b90-5ac270f3fea4
  graduated_from: feedback_singles_as_futures_proxy.md
  source_type: feedback
---

Steve's mental model for short-term 0DTE long singles: **trade them as a proxy for futures strategies.** His words: "if it works for futures, unless it is in direct contravention to the relevant Greeks — an option single is a futures contract on its last day." Deep-ITM 0DTE singles track the underlying ~1:1 (delta→1); even near-ATM, over a short hold the single mirrors /ES price action. So order-flow / supply-demand / scalping playbooks (e.g. [[carmine-rosato]]) port directly to singles, modulo theta/gamma.

**Why:** Sets the design approach for the singles strat (st-nd5) — start from a working futures/scalp playbook and adjust ONLY where the Greeks force it (theta cliff, gamma convexity, bid/ask spread friction), rather than inventing options-native rules from scratch.

**How to apply:** When scoping singles entries/management, lean on futures-style chart elements (order flow, S/R zones, VWAP, volume nodes) and flag only the Greek-driven deviations. Strike leans ITM for tighter delta/spread when he wants a clean futures proxy. Extends [[buying-movement-short-hold]].
