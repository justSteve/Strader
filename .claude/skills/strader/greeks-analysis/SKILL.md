---
allowedTools:
  - Read
---

# Greeks Analysis

Analyze current portfolio Greeks. Flag positions where delta exceeds threshold or gamma risk is elevated.

## Content

---
name: greeks-analysis
description: Analyze current portfolio Greeks. Flag positions where delta exceeds threshold or gamma risk is elevated.
allowed-tools: Read
---

# Greeks Analysis

Analyze current portfolio Greeks. Flag positions where delta exceeds threshold or gamma risk is elevated.

## Reference Files

Read these before executing. They contain domain knowledge needed for this skill.

- `references/domain-concepts.md` — Domain concepts relevant to this skill
- `references/trading-rules.md` — Steve's personal trading rules and risk parameters
- `references/greeks-reference.md` — Greeks calculation formulas and interpretation guide

## Inputs

- **positions_list**: (describe source and format)

## Workflow

1. Read reference files in `references/` for domain context
2. Gather required data
   - Read: positions_list
3. Process and analyze
   - Apply domain logic relevant to: Analyze current portfolio Greeks. Flag positions where delta
4. Format output
   - Produce: portfolio_greeks_summary, risk_flags

## Output Format

### portfolio_greeks_summary

(Define structure and format here)

### risk_flags

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
3. Read: positions_list
4. Process and analyze: Analyze current portfolio Greeks. Flag positions where delta
5. Format output
6. Produce: portfolio_greeks_summary, risk_flags

**Expected Outcome:**
portfolio_greeks_summary, risk_flags
