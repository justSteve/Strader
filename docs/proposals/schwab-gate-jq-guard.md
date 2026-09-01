# Proposed hook change: schwab-gate must block, not allow, when jq is missing

**Status: prepared, not landed.** Hooks are Steve's to land
(`.claude/rules/scope-and-permissions.md`). One word applies it.

**Finding 14 of the 2026-08-30 independent audit (case st-5qjq, `05-the-wall.md`
§3), verified in the hook source 2026-09-01:** both `jq` invocations in
`.claude/hooks/scripts/schwab-gate.sh` (lines 61 and 64) send stderr to
`/dev/null`. If `jq` is ever not on the PATH — a slim base image, a PATH broken
by an env change, a distro rebuild — both substitutions yield empty strings,
`COMMAND` is empty, `STRAY` is empty, and the hook takes its `exit 0` branch.
Every gate in the file returns "allow" without having inspected anything, which
is precisely the failure shape st-ad6p was written to end (five gates dormant
May–August, zero symptoms).

## The change

Insert immediately **before** the `COMMAND=$(echo "$INPUT" | jq …)` line
(currently line 61):

```bash
# jq is this hook's parser. Without it every gate below would see an empty
# command and allow — the May–August dormancy, again. Fail closed. [st-kh0l]
if ! command -v jq >/dev/null 2>&1; then
  echo "SCHWAB GATE: jq is not on PATH — blocking rather than failing open." >&2
  echo "             Install jq or fix PATH; nothing runs through this hook" >&2
  echo "             until its parser is back. [finding 14, case st-5qjq]" >&2
  exit 2
fi
```

## The test that pins it

Add to `tests/test_schwab_gate_hook.py` (the suite the hook's own header says
to run before editing):

```python
def test_the_hook_blocks_when_jq_is_missing(tmp_path):
    """Finding 14: with jq absent the hook allowed everything, silently."""
    empty_path = tmp_path / "bin"          # a PATH with no jq in it
    empty_path.mkdir()
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input='{"tool_input": {"command": "python scripts/hello_schwab.py"}}',
        capture_output=True, text=True,
        env={**os.environ, "PATH": str(empty_path)},
    )
    assert proc.returncode == 2
    assert "jq" in proc.stderr
```

(`bash` must be reachable for the test itself, so the test may need
`/usr/bin:/bin` minus jq rather than an empty dir if `bash` builtins do not
suffice; the prepared assertion is the contract, the PATH construction is the
implementation detail.)

## Why fail closed is right here

The hook's job is to refuse; its absence of opinion must read as refusal. The
cost of failing closed is one loud message on a box with a broken PATH. The
cost of failing open was measured on this repo already: every gate dormant for
three months with no symptom.
