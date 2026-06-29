"""Parse orchestration tests with a mocked extractor. [co-7lyf]

No network: the LLM call is injected as a stub returning the tool-input dict the
real model would produce. This exercises ParseResult assembly, stamping, and the
validation gate end to end.
"""
from runbook.mancini import parse as parse_mod

SOURCE = (
    "ES Trade Plan.\n"
    "Supports are: 5812, 5800 (major).\n"
    "Resistances are: 5840, 5862.\n"
    "Bull case: holding 5800 targets 5840.\n"
)

GOOD_EXTRACTION = {
    "date": "2026-06-29",
    "instrument": "ES",
    "session_bias": "bullish above 5800",
    "levels": [
        {"price": 5812, "kind": "support", "source_quote": "Supports are: 5812"},
        {"price": 5840, "kind": "resistance", "source_quote": "Resistances are: 5840"},
    ],
    "commentary": [
        {
            "text": "Holding 5800 targets 5840.",
            "tags": ["bull-case"],
            "trigger": {"type": "price_zone", "anchor_prices": [5800, 5840],
                        "condition_text": "holding 5800"},
            "source_quote": "Bull case: holding 5800 targets 5840.",
        }
    ],
    "raw_excerpt": SOURCE,
}


def test_parse_good_extraction_passes():
    outcome = parse_mod.parse(
        SOURCE,
        extractor=lambda _t: GOOD_EXTRACTION,
        model="claude-opus-4-8",
        parsed_at="2026-06-29T18:00:00Z",
    )
    assert outcome.ok, outcome.validation.errors
    r = outcome.result
    assert r.instrument == "ES"
    assert r.model == "claude-opus-4-8"          # stamped by harness, not model
    assert r.parsed_at == "2026-06-29T18:00:00Z"
    assert len(r.levels) == 2
    assert r.commentary[0].trigger.anchor_prices == [5800.0, 5840.0]


def test_parse_hallucinated_level_fails_validation():
    poisoned = dict(GOOD_EXTRACTION)
    poisoned["levels"] = GOOD_EXTRACTION["levels"] + [
        {"price": 6100, "kind": "resistance", "source_quote": "invented"}
    ]
    outcome = parse_mod.parse(SOURCE, extractor=lambda _t: poisoned)
    assert not outcome.ok
    assert 6100 in outcome.validation.missing_prices


def test_raw_excerpt_defaulted_when_absent():
    no_excerpt = dict(GOOD_EXTRACTION)
    no_excerpt.pop("raw_excerpt")
    outcome = parse_mod.parse(SOURCE, extractor=lambda _t: no_excerpt)
    assert outcome.result.raw_excerpt  # falls back to a slice of source
