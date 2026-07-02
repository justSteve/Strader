"""Tests for the stdlib block-YAML subset loader (strader/_yaml.py).

These exercise the bundled subset loader directly (``_load_subset``) so the
no-dependency fallback is covered regardless of whether PyYAML is installed in
the environment.
"""

from __future__ import annotations

import textwrap

import pytest

from strader import _yaml
from strader.entities.playbook import CONDITIONS_PATH

SAMPLE = textwrap.dedent(
    """\
    # a whole-line comment
    top:
      name: "hello world"        # inline comment, quote-aware
      count: 3
      ratio: 1.5
      flag_true: true
      flag_false: false
      empty: null
      tags: [a, b, c]
      nested:
        deep: "value; with: punctuation"
        weight: high
    other: plain
    """
)


def test_subset_scalars_and_nesting():
    data = _yaml._load_subset(SAMPLE)
    assert data["other"] == "plain"
    top = data["top"]
    assert top["name"] == "hello world"
    assert top["count"] == 3
    assert top["ratio"] == 1.5
    assert top["flag_true"] is True
    assert top["flag_false"] is False
    assert top["empty"] is None
    assert top["tags"] == ["a", "b", "c"]
    assert top["nested"]["deep"] == "value; with: punctuation"
    assert top["nested"]["weight"] == "high"


def test_block_sequence_same_indent():
    data = _yaml._load_subset("items:\n- one\n- two\n")
    assert data["items"] == ["one", "two"]


def test_flow_mapping_is_rejected():
    with pytest.raises(_yaml.YamlError):
        _yaml._load_subset("k: {a: 1}\n")


def test_conditions_file_parses_via_public_loader():
    # safe_load uses PyYAML when present, else the subset loader; either way the
    # real conditions.yaml must parse to the expected shape.
    data = _yaml.load_file(CONDITIONS_PATH)
    day_context = data["tiers"]["day_context"]
    assert "trend-up" in day_context
    assert day_context["mancini-carmine-confluence"]["weight"] == "high"
    assert data["tiers"]["entry_confirmation"]["return-to-lvn"]["def"]
