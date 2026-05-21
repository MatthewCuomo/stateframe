# Changelog

All notable changes to `stateframe` are tracked here.

This project follows semantic versioning while the API is stabilizing:

- Patch releases fix bugs without changing public behavior.
- Minor releases add features or improve diagnostics.
- Major releases are reserved for breaking API changes after `1.0.0`.

## 0.2.1 - 2026-05-21

- Added workspace-scoped file browsing helpers through `sf.workspace.list_files(...)`,
  `sf.workspace.file_info(...)`, and `sf.workspace.validate_save_path(...)`,
  plus `sf.web()` file-browser plumbing for scanning workspace data files into
  saved trees.
- Added the first pluggable query-source architecture with `sf.sources.register(...)`,
  `sf.sources.preview(...)`, `sf.sources.list_objects(...)`, `sf.query(...)`,
  and `sf.help_getdata()` for wiring external data systems into Get Data flows.
- Added persisted query connection profiles through `sf.sources.save_connection(...)`
  and the web **Get Data -> Query Data / Connections** flow. Saved connections
  auto-import repo-local provider files such as `company_query_source.py:register`
  so future `sf.web()` and `sf.query(...)` calls can use them without manual
  notebook imports.
- Added artifact leaves for plots and custom output, including
  `Profile.record_plot_leaf(...)`, embedded web viewer lineage/draft summaries,
  and UI actions for saving plot leaves under selected data branches.
- Added code leaves through `sf.leaf(...)` and the optional `%%sf_leaf` IPython
  cell magic, including terminal/dataframe/figure/Plotly capture and optional
  durable output saves under `stateframe_saves/`.
- Added unified pull references through `sf.pull()` and `sf.pull("entry_id")`
  so selected UI items, saved dataframe states, and output leaves can be pulled
  or rendered from one notebook call. The web UI now surfaces copyable pull code
  for each branch and leaf.
- Added the first Plotly visualizer subsystem with declarative visual specs,
  a web visualizer mode, plot library, field bindings, filters, grouped
  collapsible options, render previews, and saved visual leaves under the
  selected dataframe state.
- Improved the web tree with tree-ordered plot placement, static plot thumbnails,
  collapsible branch sections, tree guide lines, resizable panels, rendered leaf
  notes, and output-leaf detail views.
- Marked older standalone viewer/tree assets as `_decom`; compatibility Python
  entry points now mount `workspace_web.js` directly.
- Improved widget text-input handling so search boxes preserve focus/caret
  through synced-state redraws.

## 0.2.0 - 2026-05-18

- Added the interactive dataframe explorer behind the `interactive` extra.
- Added `sf.view(...)` and `Profile.view()`.
- Added the standalone ledger tree widget through `sf.ledger_view(...)`,
  `sf.tree_view(...)`, `Profile.ledger_view()`, and `Profile.tree_view()`.
- Viewer-shaped DataFrames returned through `viewer.pull(...)` now create
  ledger checkpoints by default, and `viewer.save_current_view(...)` creates
  explicit named branch points from UI filters, sorting, hidden columns, and
  column ordering. `viewer.filtered_dataframe()` remains as a compatibility
  alias.
- Added the first durable save layer with `sf.save.configure(...)`,
  `sf.save.tree(...)`, `sf.save.data(...)`, `scan.save_tree()`, and
  `scan.save_data()` for metadata trees and Parquet state checkpoints.
- Added the workspace web foundation with `sf.workspace.configure(...)`,
  `sf.workspace.list_trees()`, `sf.web()`, per-tree metadata files, editable
  tree names, and stable tree ids.
- Added synced viewer state helpers: `current_state()`, `selected_column()`, and
  `filtered_dataframe()`.
- Expanded the scan architecture with richer recommendation and lens plumbing.

## 0.1.0

- Bootstrapped the deterministic scan/profile engine.
- Added semantic type inference, issue generation, insights, recommendations,
  executable lenses, transform helpers, plotting helpers, and the CLI.
