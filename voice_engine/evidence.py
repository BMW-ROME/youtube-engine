"""
Helping Others With My Voice — Evidence Engine v1

Purpose:
    Convert available source material into traceable evidence records.
    This module deliberately separates observations from interpretations.

It is intentionally dependency-light. It does not pretend to infer audio/video
facts that are not actually supplied by an upstream analyzer.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import uuid


CONFIDENCE = {"high", "medium", "low", "insufficient"}
TIERS = {"T1", "T2", "T3", "T4", "T5"}
MODALITIES = {"text", "audio", "visual"}


@dataclass
class Evidence:
    asset_id: str
    modality: str
    tier: str
    claim: str
    source_reference: str
    confidence: str = "high"
    timestamp_start: Optional[float] = None
    timestamp_end: Optional[float] = None
    supporting_observations: List[str] = field(default_factory=list)
    notes: Optional[str] = None
    evidence_id: str = field(default_factory=lambda: f"EV-{uuid.uuid4().hex[:8]}")


@dataclass
class Conflict:
    asset_id: str
    modalities: List[str]
    observations: List[str]
    interpretation: Optional[str] = None
    confidence: str = "low"
    resolution: str = "unresolved"
    conflict_id: str = field(default_factory=lambda: f"CF-{uuid.uuid4().hex[:8]}")


class EvidenceEngine:
    """Create and reconcile evidence without silently upgrading uncertainty."""

    def add_observation(self, asset_id: str, modality: str, claim: str,
                        source_reference: str, confidence: str = "high",
                        timestamp_start: Optional[float] = None,
                        timestamp_end: Optional[float] = None,
                        notes: Optional[str] = None) -> Evidence:
        self._validate_modality(modality)
        self._validate_confidence(confidence)
        return Evidence(
            asset_id=asset_id,
            modality=modality,
            tier="T1",
            claim=claim,
            source_reference=source_reference,
            confidence=confidence,
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
            notes=notes,
        )

    def add_inference(self, asset_id: str, modality: str, claim: str,
                      source_reference: str,
                      supporting_observations: List[str],
                      confidence: str = "medium",
                      tier: str = "T2") -> Evidence:
        self._validate_modality(modality)
        self._validate_confidence(confidence)
        if tier not in {"T2", "T3", "T4", "T5"}:
            raise ValueError("Inference tier must be T2, T3, T4, or T5.")
        if not supporting_observations:
            raise ValueError("An inference requires supporting observations.")
        return Evidence(
            asset_id=asset_id,
            modality=modality,
            tier=tier,
            claim=claim,
            source_reference=source_reference,
            confidence=confidence,
            supporting_observations=supporting_observations,
        )

    def reconcile(self, asset_id: str, observations_by_modality: Dict[str, List[str]]) -> List[Conflict]:
        present = [m for m in observations_by_modality if m in MODALITIES and observations_by_modality[m]]
        if len(present) < 2:
            return []

        # v1 deliberately flags cross-modal disagreement for review rather than
        # inventing a semantic resolution. A higher-level analyzer can populate
        # interpretation/resolution after reviewing the actual evidence.
        conflicts = []
        for i, first in enumerate(present):
            for second in present[i + 1:]:
                conflicts.append(
                    Conflict(
                        asset_id=asset_id,
                        modalities=[first, second],
                        observations=[
                            f"{first}: {observations_by_modality[first]}",
                            f"{second}: {observations_by_modality[second]}",
                        ],
                        confidence="low",
                        resolution="unresolved",
                    )
                )
        return conflicts

    @staticmethod
    def to_dict(record: Any) -> Dict[str, Any]:
        return asdict(record)

    @staticmethod
    def _validate_modality(modality: str) -> None:
        if modality not in MODALITIES:
            raise ValueError(f"Unsupported modality: {modality}")

    @staticmethod
    def _validate_confidence(confidence: str) -> None:
        if confidence not in CONFIDENCE:
            raise ValueError(f"Unsupported confidence: {confidence}")
