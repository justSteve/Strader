# Rule: `find` and `grep` in the Bash Tool Are Claude Code Shims — Handle Accordingly

In every Bash tool call, `find`, `grep` and (when `rg` is absent) `rg` are
**shell functions** that re-exec the Claude Code binary as its embedded
`bfs` / `ugrep` (`exec -a ugrep "$CLAUDE_CODE_EXECPATH" …`). Not GNU find,
not GNU grep. In `ps` they appear as the binary's version string
(`2.1.233`), which is how the 2026-08-15 post-mortem found them. Verify any
time: `type grep` → "grep is a function".

Two of those shims have failure modes GNU's tools do not, and on 2026-08-15
they took the whole WSL distro down twice in four minutes [co-8ygyt].

## 1. Never `-o` with a bounded-repetition context under the shimmed grep

`grep -oE '.{0,120}NEEDLE.{0,120}'`, `grep -oE '.{0,150}timeout[^;]{0,60}1000.{0,60}'`,
`grep -rnoE '"[^"]{0,80}(healthy|…)[^"]{0,60}"'` — the embedded ugrep allocates
at **~150 MB/s** on such patterns and does not stop. Measured 2026-08-15 under a
4 GB cap: 3.4 G / 3.6 G / 3.35 G in ~20 s, one segfault at the cap. Uncapped, one
reached **18 GB** (11 G resident + 7 G swap) and a second 6.8 GB; together they
exhausted 20 GB RAM + 8 GB swap. GNU grep finishes the same jobs instantly.

**Do:** `command grep -oE …` (bypasses the function) whenever the pattern
carries `.{0,N}` / `[^x]{0,N}` context or `-o` at all on unfamiliar input.
Or drop `-o` and use `-n` with a plain fixed string, then read the line.

## 2. Never `find /` — and never leave a timed-out find/grep running

The shimmed `find` is `bfs`, and `find /` on this box walks **every 9p mount**
— C:, F:, G:, H:, J:, K:, Z: (a 4 TB archive) — over the WSL file bridge.
Root any `find` at or below `/root/projects`, `/root/.claude`, `/var/moo`,
`/etc`, or a named `/mnt/c/...` path, and add `-maxdepth` or `-xdev` when the
tree is not yours.

When a Bash tool call reports *"did not complete within its 120s timeout and
was moved to the background"*, the process is **still running and still
allocating**. That message is a work order: kill it now (`TaskStop`, or
`kill <pid>` from `pgrep -x 2.1.233`), then rewrite the command. On
2026-08-15 three such commands were left in the background by two parallel
sweeps and nobody was watching them grow.

## 3. Shimmed `grep -r` is not a completeness sweep

The shim adds `--ignore-files --hidden -I --exclude-dir=.git …`: it **skips
gitignored files and binaries**. A `grep -r` that reports "no occurrences" has
not looked inside `.gitignore`d paths. For any "is anything left?" question
(`completeness-sweeps.md`), use `command grep -r` so the sweep sees what git
does not track.

## Why the box died rather than one process

The kernel did the right thing at 08:53:09 — it killed the 18 GB process.
systemd then applied `OOMPolicy=stop` to `init.scope`, and on WSL that scope
holds every terminal SessionLeader, every claude, dolt, tmux. Everything died,
the distro restarted, systemd re-read the cgroup's OOM event and did it
**again**. The drop-in `/etc/systemd/system/init.scope.d/oom.conf`
(`OOMPolicy=continue`) now confines a kernel OOM kill to the culprit
[co-8ygyt]. Six interactive sessions were ~1.5 GB between them; the session
count was never the problem.
