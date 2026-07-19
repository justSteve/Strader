---
type: convention
title: "WSL Distro Is Zgent"
description: "This session runs in WSL distro \"Zgent\", not \"Ubuntu\" — use \\\\wsl$\\Zgent\\ for Windows paths"
timestamp: 2026-05-17T06:42:40-05:00
metadata:
  originSessionId: 1c9f6a10-b0fc-49cc-b683-82172206205a
  graduated_from: feedback_wsl_distro.md
  source_type: feedback
---

Always use `\\wsl$\Zgent\` when giving Windows-side paths to WSL files. The distro name is "Zgent", not "Ubuntu" (there is a separate Ubuntu distro on this machine but that's not where we run).

**Why:** Steve corrected this multiple times — using the wrong distro name in paths means the paths don't work.

**How to apply:** Any time you reference a `\\wsl$\` path, use `Zgent` as the distro name. Can verify with `$WSL_DISTRO_NAME` if unsure.
