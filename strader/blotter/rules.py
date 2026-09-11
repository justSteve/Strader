"""The rule registry — a predictive entity's ``rule:`` block joined to its code. [st-djb9]

WHY
    Until this module, a pre-registered rule was prose in a script docstring
    plus an ``if/elif`` chain in the same file (``final_hour_lens.py:11-54``,
    ``final_hour_combo.py:11-45``): no registry, no id, nothing the blotter
    could iterate. The refactor-and-blotter plan (§5 "The rule block") puts the
    declaration in the entity's header and the code in
    ``scripts/measurement/rules/<id>.py``, named by the entity id, so the prose
    stays in the bundle, the code beside the harness, and one id joins them.

THE CONTRACT
    An entity (``strader.entities.canon``) with a ``rule:`` block declares::

        rule:
          registered: <sha>        # the commit that fixed the rule before any
                                   # scoring — pre-registration by history
          module: rules/<id>       # scripts/measurement/rules/<id>.py
          entry: "<prose>"         # for the page
          exit: {stop_pts, target_pct, time}
          instrument: itm-single-10

    The module exposes ``ID`` (== the entity id), ``STATE`` (the state shape
    it reads — today only :data:`strader.blotter.state.STATE_KIND`),
    ``FIRE_AT`` (the CT minutes it is called at) and
    ``call(state) -> "up" | "down" | None``. A rule that reads a wall clock,
    a file, or the network is not a rule; ``call`` gets a dict and returns a
    word.

    :func:`registry_problems` says everything that is wrong, naming the file:
    a ``rule.module`` with no file, a rules file with no entity, a module
    missing a name, an exit missing a field, an instrument nobody scores. A
    test pins that the real registry has no problems. Strader's counter §5.4:
    ``registered`` must predate the first grid run on that rule, and a
    changed ``exit:`` is a re-registered rule — the sha is carried on every
    row so a later reader can tell.
"""
from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Mapping

from strader.blotter.state import STATE_KIND
from strader.entities.canon import BUNDLE_DIRS, Canon, Entity, REPO_ROOT

__all__ = [
    "RULES_DIR", "INSTRUMENTS", "CALLS", "ExitSpec", "Rule",
    "load_rules", "registry_problems", "RegistryError",
]

RULES_DIR = REPO_ROOT / "scripts" / "measurement" / "rules"

#: The scoreboards the harness knows how to price. ``itm-single-10``: the 0DTE
#: SPXW single ~10 points in the money on the call's side (st-g0jo decision 3;
#: Steve leans ITM for the futures-proxy single, knowledge/singles-as-futures-proxy.md).
INSTRUMENTS = frozenset({"itm-single-10"})
INSTRUMENT_OFFSET_SPX = {"itm-single-10": 10}   # ITM distance, SPX points

CALLS = frozenset({"up", "down"})
STATE_KINDS = frozenset({STATE_KIND})

_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
_TIME_RE = re.compile(r"^(\d{2}:\d{2})(?:\s*CT)?$")


class RegistryError(Exception):
    """The registry does not validate; the message names every problem."""


@dataclass(frozen=True)
class ExitSpec:
    """The declared exit, one per rule: a stop in premium points below the
    entry, a target as a percent of the entry, and the time exit."""

    stop_pts: float
    target_pct: float
    time_ct: str          # "HH:MM"

    @classmethod
    def parse(cls, raw: Mapping) -> "ExitSpec":
        m = _TIME_RE.match(str(raw["time"]).strip())
        if not m:
            raise ValueError(f"exit.time {raw['time']!r} is not 'HH:MM CT'")
        return cls(stop_pts=float(raw["stop_pts"]), target_pct=float(raw["target_pct"]), time_ct=m.group(1))

    def to_dict(self) -> dict:
        return {"stop_pts": self.stop_pts, "target_pct": self.target_pct, "time": f"{self.time_ct} CT"}


@dataclass(frozen=True)
class Rule:
    """One registered rule: the entity, its code, and what the harness scores."""

    id: str
    entity: Entity
    path: Path
    module: ModuleType
    fire_at: tuple[str, ...]
    state_kind: str
    entry: str
    exit: ExitSpec
    instrument: str
    registered: str

    @property
    def offset_spx(self) -> int:
        return INSTRUMENT_OFFSET_SPX[self.instrument]

    def call(self, state: Mapping) -> str | None:
        out = self.module.call(state)
        if out is not None and out not in CALLS:
            raise RegistryError(f"rule {self.id} returned {out!r}; a call is 'up', 'down' or None")
        return out


def _module_path(spec: str, rules_dir: Path) -> Path:
    """``rules/<id>`` (the plan's form) or a bare ``<id>`` -> the file."""
    name = spec.strip()
    if name.startswith("rules/"):
        name = name[len("rules/"):]
    if name.endswith(".py"):
        name = name[:-3]
    return rules_dir / f"{name}.py"


def _import(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"strader_blotter_rule_{path.stem.replace('-', '_')}", path)
    assert spec is not None and spec.loader is not None, path
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _build(entity: Entity, rules_dir: Path) -> tuple[Rule | None, list[str]]:
    raw = entity.rule
    problems: list[str] = []
    assert raw is not None
    path = _module_path(str(raw.get("module", "")), rules_dir)
    if path.stem != entity.id:
        problems.append(f"rule.module {raw.get('module')!r} does not name the entity id {entity.id!r}")
    if not path.is_file():
        problems.append(f"rule.module {raw.get('module')!r}: {path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path} does not exist")
        return None, problems
    registered = str(raw.get("registered", "")).strip()
    if not _SHA_RE.match(registered):
        problems.append(f"rule.registered {registered!r} is not a git sha")
    instrument = str(raw.get("instrument", "")).strip()
    if instrument not in INSTRUMENTS:
        problems.append(f"rule.instrument {instrument!r} not one of {sorted(INSTRUMENTS)}")
    exit_raw = raw.get("exit")
    exit_spec: ExitSpec | None = None
    if not isinstance(exit_raw, Mapping):
        problems.append("rule.exit must be a mapping {stop_pts, target_pct, time}")
    else:
        lacking = [k for k in ("stop_pts", "target_pct", "time") if exit_raw.get(k) in (None, "")]
        if lacking:
            problems.append(f"rule.exit missing {', '.join(lacking)}")
        else:
            try:
                exit_spec = ExitSpec.parse(exit_raw)
            except (ValueError, TypeError) as e:
                problems.append(f"rule.exit does not parse: {e}")
    try:
        mod = _import(path)
    except Exception as e:  # a rules file that does not import is a registry problem, named
        problems.append(f"{path.name} does not import: {e!r}")
        return None, problems
    lacking_names = [name for name in ("ID", "STATE", "FIRE_AT", "call") if not hasattr(mod, name)]
    if lacking_names:
        problems += [f"{path.name} lacks {name}" for name in lacking_names]
        return None, problems          # nothing further can be checked without them
    if mod.ID != entity.id:
        problems.append(f"{path.name}: ID {mod.ID!r} != entity id {entity.id!r}")
    if mod.STATE not in STATE_KINDS:
        problems.append(f"{path.name}: STATE {mod.STATE!r} not one of {sorted(STATE_KINDS)}")
    fire_at = tuple(str(t) for t in (mod.FIRE_AT if isinstance(mod.FIRE_AT, (list, tuple)) else [mod.FIRE_AT]))
    for t in fire_at:
        if not re.match(r"^\d{2}:\d{2}$", t):
            problems.append(f"{path.name}: FIRE_AT entry {t!r} is not 'HH:MM'")
    if not fire_at:
        problems.append(f"{path.name}: FIRE_AT is empty")
    if not callable(mod.call):
        problems.append(f"{path.name}: call is not callable")
    if problems or exit_spec is None:
        return None, problems
    return Rule(id=entity.id, entity=entity, path=path, module=mod, fire_at=fire_at,
                state_kind=str(mod.STATE), entry=str(raw.get("entry", "")).strip(),
                exit=exit_spec, instrument=instrument, registered=registered), []


def _collect(canon: Canon, rules_dir: Path) -> tuple[list[Rule], list[str]]:
    rules: list[Rule] = []
    problems: list[str] = []
    declared: set[str] = set()      # entity ids that carry a rule block, built or not
    for e in canon.all():
        if e.rule is None:
            continue
        declared.add(e.id)
        r, probs = _build(e, rules_dir)
        rel = e.path.relative_to(REPO_ROOT) if e.path.is_relative_to(REPO_ROOT) else e.path
        problems += [f"{rel}: {p}" for p in probs]
        if r is not None:
            rules.append(r)
    if rules_dir.is_dir():
        for p in sorted(rules_dir.glob("*.py")):
            if p.name.startswith("_"):
                continue
            if p.stem in declared:
                continue
            if p.stem in canon:
                ent = canon.by_id(p.stem)
                problems.append(f"{p.name}: entity {p.stem!r} at {ent.path.name} carries no rule block")
            else:
                bad = next((path for path in canon.problems if path.stem == p.stem), None)
                if bad is not None:
                    problems.append(f"{p.name}: its entity {bad.name} does not validate: "
                                    + "; ".join(canon.problems[bad]))
                else:
                    problems.append(f"{p.name}: no entity with id {p.stem!r} in the bundle")
    rules.sort(key=lambda r: r.id)
    return rules, problems


def registry_problems(*, canon: Canon | None = None, rules_dir: Path = RULES_DIR,
                      dirs=BUNDLE_DIRS) -> list[str]:
    """Everything wrong with the registry, one line each; empty when it validates."""
    canon = canon if canon is not None else Canon.load(dirs, strict=False)
    return _collect(canon, rules_dir)[1]


def load_rules(*, canon: Canon | None = None, rules_dir: Path = RULES_DIR, dirs=BUNDLE_DIRS,
               strict: bool = True, only: str | None = None) -> list[Rule]:
    """Every registered rule, sorted by id. ``strict`` raises on any problem;
    ``only`` keeps one id (and raises if it is not registered)."""
    canon = canon if canon is not None else Canon.load(dirs, strict=False)
    rules, problems = _collect(canon, rules_dir)
    if strict and problems:
        raise RegistryError("rule registry does not validate:\n  " + "\n  ".join(problems))
    if only is not None:
        rules = [r for r in rules if r.id == only]
        if not rules:
            raise RegistryError(f"no registered rule with id {only!r}")
    return rules
