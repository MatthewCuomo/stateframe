"""Public API for stateframe."""

from stateframe import save as save
from stateframe import workspace as workspace
from stateframe.api import (
    apply_suggested_conversions,
    branch,
    connect_web,
    ledger_view,
    optimize_footprint,
    plot,
    profile,
    report,
    scan,
    scan_path,
    tree_view,
    unify_binary_flags,
    view,
    web,
    web_payload,
)
from stateframe.cleaning import CleaningPlan, TransformAction
from stateframe.branch import BranchRecorder
from stateframe.config import ScanConfig, SuggestedConfig
from stateframe.footprint import FootprintAction, FootprintPlan
from stateframe.help import help
from stateframe.ledger import LedgerEntry, LedgerState, LensLedger
from stateframe.lens_registry import LensSpec, all_lenses, get_lens_spec
from stateframe.models import (
    BinaryProfile,
    ColumnProfile,
    DatasetSummary,
    EvidenceFact,
    Insight,
    Issue,
    LensResult,
    PlotResult,
    Profile,
    Recommendation,
    RecommendationList,
    ShapeHypothesis,
    TargetCandidate,
    TargetProfile,
    TaskInference,
    TimeCandidate,
    ValueProfile,
)

__all__ = [
    "BinaryProfile",
    "BranchRecorder",
    "CleaningPlan",
    "ColumnProfile",
    "DatasetSummary",
    "EvidenceFact",
    "FootprintAction",
    "FootprintPlan",
    "Insight",
    "Issue",
    "LedgerEntry",
    "LedgerState",
    "LensResult",
    "LensLedger",
    "LensSpec",
    "PlotResult",
    "Profile",
    "Recommendation",
    "RecommendationList",
    "ScanConfig",
    "ShapeHypothesis",
    "SuggestedConfig",
    "TargetCandidate",
    "TargetProfile",
    "TaskInference",
    "TimeCandidate",
    "TransformAction",
    "ValueProfile",
    "apply_suggested_conversions",
    "branch",
    "connect_web",
    "all_lenses",
    "get_lens_spec",
    "help",
    "ledger_view",
    "optimize_footprint",
    "plot",
    "profile",
    "report",
    "scan",
    "scan_path",
    "save",
    "tree_view",
    "unify_binary_flags",
    "view",
    "web",
    "web_payload",
    "workspace",
]

__version__ = "0.2.0"
