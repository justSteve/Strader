---
type: convention
title: "Fork Doctrine"
description: "Enterprise forks repos to own/extend them, not just pin versions. Use local clones and editable installs, not pip from PyPI."
timestamp: 2026-05-06T09:42:27-05:00
metadata:
  graduated_from: feedback_fork_doctrine.md
---

When a dependency is forked under justSteve/, treat it as an owned, modifiable codebase — not an opaque pip package. Use local clones (e.g. `lib/<repo>`) with `sys.path` or `pip install -e`, never `pip install <package>` from PyPI.

**Why:** Fork Doctrine (Steve directive, 2026-04-19). Forks are deliberate appropriation. The enterprise intends to understand, extend, and modify upstream code. Agentic AI collapses the cost of well-done local changes. Extension points the upstream didn't design become viable surfaces.

**How to apply:** When a forked repo exists under justSteve/, clone it locally rather than pip-installing. Reference via editable install or sys.path. When upstream doesn't expose an extension point we need, patch the fork directly and carry the change.
