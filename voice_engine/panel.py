"""Validate supplied independent synthetic reactions; never invent them."""

import json
import math
from dataclasses import dataclass
from pathlib import Path

DIMENSIONS = (
    "clarity", "originality", "usefulness", "attention", "authenticity",
    "emotional_impact", "memorability", "curiosity", "humor",
    "self_indulgence", "trust", "distinctiveness",
)


@dataclass
class Reaction:
    panelist_id: str
    asset_id: str
    dimensions: dict
    record: dict

    def to_dict(self):
        return {**self.record, "dimensions": dict(self.dimensions)}


class WalkWithMeEngine:
    def __init__(self, definition_path=None):
        path = Path(definition_path) if definition_path else Path(__file__).with_name("panel_definition.json")
        self.definition = json.loads(path.read_text(encoding="utf-8"))
        self.ids = {row["id"] for row in self.definition["panelists"]}
        if self.ids != {f"WMW-{i:02d}" for i in range(1, 9)}:
            raise ValueError("preserve the eight original panel identities")

    def validate_panel(self, records, *, asset_id=None):
        if not isinstance(records, list) or len(records) != 8:
            raise ValueError("exactly eight independent reactions are required")
        reactions = []
        seen = set()
        required = {"panelist_id", "asset_id", "verdict", "strongest_point", "weakest_point",
                    "reaction", "dimensions", "evidence_refs", "uncertainty", "keep", "change"}
        for record in records:
            if not isinstance(record, dict) or not required <= record.keys():
                raise ValueError("incomplete panel reaction")
            pid = record["panelist_id"]
            if pid not in self.ids or pid in seen:
                raise ValueError("unknown or duplicate panelist")
            seen.add(pid)
            rid = record["asset_id"]
            if not isinstance(rid, str) or not rid:
                raise ValueError("reaction requires source asset")
            if asset_id is None:
                asset_id = rid
            if rid != asset_id:
                raise ValueError("panel reactions cannot mix source assets")
            dims = record["dimensions"]
            if not isinstance(dims, dict) or set(dims) != set(DIMENSIONS):
                raise ValueError("reaction requires every defined dimension")
            for value in dims.values():
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 10:
                    raise ValueError("dimension scores must be finite numbers from 0 to 10")
            for key in ("evidence_refs", "uncertainty", "keep", "change"):
                if not isinstance(record[key], list) or not all(isinstance(x, str) for x in record[key]):
                    raise ValueError(f"{key} must be a list of strings")
            reactions.append(Reaction(pid, rid, dict(dims), dict(record)))
        return reactions

    def preserve_disagreement(self, reactions):
        records = [r.to_dict() if isinstance(r, Reaction) else r for r in reactions]
        validated = self.validate_panel(records)
        disagreements = []
        for dimension in DIMENSIONS:
            scores = {r.panelist_id: r.dimensions[dimension] for r in validated}
            low, high = min(scores.values()), max(scores.values())
            if low != high:
                disagreements.append({"dimension": dimension, "min": low, "max": high,
                                      "spread": high - low, "scores": scores})
        return {"disagreements": disagreements, "reactions": records,
                "audience_type": "synthetic", "market_validated": False}
