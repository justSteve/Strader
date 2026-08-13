#!/usr/bin/env bash
# precommit_size_guard.sh — refuse oversized blobs before they reach GitHub. [st-z3y5]
#
# Steve, 2026-08-13: "I don't want to use GH's diskspace unnecessarily so we
# don't want to store the DB exports there." This makes that a rule the repo
# enforces instead of a question he has to ask an agent each time.
#
# Checks only what is STAGED, by real blob size, and blocks the commit if any
# staged file exceeds the limit. Deletions and unstaged files are ignored.
#
#   MAX_COMMIT_FILE_KB=1024   override the 1 MB limit for one commit
#   ALLOW_BIG_COMMIT=1        bypass entirely (deliberate, visible in the shell)
#
# Installed at .git/hooks/pre-commit, which is NOT version-controlled — that is
# why the logic lives here, tracked and reviewable, and the hook is a one-line
# caller. Re-install with:  bash tools/precommit_size_guard.sh --install
set -uo pipefail

LIMIT_KB="${MAX_COMMIT_FILE_KB:-1024}"

if [[ "${1:-}" == "--install" ]]; then
    HOOK="$(git rev-parse --git-dir)/hooks/pre-commit"
    if [[ -f "$HOOK" ]] && grep -q "precommit_size_guard.sh" "$HOOK"; then
        echo "already installed: $HOOK"
        exit 0
    fi
    # Compose rather than clobber: beads manages its own marked section in this
    # file, so append if something is already there.
    if [[ -f "$HOOK" ]]; then
        printf '\n# --- size guard (tools/precommit_size_guard.sh) ---\nbash "%s/tools/precommit_size_guard.sh" || exit 1\n' \
            "$(git rev-parse --show-toplevel)" >> "$HOOK"
    else
        printf '#!/usr/bin/env bash\n# --- size guard (tools/precommit_size_guard.sh) ---\nbash "%s/tools/precommit_size_guard.sh" || exit 1\n' \
            "$(git rev-parse --show-toplevel)" > "$HOOK"
    fi
    chmod +x "$HOOK"
    echo "installed: $HOOK"
    exit 0
fi

if [[ -n "${ALLOW_BIG_COMMIT:-}" ]]; then
    echo "size guard: bypassed via ALLOW_BIG_COMMIT" >&2
    exit 0
fi

# Ask git for the STAGED blob size by path (`:path` is the index revision).
# Deliberately not parsing --raw: an off-by-one in those fields silently skipped
# every newly-added file, which is the exact case this guard exists to catch.
# Caught by the install-time test on 2026-08-13; do not "simplify" this back.
FAILED=0
while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    SIZE=$(git cat-file -s ":$path" 2>/dev/null || echo 0)
    KB=$(( SIZE / 1024 ))
    if (( KB > LIMIT_KB )); then
        if (( FAILED == 0 )); then
            echo "" >&2
            echo "COMMIT BLOCKED — staged file(s) over ${LIMIT_KB}KB:" >&2
            echo "" >&2
        fi
        printf '  %8sKB  %s\n' "$KB" "$path" >&2
        FAILED=1
    fi
done < <(git diff --cached --name-only --diff-filter=ACMR)

if (( FAILED )); then
    cat >&2 <<'EOF'

This repo pushes to GitHub; large blobs stay in history forever even if the
file is deleted later. Before overriding, check whether the file is:

  - a database export  -> do not commit it; the DB is covered by the WSL image
                          backup, and .beads/ already ignores the live exports
  - captured market data -> data/ is gitignored for exactly this reason
  - a build artifact   -> gitignore it instead

If it genuinely belongs in history:
    ALLOW_BIG_COMMIT=1 git commit ...      (bypass once)
    MAX_COMMIT_FILE_KB=4096 git commit ... (raise the limit once)
EOF
    exit 1
fi
exit 0
