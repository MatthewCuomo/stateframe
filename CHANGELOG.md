# Changelog

All notable changes to `stateframe` are tracked here.

This project follows semantic versioning while the API is stabilizing:

- Patch releases fix bugs without changing public behavior.
- Minor releases add features or improve diagnostics.
- Major releases are reserved for breaking API changes after `1.0.0`.

## 0.2.0 - Unreleased

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
- Added workspace-scoped file browsing helpers through `sf.workspace.list_files(...)`,
  `sf.workspace.file_info(...)`, and `sf.workspace.validate_save_path(...)`,
  plus initial `sf.web()` file-browser plumbing for scanning workspace data
  files into saved trees.
- Added the first pluggable query-source architecture with `sf.sources.register(...)`,
  `sf.sources.preview(...)`, `sf.sources.list_objects(...)`, `sf.query(...)`,
  and `sf.help_getdata()` for wiring company data systems into Get Data flows.
- Added synced viewer state helpers: `current_state()`, `selected_column()`, and
  `filtered_dataframe()`.
- Expanded the scan architecture with richer recommendation and lens plumbing.

## 0.1.0

- Bootstrapped the deterministic scan/profile engine.
- Added semantic type inference, issue generation, insights, recommendations,
  executable lenses, transform helpers, plotting helpers, and the CLI.
