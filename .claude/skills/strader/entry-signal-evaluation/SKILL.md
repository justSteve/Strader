---
allowedTools:
  - Read
---

# Entry Signal Evaluation

Given a potential trade setup (strike, expiration, direction), evaluate whether it meets entry criteria based on IV rank

## Content

---
name: entry-signal-evaluation
description: Given a potential trade setup (strike, expiration, direction), evaluate whether it meets entry criteria based on IV rank
allowed-tools: Read
---

# Entry Signal Evaluation

Given a potential trade setup (strike, expiration, direction), evaluate whether it meets entry criteria based on IV rank, expected move, time of day, and existing exposure.

## Reference Files

Read these before executing. They contain domain knowledge needed for this skill.

- `references/domain-concepts.md` — Domain concepts relevant to this skill

## Inputs

- **proposed_trade**: (describe source and format)

## Workflow

1. Read reference files in `references/` for domain context
2. Gather required data
   - Read: proposed_trade
3. Process and analyze
   - Apply domain logic relevant to: Given a potential trade setup (strike, expiration, direction
4. Format output
   - Produce: go_no_go_recommendation, supporting_rationale

## Output Format

### go_no_go_recommendation

(Define structure and format here)

### supporting_rationale

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
3. Read: proposed_trade
4. Process and analyze: Given a potential trade setup (strike, expiration, direction
5. Format output
6. Produce: go_no_go_recommendation, supporting_rationale

**Expected Outcome:**
go_no_go_recommendation, supporting_rationale
