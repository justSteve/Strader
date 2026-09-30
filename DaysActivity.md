# DaysActivity - 2026-09-30

## 12:17 - Session Handoff [Order Form: Phantom Loss, TOS Sync, iPad Pass]

**Summary**: Fixed the order form's phantom losses (Schwab's OCO cancel of the sibling leg, EXECUTION/CANCELED at 0.00, was read as a fill — 09-28's −$1,090 and −$930 were really −$10 stop-outs), made the form follow TOS (a moved leg is followed to its new order, a cancelled leg stays off, a re-priced entry is followed, 3 s reconcile), then worked Steve's iPad list: stop box is the distance under the entry (.2) with + − steppers, a close-at-SPX box (one live, the other NA), strike and contracts as stepper boxes, no qty cap, SEND disabled until the ticket is a valid order, no STOP anywhere (an unlock clears a STOP left on), opening strike is the highest affordable delta ≤ 0.80, after-fill card stop/target steppers, and the SENT caption tied to its stage; Mancini parsed 09-29 (60 levels) and 09-30 (49 levels).

**Open Work**:
- Order Form Phantom Loss (st-5n3s) open — Steve's iPad review group; 09-30 commits 080914b..(caption fix) are held LOCAL on his word ("let's not push until we step thru this group") — push when he closes the group Live service ran 33c71c7 at 11:24; the later commits need `bash deploy/install.sh --execd` while flat
- STOP file on since 08:59 CT 09-30 (/var/lib/execd/STOP, entries refused); the new build clears it on the next unlock
- 09-28 journal still carries the two phantom closed lines (−1,090, −930); the day's P&L on that journal stays wrong — left unedited, Steve's call
- Unmeasured live: Schwab's handling of the OCO sibling when one leg is replaced in TOS, and a triggered entry's children when the entry is re-priced in TOS
- Open ask to Steve: keep the derived SPX backup close for the dollar stop (currently kept)

**Files Changed**:
execd/broker.py
execd/schwab.py
execd/service.py
execd/watch.py
execd/page.py
execd/panel.py
execd/orderpage.py
execd/orderform.py
execd/intent.py
execd/bounds.py
execd/bounds.example.yaml
tests/execd/test_schwab.py
tests/execd/test_orderform.py
tests/execd/test_panel.py
tests/execd/test_page.py
tests/execd/test_api.py
tests/execd/test_bounds.py
tests/execd/test_bracket.py
tests/execd/test_service.py
tests/execd/test_triggered.py
tests/execd/test_entry_price.py
tests/execd/test_tos_beside.py
runbook/mancini/commentary/2026-09-28.jsonl
runbook/mancini/commentary/2026-09-29.jsonl
runbook/mancini/commentary/2026-09-30.jsonl
CurrentStatus.md

---
