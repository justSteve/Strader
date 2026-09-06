# Gate-hook fixtures — the files `tests/test_schwab_gate_hook.py` points the gate at

These exist because the hook decides by reading the named file's imports and
**skips a file that is not there** (`[ -f "$PY_FILE" ] || continue`). While the
suite named production scripts, deleting one of those scripts turned a
"must BLOCK" case into an allow — a green gate over an unguarded gate.

So the behavioural cases name these three, which exist only to be read:

| file | what the hook must do |
|---|---|
| `reaches_schwab_direct.py` | BLOCK — imports `schwab` |
| `reaches_broker_schwab.py` | BLOCK — imports `broker_schwab`, which reaches the live API |
| `reaches_nothing.py` | ALLOW — a `.py` under a gated-looking path that touches neither |

Nothing imports them and pytest does not collect them (no `test_` prefix). They
are data for a shell hook, not modules.

Real coverage of the actual estate is not lost: `test_every_reaching_file_in_the_tree_blocks`
sweeps `git ls-files '*.py'` and asserts the gate blocks every tracked file that
imports either module, the two approved readers excepted. That sweep follows the
tree as it changes instead of pinning three filenames. [st-rfjg, audit row 41]
