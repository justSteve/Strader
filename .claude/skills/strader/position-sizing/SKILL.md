---
allowedTools:
  - mcp__mssql__sql_query
  - Read
---

# Position Sizing

Calculate appropriate position size given account balance, risk tolerance (max 2% per trade), and current exposure.

## Content

---
name: position-sizing
description: Calculate appropriate position size given account balance, risk tolerance (max 2% per trade), and current exposure.
allowed-tools: mcp__mssql__sql_query, Read
---

# Position Sizing

Calculate appropriate position size given account balance, risk tolerance (max 2% per trade), and current exposure.

## Reference Files

Read these before executing. They contain domain knowledge needed for this skill.

- `references/trading-rules.md` — Steve's personal trading rules and risk parameters

## Inputs

- **account_balance**: (describe source and format)
- **risk_percentage**: (describe source and format)
- **current_exposure**: (describe source and format)
- **option_price**: (describe source and format)

## Workflow

1. Read reference files in `references/` for domain context
2. Gather required data
   - Read: account_balance, risk_percentage, current_exposure, option_price
3. Process and analyze
   - Apply domain logic relevant to: Calculate appropriate position size given account balance, r
4. Format output
   - Produce: recommended_contracts, max_loss_scenario, exposure_after_trade

## Output Format

### recommended_contracts

(Define structure and format here)

### max_loss_scenario

(Define structure and format here)

### exposure_after_trade

(Define structure and format here)

## Error Handling

- If required data is unavailable, report what is missing and skip analysis.
- If calculations produce unexpected results, flag with [WARNING] and show inputs.
- Never silently fail — always report status.

## Output Style

- Minimize words. Use tables, not paragraphs. Numbers speak. No preamble.
- Prefer structured tables over narrative text.
- Flag anomalies with [ALERT] prefix.
- Never speculate without supporting data.
- Prefer structured tables over narrative text.


## Workflows

### default

**Steps:**
1. Read reference files in references/ for domain context
2. Gather required data
3. Read: account_balance, risk_percentage, current_exposure, option_price
4. Process and analyze: Calculate appropriate position size given account balance, r
5. Format output
6. Produce: recommended_contracts, max_loss_scenario, exposure_after_trade

**Expected Outcome:**
recommended_contracts, max_loss_scenario, exposure_after_trade
