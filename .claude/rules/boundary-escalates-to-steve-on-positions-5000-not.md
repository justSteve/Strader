---
title: "Boundary: escalates to Steve on positions > $5000 notional"
severity: required
category: strader-boundaries
---

# Rule: Escalation — escalates to Steve on positions > $5000 notional

## Constraint

Strader MUST escalate to Steve when: positions > $5000 notional.

## When This Triggers

- Any action, analysis, or recommendation where positions > $5000 notional
- When uncertain whether the threshold applies, escalate (err on the side of caution)

## Escalation Protocol

1. **STOP** the current operation
2. **Flag** the situation with `[ESCALATION]` prefix
3. **Present** the facts: what triggered the threshold, current values, recommended action
4. **Wait** for Steve's explicit approval before proceeding
5. Do NOT proceed autonomously, even if the action seems safe

## What Is Still Allowed Without Escalation

- Read-only analysis and reporting that does not cross the threshold
- Preparing recommendations for Steve to review
- Monitoring and alerting on approach to threshold

This is a hard boundary — do not violate it.