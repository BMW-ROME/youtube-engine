"""Synthetic engineering fixtures, not real audience or market evidence."""

from copy import deepcopy

import pytest

from voice_engine.distillation import DistillationEngine
from voice_engine.evidence import EvidenceEngine
from voice_engine.panel import DIMENSIONS, WalkWithMeEngine


def reaction(index):
    return {"panelist_id": f"WMW-{index:02d}", "asset_id": "A1", "verdict": "mixed",
            "strongest_point": "clear analogy", "weakest_point": "long setup",
            "reaction": "synthetic test only", "dimensions": {d: 5 for d in DIMENSIONS},
            "evidence_refs": ["EV-1"], "uncertainty": ["text only"],
            "keep": ["analogy"], "change": ["shorten setup"]}


def asset():
    evidence = EvidenceEngine().add_observation("A1", "text", "The fixture uses an analogy.", "fixture:1")
    evidence.evidence_id = "EV-1"
    panel = WalkWithMeEngine()
    rows = [reaction(i) for i in range(1, 9)]
    rows[0]["dimensions"]["humor"] = 1
    rows[5]["dimensions"]["humor"] = 9
    reactions = panel.validate_panel(rows, asset_id="A1")
    return {"asset_id": "A1", "source": {"transcript": "Synthetic analogy fixture."},
            "evidence": {"text": [EvidenceEngine.to_dict(evidence)], "audio": [], "visual": [],
                         "cross_modal_conflicts": []},
            "panel": {"reactions": [r.to_dict() for r in reactions],
                      "disagreement_map": panel.preserve_disagreement(reactions)},
            "distillation": {"strongest_ideas": [{"id": "idea-1", "statement": "Explain with analogies",
                             "evidence_refs": ["EV-1"], "panel_refs": ["WMW-06"]}]}}


def test_synthetic_contract_chain_preserves_source_and_independent_disagreement():
    source = asset()
    original = deepcopy(source)
    result = DistillationEngine().distill(source).to_dict()
    assert source == original
    assert len(source["panel"]["reactions"]) == 8
    assert result["strongest_ideas"][0]["source_tiers"] == ["T1"]
    for key in ("content_candidates", "product_candidates", "business_opportunities"):
        assert result[key][0]["source_asset_id"] == "A1"
        assert result[key][0]["evidence_refs"] == ["EV-1"]
        disagreements = result[key][0]["disagreement"]["disagreements"]
        humor = next(row for row in disagreements if row["dimension"] == "humor")
        assert humor["spread"] == 8
        assert len(humor["scores"]) == 8
    assert result["business_opportunities"][0]["hypothesis_type"] == "business_hypothesis"
    assert DistillationEngine.validate(result) == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 11, True])
def test_panel_rejects_invalid_scores(value):
    rows = [reaction(i) for i in range(1, 9)]
    rows[0]["dimensions"]["humor"] = value
    with pytest.raises(ValueError):
        WalkWithMeEngine().validate_panel(rows)


def test_panel_preserves_original_identifiers_and_requires_all_eight():
    engine = WalkWithMeEngine()
    assert len(engine.definition["panelists"]) == 8
    assert engine.definition["panelists"][1]["name"] == "The Skeptic"
    with pytest.raises(ValueError):
        engine.validate_panel([reaction(i) for i in range(1, 8)])
    rows = [reaction(i) for i in range(1, 9)]
    rows[-1]["panelist_id"] = rows[0]["panelist_id"]
    with pytest.raises(ValueError):
        engine.validate_panel(rows)


@pytest.mark.parametrize("field,ref", [("evidence_refs", "missing-evidence"), ("panel_refs", "missing-panel")])
def test_distillation_rejects_orphaned_references(field, ref):
    record = asset()
    record["distillation"]["strongest_ideas"][0][field] = [ref]
    with pytest.raises(ValueError):
        DistillationEngine().distill(record)


def test_unsupported_idea_is_not_promoted():
    record = asset()
    record["evidence"]["text"] = []
    record["distillation"]["strongest_ideas"][0]["evidence_refs"] = []
    result = DistillationEngine().distill(record).to_dict()
    assert result["strongest_ideas"][0]["confidence"] == "insufficient"
    assert result["content_candidates"] == []
    assert result["business_opportunities"] == []


def test_minimum_confidence_filters_candidates():
    record = asset()
    record["evidence"]["text"][0]["confidence"] = "low"
    result = DistillationEngine(min_confidence="high").distill(record).to_dict()
    assert result["content_candidates"] == []
    assert result["strongest_ideas"]


def test_conflict_and_list_disagreement_are_not_dropped():
    record = asset()
    record["evidence"]["cross_modal_conflicts"] = [{"conflict_id": "CF-1", "resolution": "unresolved"}]
    record["panel"]["disagreement_map"] = [{"dimension": "humor", "spread": 8}]
    result = DistillationEngine().distill(record).to_dict()
    assert result["cross_modal_conflicts"] == record["evidence"]["cross_modal_conflicts"]
    assert result["content_candidates"][0]["disagreement"]["disagreements"][0]["spread"] == 8


@pytest.mark.parametrize("change", ["duplicate", "foreign_asset", "nonfinite_panel"])
def test_distillation_rejects_inconsistent_inputs(change):
    record = asset()
    if change == "duplicate":
        record["evidence"]["text"].append(deepcopy(record["evidence"]["text"][0]))
    elif change == "foreign_asset":
        record["evidence"]["text"][0]["asset_id"] = "A2"
    else:
        record["panel"]["reactions"][0]["dimensions"]["humor"] = float("nan")
    with pytest.raises(ValueError):
        DistillationEngine().distill(record)
