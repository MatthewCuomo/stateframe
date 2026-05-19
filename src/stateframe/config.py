"""Configuration objects for scans and suggested follow-up analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ScanDepth = Literal["quick", "standard", "deep"]
AssumptionRisk = Literal["conservative", "moderate", "aggressive"]
GuidanceMode = Literal["guided", "balanced", "expert"]
SemanticPolicy = Literal["auto", "minimal", "off"]
VisualPolicy = Literal["none", "recommended", "rich"]
ExplanationLevel = Literal["terse", "standard", "detailed"]
EvidenceSource = Literal[
    "semantic",
    "statistical",
    "quality",
    "relationship",
    "target",
    "time",
    "model",
    "visual",
    "cleaning",
    "performance",
]


DEFAULT_RECOMMENDATION_BASIS: dict[GuidanceMode, list[EvidenceSource]] = {
    "guided": [
        "semantic",
        "statistical",
        "quality",
        "relationship",
        "target",
        "time",
        "visual",
        "cleaning",
        "model",
    ],
    "balanced": ["statistical", "quality", "relationship", "semantic", "target", "time", "visual", "cleaning"],
    "expert": ["statistical", "quality", "relationship", "target", "time", "model", "cleaning"],
}


MODE_SOURCE_WEIGHTS: dict[GuidanceMode, dict[EvidenceSource, float]] = {
    "guided": {
        "semantic": 1.0,
        "statistical": 1.0,
        "quality": 1.05,
        "relationship": 1.0,
        "target": 1.05,
        "time": 1.05,
        "model": 0.85,
        "visual": 1.18,
        "cleaning": 1.05,
        "performance": 0.9,
    },
    "balanced": {
        "semantic": 0.85,
        "statistical": 1.08,
        "quality": 1.1,
        "relationship": 1.08,
        "target": 1.08,
        "time": 1.0,
        "model": 1.0,
        "visual": 1.0,
        "cleaning": 1.05,
        "performance": 0.95,
    },
    "expert": {
        "semantic": 0.28,
        "statistical": 1.22,
        "quality": 1.18,
        "relationship": 1.22,
        "target": 1.12,
        "time": 1.08,
        "model": 1.12,
        "visual": 0.92,
        "cleaning": 1.05,
        "performance": 1.08,
    },
}


@dataclass(frozen=True)
class ScanConfig:
    """Controls how much work the first-pass scan is allowed to do."""

    scan_depth: ScanDepth = "standard"
    guidance: GuidanceMode = "guided"
    semantic_policy: SemanticPolicy = "auto"
    recommendation_basis: list[EvidenceSource] | None = None
    visual_policy: VisualPolicy = "rich"
    explanation_level: ExplanationLevel = "standard"
    sample_size: int | None = None
    random_state: int = 42
    max_top_values: int = 10
    max_relationship_columns: int = 50
    high_cardinality_threshold: int = 50
    high_cardinality_ratio: float = 0.5
    target_auto_select_threshold: float = 0.90
    time_auto_select_threshold: float = 0.80
    risk: AssumptionRisk = "conservative"

    @classmethod
    def from_mode(
        cls,
        mode: str = "standard",
        *,
        sample_size: int | None = None,
        risk: AssumptionRisk = "conservative",
        guidance: GuidanceMode | None = None,
        semantic_policy: SemanticPolicy | None = None,
        recommendation_basis: list[EvidenceSource] | None = None,
        visual_policy: VisualPolicy | None = None,
        explanation_level: ExplanationLevel | None = None,
    ) -> "ScanConfig":
        depth: ScanDepth
        if mode in {"quick", "standard", "deep"}:
            depth = mode  # type: ignore[assignment]
        else:
            depth = "standard"
        resolved_guidance: GuidanceMode = guidance or "guided"
        defaults = _mode_defaults(resolved_guidance)
        return cls(
            scan_depth=depth,
            guidance=resolved_guidance,
            semantic_policy=semantic_policy or defaults["semantic_policy"],
            recommendation_basis=recommendation_basis,
            visual_policy=visual_policy or defaults["visual_policy"],
            explanation_level=explanation_level or defaults["explanation_level"],
            sample_size=sample_size,
            risk=risk,
        )

    @property
    def active_recommendation_basis(self) -> list[EvidenceSource]:
        if self.recommendation_basis is not None:
            return list(self.recommendation_basis)
        return list(DEFAULT_RECOMMENDATION_BASIS[self.guidance])

    @property
    def mode_source_weights(self) -> dict[EvidenceSource, float]:
        return dict(MODE_SOURCE_WEIGHTS[self.guidance])

    def allows_source(self, source: EvidenceSource) -> bool:
        return source in self.active_recommendation_basis


def _mode_defaults(guidance: GuidanceMode) -> dict[str, Any]:
    if guidance == "expert":
        return {
            "semantic_policy": "minimal",
            "visual_policy": "recommended",
            "explanation_level": "terse",
        }
    if guidance == "balanced":
        return {
            "semantic_policy": "auto",
            "visual_policy": "recommended",
            "explanation_level": "standard",
        }
    return {
        "semantic_policy": "auto",
        "visual_policy": "rich",
        "explanation_level": "standard",
    }


@dataclass(frozen=True)
class SuggestedConfig:
    """High-confidence assumptions the scan can hand to a follow-up report."""

    target: str | None = None
    task: str | None = None
    time_column: str | None = None
    id_columns: list[str] = field(default_factory=list)
    ignore_columns: list[str] = field(default_factory=list)
    binary_mappings: dict[str, dict[Any, Any]] = field(default_factory=dict)
    ambiguous_binary_flags: list[str] = field(default_factory=list)
    numeric_conversions: dict[str, str] = field(default_factory=dict)
    datetime_conversions: dict[str, str] = field(default_factory=dict)
    recommended_checks: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    risk: AssumptionRisk = "conservative"

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "task": self.task,
            "time_column": self.time_column,
            "id_columns": list(self.id_columns),
            "ignore_columns": list(self.ignore_columns),
            "binary_mappings": {
                column: dict(mapping) for column, mapping in self.binary_mappings.items()
            },
            "ambiguous_binary_flags": list(self.ambiguous_binary_flags),
            "numeric_conversions": dict(self.numeric_conversions),
            "datetime_conversions": dict(self.datetime_conversions),
            "recommended_checks": list(self.recommended_checks),
            "assumptions": list(self.assumptions),
            "risk": self.risk,
        }

    def summary(self) -> str:
        lines = ["Using suggested stateframe configuration"]
        if self.target:
            lines.append(f"- Target: {self.target}")
        if self.task:
            lines.append(f"- Task: {self.task}")
        if self.time_column:
            lines.append(f"- Time column: {self.time_column}")
        if self.id_columns:
            lines.append(f"- ID columns ignored: {', '.join(self.id_columns)}")
        if self.binary_mappings:
            lines.append(
                "- Binary mappings: "
                + ", ".join(sorted(self.binary_mappings.keys()))
            )
        if self.ambiguous_binary_flags:
            lines.append(
                "- Ambiguous binary flags preserved: "
                + ", ".join(self.ambiguous_binary_flags)
            )
        if self.numeric_conversions:
            lines.append(
                "- Numeric conversions: "
                + ", ".join(sorted(self.numeric_conversions.keys()))
            )
        if self.datetime_conversions:
            lines.append(
                "- Datetime conversions: "
                + ", ".join(sorted(self.datetime_conversions.keys()))
            )
        if self.recommended_checks:
            lines.append("- Checks: " + ", ".join(self.recommended_checks))
        return "\n".join(lines)
