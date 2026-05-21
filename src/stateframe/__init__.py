"""Public API for stateframe."""

from stateframe import save as save
from stateframe import files as files
from stateframe import sources as sources
from stateframe import workspace as workspace
from stateframe.api import (
    apply_suggested_conversions,
    branch,
    connect_web,
    is_save_mode,
    ledger_view,
    leaf,
    optimize_footprint,
    plot,
    profile,
    pull,
    query,
    report,
    register_ipython_magics,
    scan,
    scan_path,
    save_mode,
    tree_view,
    unify_binary_flags,
    view,
    visual_artifact,
    visual_catalog,
    visualize,
    web,
    web_payload,
)
from stateframe.cleaning import CleaningPlan, TransformAction
from stateframe.branch import BranchRecorder
from stateframe.config import ScanConfig, SuggestedConfig
from stateframe.footprint import FootprintAction, FootprintPlan
from stateframe.help import help
from stateframe.help import help_getdata
from stateframe.help import help_tree
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
from stateframe.sources import (
    DataObject,
    DataSource,
    DataSourceError,
    FunctionDataSource,
    QueryResult,
)

__all__ = [
    "BinaryProfile",
    "BranchRecorder",
    "CleaningPlan",
    "ColumnProfile",
    "DatasetSummary",
    "DataObject",
    "DataSource",
    "DataSourceError",
    "EvidenceFact",
    "FootprintAction",
    "FootprintPlan",
    "FunctionDataSource",
    "Insight",
    "Issue",
    "LedgerEntry",
    "LedgerState",
    "LensResult",
    "LensLedger",
    "LensSpec",
    "PlotResult",
    "Profile",
    "QueryResult",
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
    "is_save_mode",
    "all_lenses",
    "get_lens_spec",
    "help",
    "help_getdata",
    "help_tree",
    "ledger_view",
    "leaf",
    "optimize_footprint",
    "plot",
    "profile",
    "pull",
    "query",
    "register_ipython_magics",
    "report",
    "scan",
    "scan_path",
    "save",
    "save_mode",
    "files",
    "sources",
    "tree_view",
    "unify_binary_flags",
    "view",
    "visual_artifact",
    "visual_catalog",
    "visualize",
    "web",
    "web_payload",
    "workspace",
]

__version__ = "0.2.0"


def load_ipython_extension(ipython):
    """Register stateframe notebook magics such as ``%%sf_leaf``."""

    register_ipython_magics(ipython)
