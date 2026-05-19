"""Registry of executable stateframe lenses.

The registry is intentionally lightweight for now: it gives every lens a stable
ID, aliases, compatibility metadata, output expectations, and visual support.
The execution functions still live in ``stateframe.lenses``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from stateframe.config import EvidenceSource


Cost = Literal["metadata-only", "cheap", "low", "medium", "high", "expensive"]


@dataclass(frozen=True)
class LensSpec:
    id: str
    family: str
    title: str
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    required_roles: list[str] = field(default_factory=list)
    compatible_semantic_types: list[str] = field(default_factory=list)
    compatible_shapes: list[str] = field(default_factory=list)
    compatible_targets: list[str] = field(default_factory=list)
    cost: Cost = "low"
    evidence_sources: list[EvidenceSource] = field(default_factory=list)
    output_types: list[str] = field(default_factory=list)
    visual_kinds: list[str] = field(default_factory=list)

    @property
    def has_visual(self) -> bool:
        return bool(self.visual_kinds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "family": self.family,
            "title": self.title,
            "description": self.description,
            "aliases": list(self.aliases),
            "required_roles": list(self.required_roles),
            "compatible_semantic_types": list(self.compatible_semantic_types),
            "compatible_shapes": list(self.compatible_shapes),
            "compatible_targets": list(self.compatible_targets),
            "cost": self.cost,
            "evidence_sources": list(self.evidence_sources),
            "output_types": list(self.output_types),
            "visual_kinds": list(self.visual_kinds),
        }


_SPECS: dict[str, LensSpec] = {}
_ALIASES: dict[str, str] = {}


def register(spec: LensSpec) -> LensSpec:
    _SPECS[spec.id] = spec
    for alias in spec.aliases:
        _ALIASES[alias] = spec.id
    return spec


def resolve_lens_id(lens_id: str) -> str:
    return _ALIASES.get(lens_id, lens_id)


def get_lens_spec(lens_id: str) -> LensSpec:
    resolved = resolve_lens_id(lens_id)
    try:
        return _SPECS[resolved]
    except KeyError as exc:
        raise ValueError(f"Unknown lens: {lens_id}") from exc


def all_lenses() -> list[LensSpec]:
    return sorted(_SPECS.values(), key=lambda spec: (spec.family, spec.id))


def available_lenses(profile: Any, *, family: str | None = None) -> list[LensSpec]:
    specs = all_lenses()
    if family is not None:
        specs = [spec for spec in specs if spec.family == family]
    return [spec for spec in specs if _is_available(profile, spec)]


def _is_available(profile: Any, spec: LensSpec) -> bool:
    if spec.required_roles:
        if "target" in spec.required_roles and not profile.target_profile:
            return False
        if "time" in spec.required_roles and not (profile.time or profile.time_candidate_list):
            return False
    if spec.compatible_semantic_types:
        if not any(
            column.semantic_type in spec.compatible_semantic_types
            for column in profile.column_profiles.values()
        ):
            return False
    if spec.compatible_targets and profile.target_profile:
        if profile.target_profile.task not in spec.compatible_targets:
            return False
    return True


register(
    LensSpec(
        id="quality.missingness",
        family="overview",
        title="Missingness profile",
        aliases=["missingness", "missingness.blocks", "quality.sparsity"],
        cost="cheap",
        evidence_sources=["quality", "statistical"],
        output_types=["metric_table", "visual"],
        visual_kinds=["missingness_bar"],
    )
)
register(
    LensSpec(
        id="quality.type_coercion",
        family="cleaning",
        title="Type coercion candidates",
        cost="cheap",
        evidence_sources=["quality", "cleaning"],
        output_types=["metric_table", "transform_candidates"],
    )
)
register(
    LensSpec(
        id="cleaning.transform_preview",
        family="cleaning",
        title="Preview cleaning transformations",
        aliases=["cleaning.preview", "transform_preview"],
        cost="cheap",
        evidence_sources=["quality", "cleaning"],
        output_types=["metric_table", "transform_plan"],
    )
)
register(
    LensSpec(
        id="footprint.optimize",
        family="performance",
        title="Optimize DataFrame memory footprint",
        aliases=["memory.optimize", "optimize_footprint", "footprint"],
        cost="low",
        evidence_sources=["performance", "statistical", "cleaning"],
        output_types=["metric_table", "transform_plan"],
    )
)
register(
    LensSpec(
        id="grain.keys",
        family="overview",
        title="Key and grain candidates",
        cost="cheap",
        evidence_sources=["semantic", "statistical"],
        output_types=["metric_table"],
    )
)
register(
    LensSpec(
        id="distribution.numeric",
        family="numeric",
        title="Numeric distribution",
        aliases=["numeric", "histogram"],
        compatible_semantic_types=["numeric", "amount", "numeric-like", "percentage", "proportion", "numeric_discrete"],
        cost="low",
        evidence_sources=["statistical", "visual"],
        output_types=["metric_table", "visual", "insights"],
        visual_kinds=["histogram", "quantiles"],
    )
)
register(
    LensSpec(
        id="concentration.lorenz",
        family="numeric",
        title="Concentration and Lorenz curve",
        aliases=["concentration.pareto", "lorenz"],
        compatible_semantic_types=["numeric", "amount", "numeric-like"],
        cost="low",
        evidence_sources=["statistical", "visual"],
        output_types=["metric_table", "visual"],
        visual_kinds=["lorenz_curve"],
    )
)
register(
    LensSpec(
        id="categorical.value_counts",
        family="categorical",
        title="Categorical value counts",
        aliases=["value_counts"],
        compatible_semantic_types=["category", "string", "postal_code", "geographic"],
        cost="cheap",
        evidence_sources=["statistical", "visual"],
        output_types=["metric_table", "visual"],
        visual_kinds=["top_k_bar"],
    )
)
register(
    LensSpec(
        id="binary.flags",
        family="cleaning",
        title="Binary flag mappings",
        aliases=["binary"],
        cost="cheap",
        evidence_sources=["quality", "cleaning", "statistical"],
        output_types=["metric_table", "transform_candidates", "visual"],
        visual_kinds=["binary_rate_bar"],
    )
)
register(
    LensSpec(
        id="time.cadence",
        family="time",
        title="Time cadence",
        aliases=["time.gaps", "time.records_over_time", "records_over_time"],
        compatible_semantic_types=["datetime", "datetime-like"],
        cost="low",
        evidence_sources=["time", "statistical", "visual"],
        output_types=["metric_table", "visual", "insights"],
        visual_kinds=["records_over_time"],
    )
)
register(
    LensSpec(
        id="target.candidates",
        family="target",
        title="Target candidates",
        required_roles=[],
        cost="cheap",
        evidence_sources=["semantic", "statistical", "target", "visual"],
        output_types=["metric_table", "visual"],
        visual_kinds=["candidate_bar"],
    )
)
register(
    LensSpec(
        id="target.balance",
        family="target",
        title="Target balance",
        required_roles=["target"],
        cost="cheap",
        evidence_sources=["target", "statistical", "visual"],
        output_types=["metric_table", "visual"],
        visual_kinds=["target_distribution"],
    )
)
register(
    LensSpec(
        id="target.associations",
        family="target",
        title="Feature associations with target",
        aliases=["associations"],
        required_roles=["target"],
        cost="medium",
        evidence_sources=["target", "relationship", "statistical", "visual"],
        output_types=["metric_table", "visual"],
        visual_kinds=["association_bar"],
    )
)
register(
    LensSpec(
        id="target.importance",
        family="target",
        title="What matters to this target?",
        required_roles=["target"],
        compatible_targets=["binary_classification", "multiclass_classification", "regression"],
        cost="medium",
        evidence_sources=["target", "model", "relationship", "visual"],
        output_types=["metric_table", "visual", "insights"],
        visual_kinds=["importance_bar"],
    )
)
register(
    LensSpec(
        id="relationships.correlation",
        family="relationships",
        title="Numeric correlation",
        aliases=["correlation"],
        compatible_semantic_types=["numeric", "amount", "numeric-like", "percentage", "proportion"],
        cost="medium",
        evidence_sources=["relationship", "statistical", "visual"],
        output_types=["matrix", "visual"],
        visual_kinds=["correlation_heatmap"],
    )
)
register(
    LensSpec(
        id="relationships.mixed_associations",
        family="relationships",
        title="Mixed association scan",
        aliases=["mixed_associations", "relationships.mixed"],
        compatible_semantic_types=["numeric", "amount", "numeric-like", "percentage", "proportion", "category", "string", "binary", "nullable_binary", "boolean"],
        cost="medium",
        evidence_sources=["relationship", "statistical", "visual"],
        output_types=["metric_table", "visual"],
        visual_kinds=["association_bar"],
    )
)
register(
    LensSpec(
        id="text.lengths",
        family="text",
        title="Text length profile",
        compatible_semantic_types=["text"],
        cost="low",
        evidence_sources=["statistical", "visual"],
        output_types=["metric_table", "visual"],
        visual_kinds=["text_length_histogram"],
    )
)
