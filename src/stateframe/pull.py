"""Pull dataframe states and output leaves back into notebook code."""

from __future__ import annotations

import html as html_lib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


class PullReferenceError(KeyError):
    """Raised when a pull reference cannot be resolved uniquely."""


_ACTIVE_WEB_VIEWER: Any | None = None
_RECENT_PULL_CONTEXTS: list[dict[str, Any]] = []


def set_active_web_viewer(viewer: Any) -> None:
    """Remember the most recently created web/viewer widget for ``sf.pull()``."""

    global _ACTIVE_WEB_VIEWER
    _ACTIVE_WEB_VIEWER = viewer


def active_web_viewer() -> Any | None:
    """Return the current active stateframe web widget, if one is known."""

    return _ACTIVE_WEB_VIEWER


def recent_pull_contexts(*, clear: bool = False) -> list[dict[str, Any]]:
    """Return dataframe contexts captured from recent ``sf.pull(...)`` calls."""

    contexts = list(_RECENT_PULL_CONTEXTS)
    if clear:
        clear_pull_contexts()
    return contexts


def clear_pull_contexts() -> None:
    """Forget recent pull contexts used by convenience helpers such as ``sf.push``."""

    _RECENT_PULL_CONTEXTS.clear()


def pull(
    reference: str | None = None,
    *,
    tree: str | None = None,
    web: Any | None = None,
) -> Any:
    """Pull a dataframe state or output leaf by id, or from the active UI.

    ``sf.pull()`` uses the selected item in the active stateframe widget.
    ``sf.pull("entry_id")`` resolves a saved workspace entry by its stable
    ledger id and returns a DataFrame for data states or a renderable
    ``PulledOutput`` for plot/code/report leaves.
    """

    viewer = web or active_web_viewer()
    if reference is None:
        if viewer is None:
            raise PullReferenceError("No active stateframe web widget is available for sf.pull().")
        return _remember_pull_result(pull_from_web(viewer), reference="sf.pull()")

    if viewer is not None:
        try:
            return _remember_pull_result(
                pull_from_web(viewer, reference),
                reference=str(reference),
            )
        except PullReferenceError:
            pass
    return _remember_pull_result(
        pull_from_workspace(reference, tree=tree),
        reference=str(reference),
    )


def pull_from_web(viewer: Any, reference: str | None = None) -> Any:
    """Pull from a live ``WorkspaceWebViewer`` instance."""

    if reference is None:
        mode = (getattr(viewer, "state", {}) or {}).get("viewMode")
        visualizer = getattr(viewer, "visualizer", {}) or {}
        if mode == "visualizer" and visualizer.get("preview"):
            preview = dict(visualizer["preview"])
            entry = {
                "id": "visualizer_preview",
                "kind": preview.get("kind") or "plot",
                "title": preview.get("title") or "Visualizer preview",
                "operation": preview.get("plot_id") or preview.get("visual_kind") or "visual.preview",
                "artifacts": [preview],
            }
            return PulledOutput(entry=entry, artifacts=[preview], reference_code="sf.pull()")
        entry = viewer.selected_entry_record()
        if entry is None:
            raise PullReferenceError("No stateframe tree entry is selected.")
        if _entry_output_artifacts(entry):
            return _pulled_output(entry, _selected_tree_record(viewer), reference_code="sf.pull()")
        if mode == "viewer" and hasattr(viewer, "viewer_dataframe"):
            return viewer.viewer_dataframe()
        return viewer.pull_selected()

    tree_record, entry = _resolve_reference_in_web(viewer, reference)
    if _entry_output_artifacts(entry):
        return _pulled_output(entry, tree_record, reference_code=pull_code(entry["id"]))

    single_profile = getattr(viewer, "_single_profile", None)
    if single_profile is not None:
        frame = single_profile.checkout(str(entry["id"]))
        frame.attrs["_stateframe"] = {
            "tree_id": getattr(single_profile, "tree_id", None),
            "tree_name": getattr(single_profile, "tree_name", None),
            "entry_id": entry.get("id"),
            "state_id": entry.get("state_id"),
        }
        return frame
    return pull_from_workspace(reference, tree=str(tree_record.get("tree_id") or ""))


def pull_from_workspace(reference: str, *, tree: str | None = None) -> Any:
    """Pull a saved workspace entry by id, state id, or unique title."""

    from stateframe import workspace

    current_workspace = workspace.current()
    tree_record, tree_payload, entry = _resolve_reference_in_workspace(
        str(reference),
        workspace=current_workspace,
        tree=tree,
    )
    if _entry_output_artifacts(entry):
        return _pulled_output(
            entry,
            tree_record,
            tree_payload=tree_payload,
            workspace_root=current_workspace.root,
            reference_code=pull_code(entry["id"]),
        )
    return _pull_dataframe_entry(
        tree_payload,
        tree_record=tree_record,
        entry=entry,
        workspace=current_workspace,
    )


def pull_code(reference: str) -> str:
    """Return the notebook code used to pull a stable stateframe reference."""

    return f"sf.pull({reference!r})"


@dataclass
class PulledOutput:
    """Renderable notebook object returned for plot/report/code leaves."""

    entry: dict[str, Any]
    artifacts: list[dict[str, Any]]
    tree: dict[str, Any] | None = None
    tree_payload: dict[str, Any] | None = None
    workspace_root: Path | None = None
    reference_code: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def artifact(self) -> dict[str, Any] | None:
        return self.artifacts[0] if self.artifacts else None

    @property
    def id(self) -> str:
        return str(self.entry.get("id") or "")

    @property
    def title(self) -> str:
        return str(self.entry.get("title") or self.entry.get("operation") or self.id)

    def show(self) -> "PulledOutput":
        """Display this output explicitly and return it."""

        try:
            from IPython.display import display

            display(self)
        except Exception:
            print(repr(self))
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry": dict(self.entry),
            "artifacts": list(self.artifacts),
            "tree": dict(self.tree or {}),
            "reference_code": self.reference_code,
        }

    def _repr_html_(self) -> str:
        title = html_lib.escape(self.title)
        meta = html_lib.escape(" / ".join(
            item for item in [
                str(self.entry.get("kind") or "output"),
                str(self.entry.get("operation") or ""),
                self.id,
            ]
            if item
        ))
        code = html_lib.escape(self.reference_code or pull_code(self.id))
        parts = [
            '<div style="display:grid;gap:10px;max-width:100%;font-family:ui-sans-serif,system-ui,sans-serif;">',
            '<div style="display:grid;gap:4px;border-left:3px solid #2563eb;padding-left:10px;">',
            f'<div style="font-weight:750;color:#111827;">{title}</div>',
            f'<div style="font-size:12px;color:#64748b;">{meta}</div>',
            f'<code style="font-size:12px;background:#f8fafc;border:1px solid #e5e7eb;border-radius:4px;padding:3px 6px;width:max-content;max-width:100%;overflow-wrap:anywhere;">{code}</code>',
            "</div>",
        ]
        for artifact in self.artifacts:
            parts.append(_artifact_html(artifact, workspace_root=self.workspace_root))
        parts.append("</div>")
        return "".join(parts)

    def __repr__(self) -> str:
        return f"PulledOutput(id={self.id!r}, title={self.title!r}, code={self.reference_code or pull_code(self.id)!r})"


def _selected_tree_record(viewer: Any) -> dict[str, Any] | None:
    if hasattr(viewer, "selected_tree_record"):
        return viewer.selected_tree_record()
    selected_tree_id = (getattr(viewer, "state", {}) or {}).get("selectedTreeId")
    for tree in (getattr(viewer, "payload", {}) or {}).get("trees", []) or []:
        if tree.get("tree_id") == selected_tree_id:
            return dict(tree)
    return None


def _resolve_reference_in_web(viewer: Any, reference: str) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = getattr(viewer, "payload", {}) or {}
    matches: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
    for tree_record in payload.get("trees", []) or []:
        entries = ((tree_record.get("tree_detail") or {}).get("entries") or [])
        for entry in entries:
            score = _entry_match_score(entry, reference)
            if score:
                matches.append((score, dict(tree_record), dict(entry)))
    if not matches:
        raise PullReferenceError(f"Unknown stateframe pull reference: {reference}")
    best_score = min(score for score, _, _ in matches)
    best = [(tree, entry) for score, tree, entry in matches if score == best_score]
    if len(best) > 1:
        ids = ", ".join(str(entry.get("id")) for _, entry in best)
        raise PullReferenceError(f"Ambiguous stateframe pull reference {reference!r}. Use one of: {ids}")
    return best[0]


def _resolve_reference_in_workspace(
    reference: str,
    *,
    workspace: Any,
    tree: str | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    records = [workspace.resolve_tree(tree)] if tree else list(workspace.list_trees())
    matches: list[tuple[int, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for tree_record in records:
        try:
            tree_payload = workspace.load_tree(str(tree_record.get("tree_id") or tree_record.get("tree_name")))
        except Exception:
            continue
        ledger = _saved_ledger_payload(tree_payload)
        for entry in ledger.get("entries", []) or []:
            score = _entry_match_score(entry, reference)
            if score:
                matches.append((score, dict(tree_record), tree_payload, dict(entry)))
    if not matches:
        raise PullReferenceError(f"Unknown stateframe pull reference: {reference}")
    best_score = min(score for score, _, _, _ in matches)
    best = [(tree_record, tree_payload, entry) for score, tree_record, tree_payload, entry in matches if score == best_score]
    if len(best) > 1:
        ids = ", ".join(str(entry.get("id")) for _, _, entry in best)
        raise PullReferenceError(f"Ambiguous stateframe pull reference {reference!r}. Use one of: {ids}")
    return best[0]


def _entry_match_score(entry: dict[str, Any], reference: str) -> int | None:
    ref = str(reference)
    if ref == str(entry.get("id")):
        return 1
    if ref == str(entry.get("state_id")):
        return 2
    if ref == str(entry.get("title")):
        return 3
    return None


def _pull_dataframe_entry(
    tree_payload: dict[str, Any],
    *,
    tree_record: dict[str, Any],
    entry: dict[str, Any],
    workspace: Any,
) -> pd.DataFrame:
    state = (_saved_ledger_payload(tree_payload).get("states") or {}).get(entry.get("state_id") or "")
    snapshot = _data_snapshot_artifact(entry)
    if snapshot is not None:
        from stateframe.save import load_data

        frame = load_data(_artifact_path(workspace.root, snapshot))
    elif isinstance(state, dict) and isinstance(state.get("data"), list):
        frame = pd.DataFrame(state["data"])
    else:
        from stateframe.replay import replay_tree_state

        frame = replay_tree_state(tree_payload, workspace=workspace, entry_id=str(entry.get("id") or ""))
    frame.attrs["_stateframe"] = {
        "tree_id": tree_record.get("tree_id") or tree_payload.get("tree_id"),
        "tree_name": tree_record.get("tree_name") or tree_payload.get("tree_name"),
        "entry_id": entry.get("id"),
        "state_id": entry.get("state_id"),
    }
    return frame


def _pulled_output(
    entry: dict[str, Any],
    tree: dict[str, Any] | None,
    *,
    tree_payload: dict[str, Any] | None = None,
    workspace_root: Path | None = None,
    reference_code: str = "",
) -> PulledOutput:
    return PulledOutput(
        entry=dict(entry),
        artifacts=_entry_output_artifacts(entry),
        tree=dict(tree or {}),
        tree_payload=tree_payload,
        workspace_root=workspace_root,
        reference_code=reference_code or pull_code(str(entry.get("id") or "")),
    )


def _entry_output_artifacts(entry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(artifact)
        for artifact in entry.get("artifacts", []) or []
        if isinstance(artifact, dict) and artifact.get("kind") != "data_snapshot"
    ]


def _data_snapshot_artifact(entry: dict[str, Any]) -> dict[str, Any] | None:
    artifacts = [
        artifact
        for artifact in entry.get("artifacts", []) or []
        if isinstance(artifact, dict)
        and artifact.get("kind") == "data_snapshot"
        and artifact.get("format") == "parquet"
        and artifact.get("path")
    ]
    return dict(artifacts[-1]) if artifacts else None


def _saved_ledger_payload(tree_payload: dict[str, Any]) -> dict[str, Any]:
    from stateframe.replay import saved_ledger_payload

    return saved_ledger_payload(tree_payload)


def _artifact_path(root: Path, artifact: dict[str, Any]) -> Path:
    path = Path(str(artifact.get("path") or ""))
    return path if path.is_absolute() else root / path


def _artifact_html(artifact: dict[str, Any], *, workspace_root: Path | None) -> str:
    title = html_lib.escape(str(artifact.get("title") or artifact.get("name") or artifact.get("kind") or "Output"))
    body = ""
    if artifact.get("kind") == "code_leaf":
        body = _code_leaf_html(artifact, workspace_root=workspace_root)
    else:
        body = _plot_or_artifact_html(artifact, workspace_root=workspace_root)
    return (
        '<section style="display:grid;gap:8px;border:1px solid #e5e7eb;border-radius:6px;padding:10px;background:#fff;">'
        f'<div style="font-size:13px;font-weight:750;color:#111827;">{title}</div>'
        f"{body}"
        "</section>"
    )


def _code_leaf_html(artifact: dict[str, Any], *, workspace_root: Path | None) -> str:
    parts = []
    for preview in artifact.get("previews", []) or []:
        if not isinstance(preview, dict):
            continue
        parts.append(_preview_html(preview, workspace_root=workspace_root))
    if artifact.get("code"):
        parts.append(
            "<details><summary style=\"cursor:pointer;color:#64748b;font-size:12px;font-weight:700;\">Code</summary>"
            f"<pre style=\"overflow:auto;background:#0f172a;color:#e2e8f0;border-radius:6px;padding:10px;\">{html_lib.escape(str(artifact['code']))}</pre>"
            "</details>"
        )
    return "".join(parts) or _json_html(artifact)


def _preview_html(preview: dict[str, Any], *, workspace_root: Path | None) -> str:
    kind = preview.get("kind")
    name = html_lib.escape(str(preview.get("name") or kind or "Preview"))
    if kind == "terminal":
        text = "\n".join(part for part in [preview.get("stdout") or "", preview.get("stderr") or ""] if part)
        if not text and preview.get("path"):
            text = _read_text_path(preview.get("path"), workspace_root=workspace_root)
        return f"<div><div style=\"font-size:12px;font-weight:700;color:#334155;\">{name}</div><pre style=\"overflow:auto;background:#0f172a;color:#e2e8f0;border-radius:6px;padding:10px;\">{html_lib.escape(text)}</pre></div>"
    if kind in {"plotly", "html"}:
        html = str(preview.get("html") or _read_text_path(preview.get("html_path"), workspace_root=workspace_root) or "")
        if html:
            return _iframe_html(html, title=name)
    if kind in {"image", "matplotlib", "plotly"} and preview.get("preview_data_url"):
        return _image_html(str(preview["preview_data_url"]), alt=name)
    if kind == "dataframe":
        return _dataframe_preview_html(preview)
    if "repr" in preview:
        return f"<pre style=\"overflow:auto;background:#f8fafc;border:1px solid #e5e7eb;border-radius:6px;padding:8px;\">{html_lib.escape(str(preview.get('repr')))}</pre>"
    return _json_html(preview)


def _plot_or_artifact_html(artifact: dict[str, Any], *, workspace_root: Path | None) -> str:
    html = str(artifact.get("html") or _read_text_path(artifact.get("html_path"), workspace_root=workspace_root) or "")
    if not html and artifact.get("plotly_json") is not None:
        html = _plotly_json_html(artifact.get("plotly_json"))
    if html:
        return _iframe_html(html, title=str(artifact.get("title") or "Plot"))
    if artifact.get("preview_data_url"):
        return _image_html(str(artifact["preview_data_url"]), alt=str(artifact.get("title") or "Output"))
    if artifact.get("path"):
        text = _read_text_path(artifact.get("path"), workspace_root=workspace_root)
        if text:
            return f"<pre style=\"overflow:auto;background:#f8fafc;border:1px solid #e5e7eb;border-radius:6px;padding:8px;\">{html_lib.escape(text)}</pre>"
    return _json_html(artifact)


def _plotly_json_html(value: Any) -> str:
    try:
        import plotly.io as pio

        figure = pio.from_json(json.dumps(value))
        return figure.to_html(full_html=False, include_plotlyjs="cdn", config={"responsive": True, "displaylogo": False})
    except Exception:
        return ""


def _iframe_html(value: str, *, title: str) -> str:
    srcdoc = html_lib.escape(value, quote=True)
    safe_title = html_lib.escape(title, quote=True)
    return (
        f'<iframe title="{safe_title}" sandbox="allow-scripts allow-same-origin" srcdoc="{srcdoc}" '
        'style="width:100%;min-height:620px;border:1px solid #eef2f7;border-radius:6px;background:#fff;"></iframe>'
    )


def _image_html(data_url: str, *, alt: str) -> str:
    return (
        f'<img src="{html_lib.escape(data_url, quote=True)}" alt="{html_lib.escape(alt, quote=True)}" '
        'style="display:block;width:100%;max-height:620px;object-fit:contain;border:1px solid #eef2f7;border-radius:6px;background:#fff;" />'
    )


def _dataframe_preview_html(preview: dict[str, Any]) -> str:
    columns = [str(column) for column in preview.get("columns", []) or []]
    rows = preview.get("rows", []) or []
    if not columns or not rows:
        return _json_html(preview)
    header = "".join(f"<th>{html_lib.escape(column)}</th>" for column in columns)
    body_rows = []
    for row in rows[:20]:
        cells = "".join(f"<td>{html_lib.escape(str(row.get(column, '')))}</td>" for column in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    return (
        '<div style="overflow:auto;"><table style="border-collapse:collapse;font-size:12px;">'
        f"<thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody></table></div>"
    )


def _json_html(value: Any) -> str:
    text = json.dumps(value, indent=2, default=str)
    return f"<pre style=\"overflow:auto;background:#f8fafc;border:1px solid #e5e7eb;border-radius:6px;padding:8px;\">{html_lib.escape(text)}</pre>"


def _read_text_path(path: Any, *, workspace_root: Path | None) -> str:
    if not path:
        return ""
    try:
        candidate = Path(str(path))
        if not candidate.is_absolute() and workspace_root is not None:
            candidate = workspace_root / candidate
        if candidate.exists() and candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    except Exception:
        return ""
    return ""


def _remember_pull_result(value: Any, *, reference: str | None) -> Any:
    if isinstance(value, pd.DataFrame):
        context = value.attrs.get("_stateframe")
        if isinstance(context, dict):
            _RECENT_PULL_CONTEXTS.append(
                {
                    **dict(context),
                    "reference": reference,
                    "_frame": value,
                }
            )
            del _RECENT_PULL_CONTEXTS[:-20]
    return value


__all__ = [
    "PullReferenceError",
    "PulledOutput",
    "active_web_viewer",
    "clear_pull_contexts",
    "pull",
    "pull_code",
    "pull_from_web",
    "pull_from_workspace",
    "recent_pull_contexts",
    "set_active_web_viewer",
]
