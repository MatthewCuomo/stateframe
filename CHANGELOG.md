# Changelog

All notable changes to `stateframe` are tracked here.

This project follows semantic versioning while the API is stabilizing:

- Patch releases fix bugs without changing public behavior.
- Minor releases add features or improve diagnostics.
- Major releases are reserved for breaking API changes after `1.0.0`.

## Unreleased

## 0.3.0 - 2026-05-27

- Added the first shared operation registry for UI- and replay-readable
  cleansing controls. Cleaning plan actions now expose operation ids, control
  metadata, affected row counts, examples, risk, default-apply behavior, and a
  cleaning operation catalog.
- Expanded cleaning previews with ambiguous binary flag review, richer binary
  null policies, mixed-format datetime parsing, category variant review,
  true-null treatment, duplicate-row review, numeric outlier
  review/treatment, and latitude/longitude anomaly review.
- Added modeling-prep transform helpers: `sf.map_values(...)`,
  `sf.impute_missing(...)`, `sf.add_missing_indicators(...)`,
  `sf.one_hot_encode(...)`, `sf.scale_numeric(...)`,
  `sf.add_date_features(...)`, `sf.add_ratio(...)`, and
  `sf.clean_numeric_outliers(...)`.
- Added public column-name helpers with `sf.clean_column_names(...)`,
  `sf.rename_columns(...)`, and `sf.clean_column_name(...)` for mass
  snake-case/compact renaming, manual selected-column renames, punctuation
  cleanup, case conversion, digit-prefixing, and duplicate-safe names.
- Added previewable modeling-readiness plans through `scan.modeling_plan()`,
  `sf.modeling_plan(...)`, and `scan.run("modeling.readiness")`, covering
  target review, identifier/constant drops, imputation indicators, one-hot
  encoding, date features, and optional numeric scaling.
- Added a workspace modeling workbench that opens from a selected state,
  previews the modeling-readiness action list, and saves the selected feature
  preparation as a tracked dataframe branch.
- Added editable per-action control overrides for cleaning and modeling
  workbenches, so individual parse, mapping, imputation, encoding, date, and
  outlier choices can be changed before applying a branch.
- Added a cleaning-plan column rename review operation so mass/manual column
  naming changes can be previewed and applied from the same auditable
  workbench flow as other cleaning actions.
- Added optional modeling ratio feature suggestions, such as price per square
  foot or revenue per unit, with replayable numerator, denominator, output, and
  zero-denominator controls.
- Added `scan.run("modeling.baseline")` for a fast target-aware modeling smoke
  test with baseline and model scores on a holdout split.
- Improved mixed datetime inference by parsing mixed-format date strings within
  one column during scan and cleaning.
- Expanded the Plotly visualizer spec controls with data min/max filters,
  numeric axis transforms, date bucketing, X sorting, quantile/fixed-width
  histogram binning, numeric X-axis binning for distribution comparisons, and
  top-N category grouping into an "Other" bucket.
- Added rolling-window and cumulative line/area chart controls after visual
  aggregation, supporting mean, sum, and median windows.
- Added a broader first-class visual control surface for sampling/deduping,
  missing-category labels, top/bottom category selection, percent-of-total and
  percent-within-group value transforms, value ranking, y/x sorting, axis
  reversal, tick formatting, palettes, facet wrapping, reference lines, stat
  lines, and target bands.
- Added advanced visual aggregation and presentation controls for weighted
  means, P25/P75/P90/P95 aggregations, value labels, X range sliders, and
  shared-axis toggles for faceted charts.
- Expanded the Plotly visual catalog with strip plots, density heatmaps,
  density contours, sunbursts, geographic scatter maps, choropleths, parallel
  coordinates, and parallel categories, including smarter web defaults for
  required multi-field plots such as x/y, lat/lon, and location/value maps.
- Added profile-driven visual suggestions through
  `scan.visual_recommendations()` and `sf.suggest_visuals(...)`; workspace web
  visualizer payloads now include suggested replayable specs and show them in
  the plot library.
- Added a replayable modeling experiment engine with
  `scan.modeling_experiment(...)`, `sf.modeling_experiment(...)`,
  `sf.modeling_catalog()`, and the `modeling.experiment` lens. Experiments now
  cover supervised regression/classification and clustering with preprocessing,
  holdout splits, cross-validation, optional grid search, random forests, KNN,
  linear/logistic models, XGBoost when installed, k-means, agglomerative
  clustering, DBSCAN, metrics, prediction samples, feature importances, and
  SHAP/permutation/model-native observability.
- Expanded the workspace modeling workbench with experiment controls for task,
  estimator, split size, CV folds, validation strategy, encoder, scaler, grid
  search, SHAP observability, and cluster count plus an in-panel experiment
  result summary.
- Added more advanced visual families: Pareto charts, waterfall charts,
  funnels, radar charts, Q-Q plots, autocorrelation plots, and cumulative
  concentration/Lorenz-style curves, with visual recommendations now suggesting
  concentration and Pareto views where they fit.
- Upgraded modeling observability with real SHAP payloads for supported models:
  global mean absolute SHAP rankings, beeswarm-ready rows, per-record SHAP
  contribution lists, and richer classification reports including precision,
  recall, F1, support, confusion matrices, ROC curve data, and
  precision-recall curve data.
- Added XGBoost SHAP support for modeling experiments, including a fallback
  path for XGBoost estimators that are not accepted by the default SHAP
  explainer interface.
- Added a smarter visual inspector that classifies controls as basic,
  advanced, or expert, supports in-panel control search, and filters controls
  by chart bindings so the visual builder stays compact until deeper options
  are needed.
- Added another visual catalog expansion with lollipop charts, slope charts,
  bump charts, and calendar heatmaps, plus profile-driven recommendations for
  calendar intensity, lollipop comparisons, and rank-movement views.
- Added dedicated correlation heatmap and PCA scatter visual kinds for
  multivariate review, with correlation method, absolute/triangle, annotation,
  and scaling controls.
- Added `target.best_splits` / `entropy.splits`, a target-aware split lens that
  ranks simple numeric thresholds and category one-vs-rest splits by entropy
  information gain for classification targets or variance reduction for
  regression targets.
- Expanded the workspace modeling result panel with native report visuals for
  metric tiles, confusion matrices, ROC/precision-recall curves, SHAP global
  feature bars, beeswarm-style SHAP distributions, and expandable per-record
  SHAP contribution reports.
- Added power-viewer controls for pinned columns, pinned rows, selected-cell
  copying, dataset and filter summary strips, column search/sort, column
  sparklines, collapsible side panels, and stacked sorts while keeping
  view-only controls out of replayed dataframe signatures.

## 0.2.2 - 2026-05-21

- Fixed saved query trees so `sf.query(..., save_tree=True)` and web **Get Data
  -> Query Data** runs materialize the returned root dataframe as a Parquet
  snapshot. Query-created trees can now reopen in the viewer and be pulled later
  without rerunning the source query.
- Added `save_result=False` and `result_name=...` to `sf.query(...)` for users
  who want query lineage saved without a local copy of sensitive returned rows.
- Added safe workspace cleanup helpers with `sf.workspace.delete_tree(...)` and
  `sf.workspace.delete_tree_entries(...)`. Tree deletes remove the tree from the
  workspace web index by default while leaving saved files on disk; branch/leaf
  deletes remove the selected subtree from the saved tree metadata.
- Added a web delete mode for selecting trees, branches, and leaves to remove
  from the workspace web.

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
