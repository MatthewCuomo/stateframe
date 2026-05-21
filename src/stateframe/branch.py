"""User-code branch recording helpers.

This module is the notebook-facing bridge between ordinary Python work and the
stateframe ledger. It lets a user pull an input state, transform or analyze it in
their own code, and register the result as a first-class branch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from stateframe.models import Profile


DataFrameFactory = Callable[[], pd.DataFrame]


@dataclass
class BranchRecorder:
    """Record custom data, plot, report, or analysis outputs under a tree node."""

    profile: Profile
    parent_id: str | None
    source: Any = None
    autosave_tree: bool = True
    default_code: str | bool | None = None
    default_message: str | None = None
    default_note: str | None = None
    input_factory: DataFrameFactory | None = field(default=None, repr=False)

    def input(self) -> pd.DataFrame:
        """Return the DataFrame state this custom branch starts from."""

        if self.input_factory is not None:
            frame = self.input_factory()
        else:
            if self.parent_id is None:
                raise ValueError("This branch recorder has no parent ledger entry.")
            frame = self.profile.checkout(self.parent_id)
        return _attach_dataframe_context(frame, profile=self.profile, entry_id=self.parent_id)

    def __call__(self) -> pd.DataFrame:
        """Alias for ``input`` so ``df = sf.branch(web)()`` is possible."""

        return self.input()

    def save_data(
        self,
        data: Any,
        *,
        name: str | None = None,
        message: str | None = None,
        note: str | None = None,
        code: str | bool | None = None,
        title: str | None = None,
        operation: str = "custom.transform",
        input_variable: str = "df",
        output_variable: str = "output",
        replay: bool = True,
        autosave_tree: bool | None = None,
        copy_data: bool = True,
        **params: Any,
    ):
        """Record a user-created DataFrame as a replayable state branch.

        For metadata-only replay, write custom code using ``df`` as the input
        DataFrame and assign the resulting DataFrame to ``output``.
        """

        frame = _coerce_frame(data)
        output_name = _branch_name(name)
        final_message = message if message is not None else self.default_message
        final_note = note if note is not None else self.default_note or final_message or ""
        code_text = _resolve_code(code if code is not None else self.default_code)
        custom = {
            "kind": "python",
            "input_entry_id": self.parent_id,
            "input_variable": input_variable,
            "output_variable": output_variable,
            "output_name": output_name,
            "message": final_message,
            "replayable": bool(code_text and replay),
        }
        entry = self.profile.record_state(
            frame,
            title=title or f"Custom branch as {output_name}",
            operation=operation,
            parent_id=self.parent_id,
            copy_data=copy_data,
            code=code_text,
            note=final_note,
            output_name=output_name,
            message=final_message,
            custom=custom,
            **params,
        )
        self.parent_id = entry.id
        self._after_record(autosave_tree=autosave_tree)
        return entry

    def save_artifact(
        self,
        artifact: Any = None,
        *,
        name: str | None = None,
        kind: str = "artifact",
        message: str | None = None,
        note: str | None = None,
        code: str | bool | None = None,
        title: str | None = None,
        operation: str | None = None,
        input_variable: str = "df",
        output_variable: str = "artifact",
        replay: bool = True,
        autosave_tree: bool | None = None,
        **params: Any,
    ):
        """Record a user-created non-DataFrame output such as a plot or report."""

        output_name = _branch_name(name)
        clean_kind = _clean_kind(kind)
        final_message = message if message is not None else self.default_message
        final_note = note if note is not None else self.default_note or final_message or ""
        code_text = _resolve_code(code if code is not None else self.default_code)
        custom = {
            "kind": "python_artifact",
            "input_entry_id": self.parent_id,
            "input_variable": input_variable,
            "output_variable": output_variable,
            "output_name": output_name,
            "message": final_message,
            "replayable": bool(code_text and replay),
        }
        payload = _artifact_payload(
            artifact,
            kind=clean_kind,
            name=output_name,
        )
        entry = self.profile.record_artifact(
            title=title or f"Custom {clean_kind} as {output_name}",
            kind=clean_kind,
            operation=operation or f"custom.{clean_kind}",
            parent_id=self.parent_id,
            artifact=payload,
            code=code_text,
            note=final_note,
            summary={
                "artifact_kind": clean_kind,
                "output_name": output_name,
                "has_code": bool(code_text),
            },
            output_name=output_name,
            message=final_message,
            custom=custom,
            **params,
        )
        self.parent_id = entry.id
        self._after_record(autosave_tree=autosave_tree)
        return entry

    def save_plot(self, plot: Any = None, **kwargs: Any):
        """Record a plot branch."""

        return self.save_artifact(plot, kind="plot", operation="custom.plot", **kwargs)

    def save_report(self, report: Any = None, **kwargs: Any):
        """Record a report branch."""

        return self.save_artifact(report, kind="report", operation="custom.report", **kwargs)

    def save(self, output: Any, **kwargs: Any):
        """Save DataFrames as states and other objects as artifacts."""

        if isinstance(output, pd.DataFrame) or hasattr(output, "to_pandas"):
            return self.save_data(output, **kwargs)
        return self.save_artifact(output, **kwargs)

    def save_tree(self):
        """Persist the backing tree metadata now."""

        return self.profile.save_tree()

    def _after_record(self, *, autosave_tree: bool | None) -> None:
        should_save = self.autosave_tree if autosave_tree is None else bool(autosave_tree)
        if should_save:
            self.profile.save_tree()
        if hasattr(self.source, "refresh"):
            self.source.refresh()


def branch(
    source: Any,
    *,
    parent_id: str | None = None,
    code: str | bool | None = None,
    message: str | None = None,
    note: str | None = None,
    autosave_tree: bool = True,
) -> BranchRecorder:
    """Create a recorder for adding custom notebook work to a stateframe tree.

    ``source`` can be a ``Profile`` returned by ``sf.scan(...)``, a workspace
    web widget, a dataframe viewer, or a DataFrame previously pulled from
    stateframe with attached context.
    """

    profile, resolved_parent, input_factory = _resolve_profile_and_parent(source, parent_id)
    return BranchRecorder(
        profile=profile,
        parent_id=resolved_parent,
        source=source,
        autosave_tree=autosave_tree,
        default_code=code,
        default_message=message,
        default_note=note,
        input_factory=input_factory,
    )


def _resolve_profile_and_parent(
    source: Any,
    parent_id: str | None,
) -> tuple[Profile, str | None, DataFrameFactory | None]:
    if isinstance(source, Profile):
        if source.ledger is None:
            from stateframe.ledger import LensLedger

            source.ledger = LensLedger.start(source)
        return source, parent_id or source.ledger.active_entry_id, None

    if hasattr(source, "selected_profile") and hasattr(source, "selected_entry_id"):
        profile = source.selected_profile()
        selected = parent_id or source.selected_entry_id()
        return profile, selected, None

    if hasattr(source, "record_profile") and isinstance(source.record_profile, Profile):
        profile = source.record_profile
        selected = parent_id or getattr(source, "ledger_parent_id", None)
        if selected is None and profile.ledger is not None:
            selected = profile.ledger.active_entry_id

        def factory() -> pd.DataFrame:
            return source.pull(record=False)

        return profile, selected, factory

    if isinstance(source, pd.DataFrame):
        context = source.attrs.get("_stateframe")
        if isinstance(context, dict):
            return _profile_from_dataframe_context(source, context, parent_id)

    raise TypeError(
        "sf.branch(...) expects a stateframe Profile, web widget, dataframe "
        "viewer, or DataFrame pulled from stateframe with context."
    )


def _profile_from_dataframe_context(
    frame: pd.DataFrame,
    context: dict[str, Any],
    parent_id: str | None,
) -> tuple[Profile, str | None, DataFrameFactory | None]:
    from stateframe import workspace
    from stateframe.interactive.web import _ledger_from_saved_payload, _saved_profile_payload
    from stateframe.profile import build_profile

    root = context.get("workspace_root")
    if root:
        workspace.connect(root=root, name=context.get("workspace_name"))
    current_workspace = workspace.current()
    tree_id = str(context.get("tree_id") or "")
    if not tree_id:
        raise ValueError("The DataFrame context does not include a stateframe tree id.")
    selected = parent_id or context.get("entry_id")
    tree_payload = current_workspace.load_tree(tree_id)
    profile_payload = _saved_profile_payload(tree_payload)
    profile = build_profile(
        frame,
        name=profile_payload.get("dataset_name") or profile_payload.get("tree_name"),
        target=_valid_column(profile_payload.get("target"), frame),
        time=_valid_column(profile_payload.get("time"), frame),
        goal=profile_payload.get("goal") or "first-look",
        mode=profile_payload.get("mode") or "standard",
        register=False,
    )
    profile.dataset_name = profile_payload.get("dataset_name")
    profile.tree_name = profile_payload.get("tree_name")
    profile.source = dict(profile_payload.get("source") or {})
    profile.profile_id = profile_payload.get("profile_id") or profile.profile_id
    profile.workspace_summary = tree_payload.get("summary") or {}
    profile.workspace_source_fingerprint = tree_payload.get("source_fingerprint")
    profile.ledger = _ledger_from_saved_payload(
        tree_payload,
        selected_entry_id=str(selected) if selected else None,
        selected_state_id=context.get("state_id"),
        selected_data=frame,
    )
    profile.tree_id = tree_id

    def factory() -> pd.DataFrame:
        return frame.copy()

    return profile, str(selected) if selected else None, factory


def _attach_dataframe_context(
    frame: pd.DataFrame,
    *,
    profile: Profile,
    entry_id: str | None,
) -> pd.DataFrame:
    if entry_id is None:
        return frame
    context: dict[str, Any] = {
        "tree_id": getattr(profile, "tree_id", None),
        "tree_name": getattr(profile, "tree_name", None),
        "dataset_name": getattr(profile, "dataset_name", None),
        "entry_id": entry_id,
        "workspace_root": None,
        "workspace_name": None,
    }
    if profile.ledger is not None:
        try:
            entry = profile.ledger.get(entry_id)
            context["state_id"] = entry.state_id
        except Exception:
            pass
    try:
        from stateframe import workspace

        current_workspace = workspace.current()
        context["workspace_root"] = str(current_workspace.root)
        context["workspace_name"] = current_workspace.name
    except Exception:
        pass
    frame.attrs["_stateframe"] = {key: value for key, value in context.items() if value}
    return frame


def _coerce_frame(data: Any) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data
    if hasattr(data, "to_pandas"):
        result = data.to_pandas()
        if isinstance(result, pd.DataFrame):
            return result
    raise TypeError("Custom data branches must save a pandas DataFrame-like object.")


def _resolve_code(code: str | bool | None) -> str:
    if code is True:
        return _capture_current_cell()
    if not code:
        return ""
    return str(code).strip()


def _capture_current_cell() -> str:
    try:
        from IPython import get_ipython

        shell = get_ipython()
        history = getattr(getattr(shell, "history_manager", None), "input_hist_raw", None)
        if history:
            return str(history[-1]).strip()
    except Exception:
        return ""
    return ""


def _artifact_payload(artifact: Any, *, kind: str, name: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": kind,
        "name": name,
    }
    if artifact is None:
        return payload
    if isinstance(artifact, dict):
        return _json_safe({**payload, **artifact})
    if isinstance(artifact, (str, Path)):
        payload["path"] = str(artifact)
        return payload
    if hasattr(artifact, "to_plotly_json"):
        from stateframe.artifacts import plotly_figure_payload

        return _json_safe(plotly_figure_payload(artifact, kind=kind, name=name))
    if hasattr(artifact, "to_dict"):
        try:
            value = artifact.to_dict(include_figure=False)
        except TypeError:
            value = artifact.to_dict()
        except Exception:
            value = None
        if isinstance(value, dict):
            payload["metadata"] = value
            payload["object_type"] = _object_type(artifact)
            return _json_safe(payload)
    payload["object_type"] = _object_type(artifact)
    payload["repr"] = repr(artifact)[:500]
    return _json_safe(payload)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, Path):
        return str(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _object_type(value: Any) -> str:
    cls = value.__class__
    return f"{cls.__module__}.{cls.__name__}"


def _valid_column(column: Any, data: pd.DataFrame) -> str | None:
    return str(column) if column in data.columns else None


def _branch_name(name: str | None) -> str:
    text = str(name or "custom_branch").strip()
    return text or "custom_branch"


def _clean_kind(kind: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(kind or "artifact").strip())
    text = text.strip("._-")
    return text or "artifact"
