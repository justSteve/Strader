---
allowedTools:
  - Read
---

# Risk Limit Enforcement

Continuously monitor portfolio against risk limits: max daily loss, max position count, max single-position size, max po

## Content

---
name: risk-limit-enforcement
description: Continuously monitor portfolio against risk limits: max daily loss, max position count, max single-position size, max po
allowed-tools: Read
---

# Risk Limit Enforcement

Continuously monitor portfolio against risk limits: max daily loss, max position count, max single-position size, max portfolio delta. Alert immediately on breach.

## Reference Files

Read these before executing. They contain domain knowledge needed for this skill.

- `references/domain-concepts.md` — Domain concepts relevant to this skill
- `references/trading-rules.md` — Steve's personal trading rules and risk parameters

## Workflow

1. Read reference files in `references/` for domain context
2. Gather required data
3. Process and analyze
   - Apply domain logic relevant to: Continuously monitor portfolio against risk limits: max dail
4. Format output
   - Produce: alert_if_breached
5. Deliver to: alert_pane

## Output Format

### alert_if_breached

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
3. Process and analyze: Continuously monitor portfolio against risk limits: max dail
4. Format output
5. Produce: alert_if_breached
6. Deliver to: alert_pane

**Expected Outcome:**
alert_if_breached
