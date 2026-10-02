from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Iterable, List, Optional
import json
import math
import re


CONFIDENCE_RANK = {"insufficient": 0, "low": 1, "medium": 2, "high": 3}


@dataclass
class Candidate:
    candidate_id: str
    title: str
    hook: str
    source_asset_id: str
    rationale: str
    evidence_refs: List[str] = field(default_factory=list)
    panel_refs: List[str] = field(default_factory=list)
    confidence: str = "low"
    next_action: str = ""
    disagreement: Dict[str, Any] = field(default_factory=dict)
    hypothesis_type: str = "production_hypothesis"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DistillationResult:
    asset_id: str
    strongest_ideas: List[Dict[str, Any]]
    weaknesses: List[Dict[str, Any]]
    preserve: List[Dict[str, Any]]
    improve: List[Dict[str, Any]]
    reusable_topics: List[Dict[str, Any]]
    content_candidates: List[Candidate]
    product_candidates: List[Candidate]
    business_opportunities: List[Candidate]
    evidence_refs: List[str]
    panel_refs: List[str]
    uncertainty: List[str]
    cross_modal_conflicts: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["content_candidates"] = [c.to_dict() for c in self.content_candidates]
        out["product_candidates"] = [c.to_dict() for c in self.product_candidates]
        out["business_opportunities"] = [c.to_dict() for c in self.business_opportunities]
        return out


class DistillationEngine:
    """Dependency-light v1 distillation engine.

    It ranks what is already present in the evidence/panel data. It does not
    pretend to perform transcription, audio analysis, visual analysis, or
    market validation.
    """

    def __init__(self, min_confidence: str = "low"):
        if min_confidence not in CONFIDENCE_RANK:
            raise ValueError("Invalid min_confidence")
        self.min_confidence = min_confidence

    @staticmethod
    def _asset_id(asset: Dict[str, Any]) -> str:
        asset_id = asset.get("asset_id")
        if not asset_id:
            raise ValueError("Master Asset requires asset_id")
        return str(asset_id)

    @staticmethod
    def _evidence(asset: Dict[str, Any]) -> List[Dict[str, Any]]:
        ev = asset.get("evidence", {})
        if isinstance(ev, list):
            return ev
        records = []
        for modality in ("text", "audio", "visual"):
            value = ev.get(modality, []) if isinstance(ev, dict) else []
            if isinstance(value, list):
                records.extend(value)
        return records

    @staticmethod
    def _panel_reactions(asset: Dict[str, Any]) -> List[Dict[str, Any]]:
        panel = asset.get("panel", {})
        reactions = panel.get("reactions", []) if isinstance(panel, dict) else []
        return reactions if isinstance(reactions, list) else []

    @staticmethod
    def _safe_num(value: Any, default: float = 0.0) -> float:
        try:
            number = float(value)
            if not math.isfinite(number) or not 0 <= number <= 10:
                raise ValueError("Panel scores must be finite and between 0 and 10")
            return number
        except (TypeError, ValueError):
            return default

    def _evidence_score(self, refs: Iterable[str], evidence_by_id: Dict[str, Dict[str, Any]]) -> float:
        scores = []
        for ref in refs:
            ev = evidence_by_id.get(ref, {})
            tier = str(ev.get("tier", "T1"))
            confidence = str(ev.get("confidence", "low"))
            tier_score = {"T1": 1.0, "T2": .8, "T3": .6, "T4": .4, "T5": .2}.get(tier, .2)
            conf_score = {"high": 1.0, "medium": .7, "low": .4, "insufficient": 0.0}.get(confidence, 0.0)
            scores.append(tier_score * conf_score)
        return sum(scores) / len(scores) if scores else 0.0

    def _panel_support(self, panel_refs: Iterable[str], panel_by_id: Dict[str, Dict[str, Any]]) -> float:
        values = []
        for ref in panel_refs:
            reaction = panel_by_id.get(ref, {})
            dims = reaction.get("dimensions", {})
            if isinstance(dims, dict):
                useful = self._safe_num(dims.get("usefulness"))
                originality = self._safe_num(dims.get("originality"))
                memorability = self._safe_num(dims.get("memorability"))
                values.append((useful + originality + memorability) / 30.0)
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _refs(item: Dict[str, Any]) -> List[str]:
        refs = item.get("evidence_refs", []) or item.get("evidence_ids", [])
        return [str(x) for x in refs] if isinstance(refs, list) else []

    @staticmethod
    def _panel_refs(item: Dict[str, Any]) -> List[str]:
        refs = item.get("panel_refs", []) or item.get("reaction_refs", [])
        return [str(x) for x in refs] if isinstance(refs, list) else []

    def _confidence(self, evidence_refs: List[str], panel_refs: List[str],
                    evidence_by_id: Dict[str, Dict[str, Any]]) -> str:
        ev_score = self._evidence_score(evidence_refs, evidence_by_id)
        if not evidence_refs or ev_score == 0:
            return "insufficient"
        if ev_score >= .75:
            return "high"
        if ev_score >= .45:
            return "medium"
        return "low"

    @staticmethod
    def _normalize_items(items: Any) -> List[Dict[str, Any]]:
        if not isinstance(items, list):
            return []
        result = []
        for i, item in enumerate(items, 1):
            if isinstance(item, str):
                result.append({"id": f"item-{i}", "statement": item})
            elif isinstance(item, dict):
                result.append(dict(item))
        return result

    def _rank_ideas(self, asset: Dict[str, Any], evidence_by_id: Dict[str, Dict[str, Any]],
                    panel_by_id: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        raw = []
        # Accept analyst-created ideas if present, otherwise use strong evidence claims.
        distilled = asset.get("distillation", {})
        if not isinstance(distilled, dict):
            raise ValueError("distillation must be an object")
        raw.extend(self._normalize_items(distilled.get("strongest_ideas", [])))
        if not raw:
            for ev in self._evidence(asset):
                if ev.get("claim") and str(ev.get("tier", "T1")) in {"T1", "T2"}:
                    raw.append({
                        "statement": ev["claim"],
                        "evidence_refs": [ev.get("evidence_id")] if ev.get("evidence_id") else []
                    })

        scored = []
        for idx, item in enumerate(raw, 1):
            ev_refs = self._refs(item)
            p_refs = self._panel_refs(item)
            if any(ref not in evidence_by_id for ref in ev_refs):
                raise ValueError("idea references unknown evidence")
            if any(ref not in panel_by_id for ref in p_refs):
                raise ValueError("idea references unknown panel reaction")
            score = .55 * self._evidence_score(ev_refs, evidence_by_id) + .45 * self._panel_support(p_refs, panel_by_id)
            row = dict(item)
            row["rank_score"] = round(score, 3)
            row["confidence"] = self._confidence(ev_refs, p_refs, evidence_by_id)
            row["evidence_refs"] = ev_refs
            row["panel_refs"] = p_refs
            row["source_tiers"] = sorted({evidence_by_id[ref]["tier"] for ref in ev_refs})
            row.setdefault("id", f"idea-{idx}")
            scored.append(row)
        return sorted(scored, key=lambda x: x["rank_score"], reverse=True)

    def _disagreement(self, asset: Dict[str, Any]) -> Dict[str, Any]:
        panel = asset.get("panel", {})
        dm = panel.get("disagreement_map", {}) if isinstance(panel, dict) else {}
        if isinstance(dm, list):
            return {"disagreements": dm}
        return dm if isinstance(dm, dict) else {}

    def _make_candidates(self, kind: str, asset_id: str, ideas: List[Dict[str, Any]],
                         disagreement: Dict[str, Any]) -> List[Candidate]:
        candidates = []
        templates = {
            "content": ("Explain: {title}", "Turn the strongest idea into a short explanation, story, post, or video."),
            "product": ("Teach: {title}", "Package the idea into a repeatable transformation, lesson, framework, tool, or service."),
            "business": ("Test demand for: {title}", "Treat this as a market hypothesis and test whether a real audience has the problem and will exchange money for the outcome.")
        }
        for i, idea in enumerate(ideas[:5], 1):
            if CONFIDENCE_RANK[idea["confidence"]] < CONFIDENCE_RANK[self.min_confidence]:
                continue
            title = str(idea.get("title") or idea.get("statement") or idea.get("hook") or f"Idea {i}")
            hook = str(idea.get("hook") or title)
            rationale = str(idea.get("rationale") or idea.get("statement") or "Derived from the source asset.")
            ev_refs = self._refs(idea)
            p_refs = self._panel_refs(idea)
            ctype = {"content": "production_hypothesis", "product": "production_hypothesis", "business": "business_hypothesis"}[kind]
            next_action = templates[kind][1]
            if kind == "business":
                next_action += " Do not treat the simulated panel as proof."
            candidates.append(Candidate(
                candidate_id=f"{asset_id}:{kind}-{i:02d}",
                title=templates[kind][0].format(title=title),
                hook=hook,
                source_asset_id=asset_id,
                rationale=rationale,
                evidence_refs=ev_refs,
                panel_refs=p_refs,
                confidence=str(idea.get("confidence", "low")),
                next_action=next_action,
                disagreement=disagreement,
                hypothesis_type=ctype
            ))
        return candidates

    def distill(self, asset: Dict[str, Any]) -> DistillationResult:
        if not isinstance(asset, dict):
            raise ValueError("Master Asset must be an object")
        asset_id = self._asset_id(asset)
        evidence = self._evidence(asset)
        reactions = self._panel_reactions(asset)
        for rows, key in ((evidence, "evidence_id"), (reactions, "reaction_id")):
            identifiers = []
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("evidence and reactions must be objects")
                identifier = row.get(key) or (row.get("panelist_id") if key == "reaction_id" else None)
                if not isinstance(identifier, str) or not identifier:
                    raise ValueError("evidence and reactions require stable IDs")
                identifiers.append(identifier)
                if row.get("asset_id", asset_id) != asset_id:
                    raise ValueError("evidence or reaction belongs to another asset")
                if key == "evidence_id" and (row.get("tier") not in {"T1", "T2", "T3", "T4", "T5"} or row.get("confidence") not in CONFIDENCE_RANK):
                    raise ValueError("invalid evidence tier or confidence")
                if key == "reaction_id":
                    for value in row.get("dimensions", {}).values():
                        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 10:
                            raise ValueError("invalid panel score")
            if len(set(identifiers)) != len(identifiers):
                raise ValueError("duplicate evidence or reaction ID")
        evidence_by_id = {str(e.get("evidence_id")): e for e in evidence if e.get("evidence_id")}
        panel_by_id = {str(r.get("reaction_id") or r.get("panelist_id")): r for r in reactions if r.get("reaction_id") or r.get("panelist_id")}

        d = asset.get("distillation", {}) if isinstance(asset.get("distillation", {}), dict) else {}
        ideas = self._rank_ideas(asset, evidence_by_id, panel_by_id)
        weaknesses = self._normalize_items(d.get("weakest_sections", []))
        preserve = self._normalize_items(d.get("preserve", []))
        improve = self._normalize_items(d.get("improve", []))
        topics = self._normalize_items(d.get("reusable_topics", []))

        # If no explicit topics exist, use top ideas as topic seeds.
        if not topics:
            topics = [{"topic": x.get("title") or x.get("statement"), "source_idea_id": x.get("id")} for x in ideas[:5]]

        all_ev_refs = sorted({str(e.get("evidence_id")) for e in evidence if e.get("evidence_id")})
        all_panel_refs = sorted({str(r.get("reaction_id") or r.get("panelist_id")) for r in reactions if r.get("reaction_id") or r.get("panelist_id")})

        uncertainty = []
        if not evidence:
            uncertainty.append("No structured evidence records were supplied.")
        if not reactions:
            uncertainty.append("No Walk With Me reactions were supplied; audience implications remain untested.")
        dm = self._disagreement(asset)
        if dm:
            uncertainty.append("Panel disagreement was preserved rather than collapsed; review minority/high-spread findings before shipping.")
        uncertainty.append("Product and business entries are hypotheses, not proof of demand, conversion, or willingness to pay.")
        conflicts = asset.get("evidence", {}).get("cross_modal_conflicts", []) if isinstance(asset.get("evidence"), dict) else []
        if conflicts:
            uncertainty.append("Cross-modal conflicts remain unresolved and are retained in the output.")
        if any(x["confidence"] == "insufficient" for x in ideas):
            uncertainty.append("Unsupported ideas are retained for review, not promoted into production candidates.")

        return DistillationResult(
            asset_id=asset_id,
            strongest_ideas=ideas,
            weaknesses=weaknesses,
            preserve=preserve,
            improve=improve,
            reusable_topics=topics,
            content_candidates=self._make_candidates("content", asset_id, ideas, dm),
            product_candidates=self._make_candidates("product", asset_id, ideas, dm),
            business_opportunities=self._make_candidates("business", asset_id, ideas, dm),
            evidence_refs=all_ev_refs,
            panel_refs=all_panel_refs,
            uncertainty=uncertainty,
            cross_modal_conflicts=conflicts
        )

    @staticmethod
    def validate(result: Dict[str, Any]) -> List[str]:
        errors = []
        required = [
            "asset_id", "strongest_ideas", "weaknesses", "preserve", "improve",
            "reusable_topics", "content_candidates", "product_candidates",
            "business_opportunities", "evidence_refs", "panel_refs", "uncertainty"
        ]
        for key in required:
            if key not in result:
                errors.append(f"missing:{key}")

        for kind in ("content_candidates", "product_candidates", "business_opportunities"):
            for idx, candidate in enumerate(result.get(kind, [])):
                if candidate.get("source_asset_id") != result.get("asset_id"):
                    errors.append(f"{kind}[{idx}]:broken_provenance")
                if kind == "business_opportunities" and candidate.get("hypothesis_type") != "business_hypothesis":
                    errors.append(f"{kind}[{idx}]:must_be_business_hypothesis")
        return errors


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(data: Dict[str, Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("asset_json")
    parser.add_argument("--out", default="distillation_result.json")
    args = parser.parse_args()
    result = DistillationEngine().distill(load_json(args.asset_json))
    dump_json(result.to_dict(), args.out)
    errors = DistillationEngine.validate(result.to_dict())
    if errors:
        raise SystemExit("Validation failed: " + "; ".join(errors))
    print(f"Wrote {args.out}")
