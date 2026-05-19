# stateframe Option Registry

This document is the living registry for every data science option that should
eventually be available through stateframe.

The goal is not to build a loose pile of helper functions. The goal is to make
every useful data workflow step available as a structured, discoverable,
clickable, replayable action that fits into the tree/web ledger.

In the final system, a user should be able to select a dataset state, select a
column or group of columns, choose an option such as "histogram", "clip then
histogram", "log transform", "fit baseline model", or "save checkpoint", and
have stateframe handle:

- valid inputs
- parameter controls
- preview
- execution
- output display
- branch placement
- metadata capture
- replay
- optional data materialization

## Registry Contract

Every option should eventually be represented by a registry spec. The spec is
what lets the notebook API, viewer widget, tree widget, future web UI, and
recommendation engine all speak the same language.

Recommended spec fields:

```python
ActionSpec(
    id="distribution.numeric.histogram",
    title="Histogram",
    family="plots",
    kind="plot",
    scope=["column", "columns", "state"],
    input_types=["dataframe"],
    compatible_semantic_types=["numeric", "amount", "percentage"],
    parameters=[...],
    output_types=["visual", "metric_table", "insight"],
    ledger_behavior="artifact",
    replay_behavior="deterministic",
    can_batch=True,
    can_preview=True,
    cost="low",
)
```

### Action Kinds

Use these kinds consistently.

- `view`: changes only the current widget view state.
- `filter`: produces a subsetted DataFrame state.
- `transform`: produces a modified DataFrame state.
- `feature`: produces a DataFrame state with added or changed features.
- `analysis`: produces metrics, tables, insight text, or diagnostics.
- `plot`: produces one or more visual artifacts.
- `model`: produces trained model artifacts, predictions, metrics, or reports.
- `save`: persists tree metadata or materialized data.
- `export`: writes reports, notebooks, HTML, images, model cards, or data files.
- `web`: manages project/workspace/tree registry behavior.

### Ledger Behaviors

Every action must declare how it affects the tree.

- `none`: no ledger write, usually temporary UI preview only.
- `note`: attaches a human note to a state.
- `artifact`: attaches analysis output, plot output, or report output to a state.
- `state`: creates a new child DataFrame state.
- `state_and_artifact`: creates a new DataFrame state and attaches output.
- `tree`: creates, renames, saves, imports, exports, or restores a tree.
- `web`: creates or changes project-level registry metadata.

### Scope

Actions should declare where they operate.

- `cell`: notebook cell or direct Python call.
- `viewer`: current viewer UI state.
- `selection`: selected rows, selected columns, or highlighted values.
- `column`: one column.
- `columns`: multiple columns.
- `row`: one row.
- `rows`: multiple rows.
- `state`: selected ledger state.
- `branch`: selected subtree or path.
- `tree`: one dataset lifecycle.
- `web`: workspace-level registry across trees.

### Parameter Controls

Every parameter should map to a predictable UI control.

- boolean -> toggle
- enum -> select menu or segmented control
- numeric range -> slider plus numeric input
- integer count -> stepper or numeric input
- column -> column picker
- columns -> multi-column picker
- date/datetime -> date picker
- mapping -> editable table
- expression -> guarded expression editor
- code -> explicit advanced mode only
- free text -> text input or note box

### Status Legend

- `built`: present in some form in the current package.
- `next`: high-value target for the clickable UI MVP.
- `planned`: important for the broad framework.
- `later`: valuable, but not needed for the first strong release.
- `research`: needs design, dependency, or statistical validation before adding.

## Current Built Surface

These are already present in some form and should be migrated into the same
option registry shape.

| Option id | Status | Kind | Ledger behavior | Notes |
| --- | --- | --- | --- | --- |
| `viewer.open` | built | view | none | Opens the DataFrame viewer. |
| `viewer.pull` | built | state | state | Pulls current UI state into Python and records a branch. |
| `viewer.filtered_dataframe` | built | state | state | Compatibility alias for `viewer.pull`. |
| `tree.open` | built | web/view | none | Opens one scan's tree widget. |
| `tree.checkout_selected` | built | view | none | Returns selected state DataFrame from memory. |
| `tree.view_selected` | built | view | none | Opens viewer from selected state. |
| `tree.run_selected` | built | analysis | artifact | Runs lens on selected state and records under that node. |
| `tree.run_recommendation` | built | analysis | artifact | Runs selected-state recommendation by rank. |
| `save.tree` | built | save | tree | Saves tree metadata JSON. |
| `save.data` | built | save | artifact | Saves selected or active state to Parquet. |
| `quality.missingness` | built | analysis | artifact | Missingness profile. |
| `quality.type_coercion` | built | analysis | artifact | Type coercion candidates. |
| `cleaning.transform_preview` | built | analysis | artifact | Preview cleaning actions. |
| `footprint.optimize` | built | analysis | artifact | Memory footprint optimization plan. |
| `grain.keys` | built | analysis | artifact | Key and grain candidates. |
| `distribution.numeric` | built | analysis/plot | artifact | Numeric distribution lens. |
| `concentration.lorenz` | built | analysis/plot | artifact | Concentration and Lorenz curve. |
| `categorical.value_counts` | built | analysis/plot | artifact | Categorical counts. |
| `binary.flags` | built | analysis | artifact | Binary flag detection and mapping. |
| `time.cadence` | built | analysis/plot | artifact | Time cadence and records over time. |
| `target.candidates` | built | analysis | artifact | Candidate target detection. |
| `target.balance` | built | analysis/plot | artifact | Target distribution/balance. |
| `target.associations` | built | analysis/plot | artifact | Feature association with target. |
| `target.importance` | built | analysis/plot | artifact | Model-based importance lens. |
| `relationships.correlation` | built | analysis/plot | artifact | Numeric correlation. |
| `relationships.mixed_associations` | built | analysis/plot | artifact | Mixed type associations. |
| `text.lengths` | built | analysis/plot | artifact | Text length diagnostics. |

## UI And Workflow Options

These are the controls that make stateframe feel like a data science workbench
rather than a static profiler.

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `web.open` | built | web | none | Open the workspace web/brain view across all trees. |
| `web.create_workspace` | built | web | web | Initialize `.stateframe` workspace metadata. |
| `web.configure_workspace` | built | web | web | Set tree/data/artifact roots. |
| `web.list_trees` | built | web | none | List all dataset lifecycle trees. |
| `web.search` | built | web | none | Search trees, states, notes, columns, artifacts, code, and models. |
| `web.select_tree` | built | web | none | Select a workspace tree in the web widget. |
| `web.select_state` | built | web | none | Select an entry/state inside a workspace tree. |
| `web.restore_tree` | built | web | tree | Restore a saved tree into live branch-capable objects. |
| `web.restore_state` | built | web | none | Load a selected saved state into Python when a snapshot/source is available. |
| `web.compare_trees` | planned | analysis | artifact | Compare two dataset trees or source versions. |
| `web.merge_trees` | research | transform | state | Join/merge data from separate trees into a new lineage graph node. |
| `tree.rename` | built | web | tree | Rename tree or dataset lifecycle. |
| `tree.clone` | planned | web | tree | Clone tree metadata under a new name. |
| `tree.archive` | planned | web | web | Hide/archive a tree without deleting it. |
| `tree.delete` | planned | web | web | Delete a tree after confirmation. |
| `tree.export` | planned | export | artifact | Export tree as JSON, Markdown, HTML, or image. |
| `tree.report` | planned | export | artifact | Generate narrative report from selected branch or whole tree. |
| `tree.pin_state` | next | web | tree | Mark a state as important. |
| `tree.mark_final` | planned | web | tree | Mark a branch output as final or publishable. |
| `tree.diff_states` | next | analysis | artifact | Compare two states for rows, columns, dtypes, summaries, and filters. |
| `tree.diff_branches` | planned | analysis | artifact | Compare sibling branches. |
| `tree.active_path` | built | view | none | Show active lineage path. |
| `tree.copy_code` | next | export | none | Copy replay code for selected state or action. |
| `tree.open_viewer_from_state` | built | view | none | Open viewer from selected state. |
| `tree.run_action_from_state` | next | analysis | artifact/state | Click any available action for selected state. |
| `tree.save_state_data` | built | save | artifact | Materialize selected state as Parquet. |
| `tree.save_metadata` | built | save | tree | Save ledger metadata. |
| `tree.restore_materialized_state` | built | save | none | Load Parquet checkpoint for selected saved state. |
| `tree.replay_state` | built | transform | none | Rebuild selected viewer-pull state from source and action history. |
| `tree.replay_viewer_state` | built | transform | state | Replay saved viewer filters, sorts, offloads, and column order. |
| `viewer.action_panel` | next | view | none | Show applicable actions for selected columns/state. |
| `viewer.command_palette` | planned | view | none | Search all actions by name. |
| `viewer.parameter_form` | next | view | none | Render parameter controls for chosen action. |
| `viewer.preview_action` | next | view | none | Preview an action before committing it to the tree. |
| `viewer.apply_action` | next | transform/analysis | state/artifact | Execute selected action and record output. |
| `viewer.batch_action` | next | analysis/plot | artifact | Run an action over all compatible columns. |
| `viewer.save_branch_form` | next | state | state | Name/message a pull directly inside the widget. |
| `viewer.filter_builder` | built | view | none | UI filter state. Needs promotion into replayable action spec. |
| `viewer.sort_builder` | built | view | none | UI sort state. Needs promotion into replayable action spec. |
| `viewer.column_order` | built | view | none/state | Column ordering included in pull metadata. |
| `viewer.hide_columns` | built | view | none/state | Hidden columns included in pull metadata. |
| `viewer.select_column` | built | view | none | Select a column for inspection/actions. |
| `viewer.select_rows` | planned | view | none | Select rows manually or from rules. |
| `viewer.bookmark_selection` | planned | note | note | Save row/column selection as a note or named view. |

## Data Ingest And Source Options

Every tree starts with a source. Source capture must become robust enough that
states can be replayed or restored later.

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `source.from_dataframe` | built | web/tree | tree | Start tree from in-memory DataFrame. Replay needs `source_path` or snapshot. |
| `source.from_path` | built | web/tree | tree | Start tree from a local replayable file path with `sf.scan_path(...)`. |
| `source.from_csv` | built | web/tree | tree | Read CSV with tracked path. Rich encoding/dtype options are future work. |
| `source.from_parquet` | built | web/tree | tree | Read Parquet with tracked file metadata. |
| `source.from_excel` | built | web/tree | tree | Read workbook path with default pandas behavior. |
| `source.from_json` | built | web/tree | tree | Read JSON/GeoJSON path with default stateframe normalization. |
| `source.from_sql` | planned | web/tree | tree | Read SQL query/table with connection alias and query hash. |
| `source.from_duckdb` | planned | web/tree | tree | Read DuckDB relation/query. |
| `source.from_polars` | planned | web/tree | tree | Start from Polars DataFrame/LazyFrame. |
| `source.from_dask` | later | web/tree | tree | Start from Dask DataFrame. |
| `source.from_spark` | later | web/tree | tree | Start from Spark DataFrame. |
| `source.from_arrow` | planned | web/tree | tree | Start from Arrow Table/Dataset. |
| `source.from_api` | planned | web/tree | tree | Track API endpoint, params, timestamp, auth alias. |
| `source.from_url` | planned | web/tree | tree | Track URL, headers, fetch time, content hash. |
| `source.from_clipboard` | later | web/tree | tree | Ad hoc pasted table source. |
| `source.from_folder` | planned | web/tree | tree | Folder of files as a dataset. |
| `source.from_glob` | planned | web/tree | tree | Globbed file collection with pattern and resolved files. |
| `source.from_delta` | later | web/tree | tree | Delta Lake source and version. |
| `source.from_iceberg` | later | web/tree | tree | Iceberg table source and snapshot. |
| `source.from_bigquery` | later | web/tree | tree | BigQuery query/table source. |
| `source.from_snowflake` | later | web/tree | tree | Snowflake query/table source. |
| `source.from_s3` | later | web/tree | tree | S3 path, profile alias, file metadata. |
| `source.snapshot_hash` | next | analysis | artifact | Hash source schema and optional data sample. |
| `source.schema_contract` | planned | analysis | artifact | Infer or attach expected source contract. |
| `source.version_check` | planned | analysis | artifact | Detect whether source changed since last scan. |
| `source.set_path` | built | web/tree | web | Update a tree's editable base source path after data moves. |
| `source.refresh` | planned | web/tree | tree | Refresh source and create a new root/version node. |

## Filtering, Subsetting, And Sampling

Filters are first-class operations. A histogram of sold price filtered to 2025
should be represented as a plot artifact whose input state includes a filter
expression, or as a new filtered state plus a plot artifact, depending on the
user's choice.

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `filter.equals` | built | filter | state | Keep rows where column equals value. Currently captured through viewer pull. |
| `filter.not_equals` | next | filter | state | Keep rows where column does not equal value. |
| `filter.in_values` | next | filter | state | Keep values in a set. |
| `filter.not_in_values` | next | filter | state | Exclude values in a set. |
| `filter.contains` | next | filter | state | Text contains substring/pattern. |
| `filter.starts_with` | next | filter | state | Text starts with value. |
| `filter.ends_with` | next | filter | state | Text ends with value. |
| `filter.regex` | planned | filter | state | Regex match with safety and preview. |
| `filter.between` | next | filter | state | Numeric or datetime range. |
| `filter.greater_than` | next | filter | state | Numeric/date lower bound. |
| `filter.less_than` | next | filter | state | Numeric/date upper bound. |
| `filter.is_null` | next | filter | state | Keep null rows. |
| `filter.not_null` | next | filter | state | Keep non-null rows. |
| `filter.is_missing_like` | planned | filter | state | Keep missing-like strings or codes. |
| `filter.quantile_range` | planned | filter | state | Keep rows between quantiles. |
| `filter.top_n` | planned | filter | state | Keep top N by column. |
| `filter.bottom_n` | planned | filter | state | Keep bottom N by column. |
| `filter.rank_range` | planned | filter | state | Keep rank interval by grouped or ungrouped rank. |
| `filter.date_year` | next | filter | state | Keep rows in a year, such as sold date in 2025. |
| `filter.date_month` | next | filter | state | Keep rows in a month. |
| `filter.date_quarter` | planned | filter | state | Keep rows in quarter. |
| `filter.weekday` | planned | filter | state | Keep rows by weekday/weekend. |
| `filter.business_hours` | later | filter | state | Keep rows in time-of-day window. |
| `filter.group_min_count` | planned | filter | state | Keep groups with at least N rows. |
| `filter.group_top_k` | planned | filter | state | Keep top K groups by count or metric. |
| `filter.outlier_iqr` | planned | filter | state | Remove or keep IQR outliers. |
| `filter.outlier_zscore` | planned | filter | state | Remove or keep z-score outliers. |
| `filter.outlier_mad` | planned | filter | state | Remove or keep robust MAD outliers. |
| `filter.custom_query` | planned | filter | state | Pandas query expression with validation. |
| `filter.selection` | planned | filter | state | Keep manually selected rows. |
| `sample.head` | planned | filter | state | First N rows. |
| `sample.tail` | planned | filter | state | Last N rows. |
| `sample.random` | next | filter | state | Random sample with seed. |
| `sample.frac` | planned | filter | state | Fraction sample with seed. |
| `sample.stratified` | planned | filter | state | Stratified sample by column. |
| `sample.grouped` | planned | filter | state | Sample N per group. |
| `sample.systematic` | later | filter | state | Every kth row. |
| `sample.time_window` | planned | filter | state | Time range or rolling window sample. |
| `sample.balance_classes` | planned | filter | state | Balanced class sample. |

## Cleansing And Transforms

These actions produce new DataFrame states. Many should support preview mode,
side-by-side before/after summaries, and "apply to one column" or "apply to all
compatible columns".

### Missing Values

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `clean.missing_like_to_null` | built | transform | state | Convert missing-like strings/codes to null. |
| `clean.empty_string_to_null` | planned | transform | state | Convert empty/whitespace-only strings to null. |
| `clean.null_to_value` | planned | transform | state | Fill nulls with explicit value. |
| `clean.null_to_mean` | planned | transform | state | Fill numeric nulls with mean. |
| `clean.null_to_median` | planned | transform | state | Fill numeric nulls with median. |
| `clean.null_to_mode` | planned | transform | state | Fill nulls with mode. |
| `clean.null_to_group_stat` | planned | transform | state | Fill nulls using group-level statistic. |
| `clean.null_forward_fill` | planned | transform | state | Forward fill, optionally by group. |
| `clean.null_backward_fill` | planned | transform | state | Backward fill, optionally by group. |
| `clean.null_interpolate_linear` | planned | transform | state | Linear interpolation. |
| `clean.null_interpolate_time` | planned | transform | state | Time-aware interpolation. |
| `clean.null_knn_impute` | research | transform | state | KNN imputation. |
| `clean.null_iterative_impute` | research | transform | state | Iterative/model-based imputation. |
| `clean.null_indicator` | planned | feature | state | Add boolean flag indicating original missingness. |
| `clean.drop_null_rows` | planned | transform | state | Drop rows with nulls in selected columns. |
| `clean.drop_null_columns` | planned | transform | state | Drop columns above missingness threshold. |
| `clean.coalesce_columns` | planned | transform | state | Combine columns by first non-null value. |
| `clean.reconcile_duplicate_columns` | planned | transform | state | Merge duplicate source columns after review. |

### Type Parsing And Coercion

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `type.parse_numeric` | built | transform | state | Parse numeric-like strings. |
| `type.parse_datetime` | built | transform | state | Parse datetime-like strings. |
| `type.parse_boolean` | built | transform | state | Map binary-like strings to boolean/nullable boolean. |
| `type.to_string` | planned | transform | state | Cast to pandas string. |
| `type.to_category` | built | transform | state | Cast low-cardinality strings to category through footprint plan. |
| `type.to_int` | planned | transform | state | Cast numeric to integer with nullable support. |
| `type.to_float` | planned | transform | state | Cast numeric to float. |
| `type.to_decimal` | later | transform | state | Decimal type for money/precision-sensitive work. |
| `type.to_datetime_utc` | planned | transform | state | Convert datetime to UTC. |
| `type.to_timezone` | planned | transform | state | Convert datetime timezone. |
| `type.to_period` | later | transform | state | Convert datetime to period. |
| `type.to_timedelta` | planned | transform | state | Parse duration/timedelta values. |
| `type.to_ordered_category` | planned | transform | state | Ordered category with explicit order. |
| `type.downcast_integer` | built | transform | state | Downcast integer dtype through footprint plan. |
| `type.downcast_float` | built | transform | state | Downcast float dtype through footprint plan. |
| `type.infer_schema` | planned | analysis | artifact | Infer target schema without changing data. |
| `type.enforce_schema` | planned | transform | state | Apply saved schema contract. |
| `type.compare_schema` | planned | analysis | artifact | Compare current dtypes to contract or previous state. |

### String And Text Cleansing

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `string.trim` | built | transform | state | Trim leading/trailing whitespace. |
| `string.normalize_whitespace` | planned | transform | state | Collapse repeated whitespace. |
| `string.lowercase` | planned | transform | state | Lowercase text. |
| `string.uppercase` | planned | transform | state | Uppercase text. |
| `string.titlecase` | planned | transform | state | Title case text. |
| `string.casefold` | planned | transform | state | Unicode-aware normalization. |
| `string.remove_accents` | planned | transform | state | Strip diacritics for matching. |
| `string.normalize_unicode` | planned | transform | state | NFC/NFKC normalization. |
| `string.strip_prefix` | planned | transform | state | Remove known prefix. |
| `string.strip_suffix` | planned | transform | state | Remove known suffix. |
| `string.replace` | planned | transform | state | Literal string replacement. |
| `string.regex_replace` | planned | transform | state | Regex replacement with preview. |
| `string.extract_regex` | planned | feature | state | Extract capture groups into feature columns. |
| `string.split_column` | planned | feature | state | Split into multiple columns. |
| `string.join_columns` | planned | feature | state | Concatenate columns into text feature. |
| `string.remove_punctuation` | planned | transform | state | Remove punctuation. |
| `string.remove_digits` | planned | transform | state | Remove digits. |
| `string.remove_stopwords` | research | transform | state | Stopword removal for text analysis. |
| `string.stem` | research | transform | state | Stemming. |
| `string.lemmatize` | research | transform | state | Lemmatization. |
| `string.mask_sensitive` | planned | transform | state | Mask emails, phone numbers, IDs, names, or patterns. |
| `string.hash_values` | planned | transform | state | Hash sensitive identifiers. |
| `string.standardize_labels` | planned | transform | state | Map inconsistent labels to canonical values. |
| `string.fuzzy_group_labels` | research | analysis/transform | artifact/state | Suggest or apply fuzzy category merges. |

### Numeric Transforms

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `numeric.clip` | next | transform | state | Clip to explicit bounds or quantiles. |
| `numeric.winsorize` | next | transform | state | Winsorize tails. |
| `numeric.log` | next | transform | state | Log transform with offset handling. |
| `numeric.log1p` | next | transform | state | `log1p` for nonnegative skewed values. |
| `numeric.sqrt` | planned | transform | state | Square root transform. |
| `numeric.cuberoot` | planned | transform | state | Cube-root transform. |
| `numeric.boxcox` | planned | transform | state | Box-Cox transform for positive data. |
| `numeric.yeojohnson` | planned | transform | state | Yeo-Johnson transform. |
| `numeric.standardize` | planned | transform | state | Z-score scale. |
| `numeric.robust_scale` | planned | transform | state | Median/IQR scale. |
| `numeric.minmax_scale` | planned | transform | state | Min-max scale. |
| `numeric.maxabs_scale` | planned | transform | state | Max-abs scale. |
| `numeric.quantile_transform` | planned | transform | state | Quantile transform to uniform/normal. |
| `numeric.rank_transform` | planned | transform | state | Rank or percentile rank. |
| `numeric.bucketize` | planned | feature | state | Bin into fixed-width or custom bins. |
| `numeric.quantile_bins` | planned | feature | state | Bin by quantiles. |
| `numeric.round` | planned | transform | state | Round to decimals. |
| `numeric.floor` | planned | transform | state | Floor values. |
| `numeric.ceil` | planned | transform | state | Ceiling values. |
| `numeric.abs` | planned | transform | state | Absolute value. |
| `numeric.negate` | later | transform | state | Negate value. |
| `numeric.percent_change` | planned | feature | state | Percent change, optionally by group/time. |
| `numeric.diff` | planned | feature | state | Difference from prior row/time. |
| `numeric.cumulative_sum` | planned | feature | state | Cumulative sum. |
| `numeric.cumulative_mean` | planned | feature | state | Cumulative mean. |
| `numeric.cumulative_max` | planned | feature | state | Cumulative max. |
| `numeric.cumulative_min` | planned | feature | state | Cumulative min. |
| `numeric.ratio` | planned | feature | state | Ratio of two columns. |
| `numeric.safe_divide` | planned | feature | state | Divide with zero/null handling. |
| `numeric.interaction_product` | planned | feature | state | Product of two numeric columns. |
| `numeric.polynomial` | planned | feature | state | Polynomial powers. |

### Datetime And Time Transforms

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `datetime.extract_year` | planned | feature | state | Year feature. |
| `datetime.extract_quarter` | planned | feature | state | Quarter feature. |
| `datetime.extract_month` | planned | feature | state | Month feature. |
| `datetime.extract_week` | planned | feature | state | ISO week feature. |
| `datetime.extract_day` | planned | feature | state | Day of month feature. |
| `datetime.extract_dayofweek` | planned | feature | state | Weekday feature. |
| `datetime.extract_hour` | planned | feature | state | Hour feature. |
| `datetime.extract_minute` | later | feature | state | Minute feature. |
| `datetime.extract_second` | later | feature | state | Second feature. |
| `datetime.is_weekend` | planned | feature | state | Weekend flag. |
| `datetime.is_month_start` | later | feature | state | Month-start flag. |
| `datetime.is_month_end` | later | feature | state | Month-end flag. |
| `datetime.is_quarter_start` | later | feature | state | Quarter-start flag. |
| `datetime.is_quarter_end` | later | feature | state | Quarter-end flag. |
| `datetime.days_since` | planned | feature | state | Days since reference date. |
| `datetime.days_until` | planned | feature | state | Days until reference date. |
| `datetime.between_columns` | planned | feature | state | Duration between two date columns. |
| `datetime.floor` | planned | transform | state | Floor to day/week/month/etc. |
| `datetime.ceil` | planned | transform | state | Ceil to frequency. |
| `datetime.round` | planned | transform | state | Round to frequency. |
| `datetime.resample` | planned | transform | state | Resample time series with aggregation. |
| `datetime.asof_join` | later | transform | state | As-of merge for time-aligned datasets. |
| `datetime.fill_gaps` | planned | transform | state | Add missing periods. |
| `datetime.mark_holidays` | later | feature | state | Holiday flags by calendar. |
| `datetime.business_day_features` | later | feature | state | Business-day and trading-day features. |

### Categorical Transforms

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `category.standardize_values` | planned | transform | state | Map labels to canonical values. |
| `category.merge_rare` | next | transform | state | Collapse rare categories into "Other". |
| `category.top_k_other` | next | transform | state | Keep top K categories, collapse rest. |
| `category.reorder` | planned | transform | state | Set category order. |
| `category.rename_levels` | planned | transform | state | Rename levels with mapping. |
| `category.drop_unused_levels` | built | transform | state | Remove unused category levels through footprint plan. |
| `category.one_hot` | planned | feature | state | One-hot encode selected categories. |
| `category.ordinal_encode` | planned | feature | state | Ordinal encode with explicit order. |
| `category.frequency_encode` | planned | feature | state | Encode by frequency. |
| `category.target_encode` | research | feature | state | Target encoding with leakage-safe folds. |
| `category.hash_encode` | planned | feature | state | Hashing encoder. |
| `category.binary_encode` | later | feature | state | Binary encoding. |
| `category.cross` | planned | feature | state | Combine two or more categorical columns. |

### Row, Column, And Shape Transforms

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `columns.rename` | planned | transform | state | Rename columns. |
| `columns.clean_names` | next | transform | state | Standardize names to snake_case or chosen convention. |
| `columns.reorder` | built | transform/view | state | Reorder columns through viewer and pull. |
| `columns.keep` | planned | transform | state | Keep selected columns. |
| `columns.drop` | planned | transform | state | Drop selected columns. |
| `columns.hide_in_view` | built | view | none/state | Hide selected columns in viewer. |
| `columns.move_to_front` | planned | transform | state | Move selected columns to front. |
| `columns.group_by_role` | planned | view | none | Organize columns by semantic role. |
| `rows.drop_duplicates` | planned | transform | state | Drop duplicate rows. |
| `rows.dedupe_by_key` | planned | transform | state | Deduplicate by key with keep rule. |
| `rows.drop_empty` | planned | transform | state | Drop fully empty rows. |
| `rows.sort_values` | built | transform/view | state | Sort through viewer and pull. |
| `rows.reset_index` | planned | transform | state | Reset index. |
| `rows.set_index` | planned | transform | state | Set index from column. |
| `rows.create_row_id` | planned | feature | state | Add stable row id. |
| `reshape.pivot` | planned | transform | state | Pivot table to wide form. |
| `reshape.melt` | planned | transform | state | Melt wide to long. |
| `reshape.stack` | later | transform | state | Stack columns/index levels. |
| `reshape.unstack` | later | transform | state | Unstack index levels. |
| `reshape.explode` | planned | transform | state | Explode list-like column. |
| `reshape.normalize_json` | planned | transform | state | Normalize nested JSON column. |
| `group.aggregate` | planned | transform | state | Group by and aggregate. |
| `join.merge` | planned | transform | state | Merge two states/trees. |
| `join.concat_rows` | planned | transform | state | Concatenate rows. |
| `join.concat_columns` | planned | transform | state | Concatenate columns. |
| `join.anti_join` | planned | transform | state | Rows in left not in right. |
| `join.semi_join` | planned | transform | state | Rows in left matching right. |
| `join.validate_keys` | planned | analysis | artifact | Validate join key cardinality and duplicates. |

### Outliers, Anomalies, And Data Corrections

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `outlier.detect_iqr` | planned | analysis | artifact | Flag IQR outliers. |
| `outlier.detect_zscore` | planned | analysis | artifact | Flag z-score outliers. |
| `outlier.detect_mad` | planned | analysis | artifact | Flag robust MAD outliers. |
| `outlier.detect_isolation_forest` | research | analysis | artifact | Isolation forest anomaly scores. |
| `outlier.detect_lof` | research | analysis | artifact | Local outlier factor. |
| `outlier.detect_dbscan` | research | analysis | artifact | Density anomaly detection. |
| `outlier.cap` | next | transform | state | Cap detected outliers. |
| `outlier.remove` | planned | transform | state | Remove detected outliers. |
| `outlier.flag` | planned | feature | state | Add outlier flag columns. |
| `outlier.review_table` | planned | analysis | artifact | Review highest-risk rows. |
| `correct.value_mapping` | planned | transform | state | Correct known bad values using mapping. |
| `correct.range_rules` | planned | transform | state | Null, clip, or flag values outside valid range. |
| `correct.cross_field_rules` | planned | transform | state | Flag/correct impossible combinations. |

## Feature Engineering

Feature actions produce a new DataFrame state and must clearly mark generated
columns with provenance, source columns, parameters, and leakage warnings when
target-aware.

### Numeric Features

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `feature.numeric_ratio` | planned | feature | state | Ratio between two numeric columns. |
| `feature.numeric_difference` | planned | feature | state | Difference between columns. |
| `feature.numeric_sum` | planned | feature | state | Row-wise sum. |
| `feature.numeric_product` | planned | feature | state | Row-wise product. |
| `feature.numeric_mean` | planned | feature | state | Row-wise mean over selected columns. |
| `feature.numeric_max` | planned | feature | state | Row-wise max. |
| `feature.numeric_min` | planned | feature | state | Row-wise min. |
| `feature.numeric_range` | planned | feature | state | Max minus min. |
| `feature.numeric_polynomial` | planned | feature | state | Polynomial terms. |
| `feature.numeric_spline` | research | feature | state | Spline basis features. |
| `feature.numeric_quantile_bin` | planned | feature | state | Quantile bins. |
| `feature.numeric_fixed_bin` | planned | feature | state | Fixed width bins. |
| `feature.numeric_is_zero` | planned | feature | state | Zero indicator. |
| `feature.numeric_is_positive` | planned | feature | state | Positive indicator. |
| `feature.numeric_is_negative` | planned | feature | state | Negative indicator. |
| `feature.numeric_missing_indicator` | planned | feature | state | Missingness flag. |
| `feature.numeric_outlier_indicator` | planned | feature | state | Outlier flag. |

### Categorical Features

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `feature.category_one_hot` | planned | feature | state | One-hot encode. |
| `feature.category_count` | planned | feature | state | Category frequency/count. |
| `feature.category_frequency` | planned | feature | state | Category relative frequency. |
| `feature.category_rank` | planned | feature | state | Rank categories by frequency or metric. |
| `feature.category_rare_flag` | planned | feature | state | Flag rare categories. |
| `feature.category_cross` | planned | feature | state | Crossed category feature. |
| `feature.category_target_mean` | research | feature | state | Leakage-safe target mean encoding. |
| `feature.category_woe` | research | feature | state | Weight-of-evidence encoding. |
| `feature.category_embedding` | research | feature | state | Learned category embeddings. |

### Datetime And Time-Series Features

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `feature.date_parts` | planned | feature | state | Add common date parts in one action. |
| `feature.time_since_previous` | planned | feature | state | Time since prior event by entity. |
| `feature.time_until_next` | planned | feature | state | Time until next event by entity. |
| `feature.event_count_window` | planned | feature | state | Count events in rolling time window. |
| `feature.rolling_mean` | planned | feature | state | Rolling mean. |
| `feature.rolling_sum` | planned | feature | state | Rolling sum. |
| `feature.rolling_min` | planned | feature | state | Rolling min. |
| `feature.rolling_max` | planned | feature | state | Rolling max. |
| `feature.rolling_std` | planned | feature | state | Rolling standard deviation. |
| `feature.rolling_median` | planned | feature | state | Rolling median. |
| `feature.expanding_mean` | planned | feature | state | Expanding mean. |
| `feature.ewm` | planned | feature | state | Exponentially weighted moving statistic. |
| `feature.lag` | planned | feature | state | Lag feature by row or time. |
| `feature.lead` | planned | feature | state | Lead feature. |
| `feature.diff` | planned | feature | state | Difference from lag. |
| `feature.percent_change` | planned | feature | state | Percent change from lag. |
| `feature.seasonality_fourier` | research | feature | state | Fourier seasonality features. |
| `feature.cyclical_encode` | planned | feature | state | Sine/cosine encoding for cyclic date parts. |
| `feature.holiday_flag` | later | feature | state | Holiday/calendar feature. |
| `feature.business_calendar` | later | feature | state | Business-day calendar features. |

### Aggregate And Entity Features

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `feature.group_count` | planned | feature | state | Count rows by group. |
| `feature.group_sum` | planned | feature | state | Group sum joined back. |
| `feature.group_mean` | planned | feature | state | Group mean joined back. |
| `feature.group_median` | planned | feature | state | Group median joined back. |
| `feature.group_min` | planned | feature | state | Group min joined back. |
| `feature.group_max` | planned | feature | state | Group max joined back. |
| `feature.group_std` | planned | feature | state | Group standard deviation. |
| `feature.group_nunique` | planned | feature | state | Distinct count by group. |
| `feature.group_share` | planned | feature | state | Row value as share of group total. |
| `feature.group_rank` | planned | feature | state | Rank within group. |
| `feature.group_percentile` | planned | feature | state | Percentile within group. |
| `feature.entity_recency` | planned | feature | state | Recency by entity. |
| `feature.entity_frequency` | planned | feature | state | Frequency by entity. |
| `feature.entity_monetary` | planned | feature | state | Monetary/value aggregation by entity. |
| `feature.entity_tenure` | planned | feature | state | Duration since first event. |

### Text Features

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `feature.text_length` | built | analysis/feature | artifact/state | Text length; currently analysis lens exists. |
| `feature.text_word_count` | planned | feature | state | Word count. |
| `feature.text_sentence_count` | planned | feature | state | Sentence count. |
| `feature.text_avg_word_length` | planned | feature | state | Average word length. |
| `feature.text_contains` | planned | feature | state | Contains term/pattern flag. |
| `feature.text_regex_flags` | planned | feature | state | Flags from multiple regexes. |
| `feature.text_tfidf` | research | feature | state/artifact | TF-IDF matrix or selected terms. |
| `feature.text_topic_model` | research | feature/model | state/artifact | Topic scores. |
| `feature.text_sentiment` | research | feature | state | Sentiment score. |
| `feature.text_embedding` | research | feature | state/artifact | Embedding vectors with provider/local model metadata. |

### Geospatial Features

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `feature.geo_point` | planned | feature | state | Build geometry/point from lat/lon. |
| `feature.geo_geohash` | planned | feature | state | Geohash encoding. |
| `feature.geo_h3` | planned | feature | state | H3 cell encoding. |
| `feature.geo_distance` | planned | feature | state | Distance between points or to reference point. |
| `feature.geo_bearing` | later | feature | state | Bearing between points. |
| `feature.geo_within_polygon` | planned | feature | state | Spatial join or within flag. |
| `feature.geo_nearest` | later | feature | state | Nearest neighbor/place feature. |
| `feature.geo_cluster` | research | feature | state/artifact | Spatial clustering. |

### Feature Selection And Readiness

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `feature.select_by_missingness` | planned | transform | state | Keep/drop columns by missingness. |
| `feature.select_by_variance` | planned | transform | state | Drop low-variance columns. |
| `feature.select_by_cardinality` | planned | transform | state | Drop high/low-cardinality columns. |
| `feature.select_by_correlation` | planned | transform | state | Remove highly correlated features. |
| `feature.select_by_target_assoc` | planned | transform | state | Keep top target-associated features. |
| `feature.select_by_importance` | planned | transform | state | Keep model-important features. |
| `feature.detect_leakage` | planned | analysis | artifact | Detect target leakage risk. |
| `feature.detect_id_columns` | planned | analysis | artifact | Identify identifiers unlikely to be modeling features. |
| `feature.detect_constant_columns` | planned | analysis | artifact | Constant/near-constant feature detection. |
| `feature.make_model_matrix` | planned | transform | state | Build X/y matrix from selected roles. |

## Footprint And Performance Optimizing

These options should make large notebook workflows feel safer and faster. Some
produce transform states; others produce plans or storage artifacts.

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `footprint.profile` | planned | analysis | artifact | Detailed memory profile by column/block. |
| `footprint.optimize` | built | analysis | artifact | Generate optimization plan. |
| `footprint.apply_plan` | next | transform | state | Apply selected optimization actions. |
| `footprint.downcast_int` | built | transform | state | Downcast integer columns. |
| `footprint.downcast_float` | built | transform | state | Downcast float columns. |
| `footprint.object_to_category` | built | transform | state | Convert object/string to category. |
| `footprint.compact_category` | built | transform | state | Remove unused category values. |
| `footprint.object_to_string` | planned | transform | state | Convert object columns to pandas string. |
| `footprint.bool_to_nullable` | planned | transform | state | Use nullable boolean. |
| `footprint.sparse_convert` | planned | transform | state | Convert sparse-like columns to sparse dtype. |
| `footprint.drop_duplicate_columns` | planned | transform | state | Drop duplicate columns by hash. |
| `footprint.drop_constant_columns` | planned | transform | state | Drop constant columns. |
| `footprint.drop_high_missing_columns` | planned | transform | state | Drop columns above missingness threshold. |
| `footprint.materialize_parquet` | built | save | artifact | Save state as Parquet. |
| `footprint.parquet_compress` | planned | save | artifact | Choose compression codec. |
| `footprint.parquet_partition` | planned | save | artifact | Partition data by columns. |
| `footprint.parquet_row_group_size` | planned | save | artifact | Set row group size. |
| `footprint.parquet_dictionary_encode` | planned | save | artifact | Dictionary encoding options. |
| `footprint.parquet_statistics_check` | planned | analysis | artifact | Inspect min/max/null stats. |
| `footprint.cache_state` | next | save | artifact | Materialize state for fast restore. |
| `footprint.evict_state` | planned | save | artifact | Remove materialized data but keep metadata. |
| `footprint.sample_for_viewer` | planned | view | none | Load sampled view for large data. |
| `footprint.lazy_scan` | later | web/tree | tree | Lazy scanning for large datasets. |
| `footprint.polars_convert` | later | transform | state | Convert to Polars backend. |
| `footprint.duckdb_register` | later | web | artifact | Register state in DuckDB for query execution. |
| `footprint.chunked_profile` | later | analysis | artifact | Profile data in chunks. |
| `footprint.approx_distinct` | later | analysis | artifact | Approximate cardinality. |
| `footprint.approx_quantiles` | later | analysis | artifact | Approximate quantiles for large data. |

## Analysis And Profiling Options

Analysis actions should attach artifacts to the selected state. They should not
silently change data unless explicitly promoted to a transform/action.

### Overview And Schema

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `overview.summary` | planned | analysis | artifact | Rows, columns, memory, dtypes, roles. |
| `overview.column_inventory` | planned | analysis | artifact | Searchable column catalog. |
| `overview.semantic_types` | planned | analysis | artifact | Inferred semantic types and confidence. |
| `overview.dataset_shape` | planned | analysis | artifact | Long/wide/sparse/high-cardinality profile. |
| `overview.profile_report` | planned | analysis | artifact | Combined overview report. |
| `schema.infer` | planned | analysis | artifact | Infer schema. |
| `schema.compare_states` | planned | analysis | artifact | Compare schemas across states. |
| `schema.compare_source` | planned | analysis | artifact | Compare current data to source contract. |
| `schema.drift` | planned | analysis | artifact | Schema drift over source versions. |
| `schema.validate` | planned | analysis | artifact | Validate schema contract. |
| `schema.suggest_contract` | planned | analysis | artifact | Suggest constraints from observed data. |

### Quality And Integrity

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `quality.missingness` | built | analysis/plot | artifact | Missingness summary and visual. |
| `quality.missingness_matrix` | next | analysis/plot | artifact | Missingness pattern matrix. |
| `quality.missingness_by_group` | planned | analysis/plot | artifact | Missingness by category/time/group. |
| `quality.type_coercion` | built | analysis | artifact | Type conversion candidates. |
| `quality.duplicate_rows` | planned | analysis | artifact | Duplicate row diagnostics. |
| `quality.duplicate_keys` | planned | analysis | artifact | Duplicate key diagnostics. |
| `quality.invalid_values` | planned | analysis | artifact | Values outside valid sets/ranges. |
| `quality.range_violations` | planned | analysis | artifact | Range violations. |
| `quality.cross_field_violations` | planned | analysis | artifact | Logical rule violations. |
| `quality.cardinality` | planned | analysis | artifact | Cardinality and distinct ratios. |
| `quality.sparsity` | built | analysis | artifact | Sparse column/data warnings. |
| `quality.constant_columns` | planned | analysis | artifact | Constant and near-constant columns. |
| `quality.high_cardinality` | planned | analysis | artifact | High-cardinality categorical fields. |
| `quality.patterns` | planned | analysis | artifact | String pattern profile. |
| `quality.sensitive_data_scan` | planned | analysis | artifact | Potential PII/sensitive columns. |
| `quality.data_contract` | planned | analysis | artifact | Data contract validation result. |
| `quality.row_completeness` | planned | analysis/plot | artifact | Row-level completeness score. |
| `quality.column_completeness` | planned | analysis/plot | artifact | Column-level completeness score. |

### Grain, Keys, And Entity Structure

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `grain.keys` | built | analysis | artifact | Candidate keys and grain. |
| `grain.unique_key_scan` | planned | analysis | artifact | Unique key combinations. |
| `grain.functional_dependencies` | planned | analysis | artifact | Detect columns determined by keys. |
| `grain.entity_columns` | planned | analysis | artifact | Candidate entity identifiers. |
| `grain.transaction_grain` | planned | analysis | artifact | Transaction/event grain diagnostics. |
| `grain.time_grain` | planned | analysis | artifact | Time granularity and cadence by entity. |
| `grain.parent_child` | planned | analysis | artifact | Parent/child structure. |
| `grain.join_key_quality` | planned | analysis | artifact | Key quality before joining trees. |
| `grain.slowly_changing_dimension` | later | analysis | artifact | SCD patterns. |

### Numeric Analysis

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `distribution.numeric` | built | analysis/plot | artifact | Numeric distribution. |
| `numeric.summary_stats` | next | analysis | artifact | Mean, median, quantiles, skew, kurtosis, etc. |
| `numeric.quantiles` | next | analysis/plot | artifact | Quantile table/plot. |
| `numeric.skewness` | planned | analysis | artifact | Skew diagnostics. |
| `numeric.kurtosis` | planned | analysis | artifact | Tail diagnostics. |
| `numeric.zero_inflation` | planned | analysis | artifact | Zero mass diagnostics. |
| `numeric.negative_values` | planned | analysis | artifact | Negative value checks. |
| `numeric.range_profile` | planned | analysis | artifact | Min/max/range and impossible value hints. |
| `numeric.outliers_iqr` | planned | analysis/plot | artifact | IQR outlier analysis. |
| `numeric.outliers_zscore` | planned | analysis/plot | artifact | Z-score outlier analysis. |
| `numeric.outliers_mad` | planned | analysis/plot | artifact | Robust MAD outlier analysis. |
| `numeric.normality` | planned | analysis/plot | artifact | Normality tests and Q-Q plot. |
| `numeric.distribution_fit` | research | analysis/plot | artifact | Fit candidate distributions. |
| `numeric.heavy_tail` | planned | analysis/plot | artifact | Heavy-tail diagnostics. |
| `numeric.concentration` | built | analysis/plot | artifact | Lorenz/Pareto concentration. |
| `numeric.digit_analysis` | later | analysis/plot | artifact | Benford/digit frequency checks. |
| `numeric.rounding_profile` | planned | analysis | artifact | Rounding/heaping diagnostics. |
| `numeric.monotonicity` | planned | analysis | artifact | Monotonic relationship checks. |

### Categorical, Binary, And Text Analysis

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `categorical.value_counts` | built | analysis/plot | artifact | Counts and top categories. |
| `categorical.frequency_table` | next | analysis | artifact | Full or top-k frequency table. |
| `categorical.rare_categories` | planned | analysis | artifact | Rare category diagnostics. |
| `categorical.cardinality_profile` | planned | analysis | artifact | Cardinality and entropy. |
| `categorical.entropy` | planned | analysis | artifact | Category entropy. |
| `categorical.dominance` | planned | analysis | artifact | Dominant level risk. |
| `categorical.co_occurrence` | planned | analysis/plot | artifact | Co-occurrence matrix between categoricals. |
| `categorical.group_distribution` | planned | analysis/plot | artifact | Category distribution by group. |
| `categorical.chi_square` | planned | analysis | artifact | Association test between categories. |
| `binary.flags` | built | analysis | artifact | Binary flag mapping. |
| `binary.rate` | planned | analysis/plot | artifact | Binary rate overall/by group/time. |
| `binary.imbalance` | planned | analysis | artifact | Binary imbalance diagnostics. |
| `text.lengths` | built | analysis/plot | artifact | Text length profile. |
| `text.patterns` | planned | analysis | artifact | Regex/pattern profile. |
| `text.token_frequency` | planned | analysis/plot | artifact | Token frequency. |
| `text.ngram_frequency` | planned | analysis/plot | artifact | N-gram frequency. |
| `text.language_detect` | later | analysis | artifact | Language detection. |
| `text.duplicates_near` | research | analysis | artifact | Near-duplicate text. |
| `text.topic_model` | research | analysis/model | artifact | Topic modeling diagnostics. |
| `text.embedding_map` | research | analysis/plot | artifact | Embedding projection. |

### Time And Time-Series Analysis

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `time.cadence` | built | analysis/plot | artifact | Cadence, gaps, records over time. |
| `time.records_over_time` | built | analysis/plot | artifact | Records over time. |
| `time.gap_analysis` | planned | analysis/plot | artifact | Gaps by time/entity. |
| `time.duplicate_timestamps` | planned | analysis | artifact | Duplicate timestamp checks. |
| `time.coverage` | planned | analysis/plot | artifact | Time coverage and missing periods. |
| `time.seasonality` | planned | analysis/plot | artifact | Day/week/month/annual seasonality. |
| `time.trend` | planned | analysis/plot | artifact | Trend diagnostics. |
| `time.change_points` | research | analysis/plot | artifact | Change point detection. |
| `time.autocorrelation` | planned | analysis/plot | artifact | ACF/PACF. |
| `time.stationarity` | research | analysis | artifact | Stationarity tests. |
| `time.decomposition` | research | analysis/plot | artifact | Trend/seasonality/residual decomposition. |
| `time.anomaly_scan` | research | analysis/plot | artifact | Time-series anomaly detection. |
| `time.grouped_series_profile` | planned | analysis | artifact | Profile many entity-level series. |

### Relationships And Multivariate Analysis

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `relationships.correlation` | built | analysis/plot | artifact | Numeric correlation heatmap. |
| `relationships.mixed_associations` | built | analysis/plot | artifact | Mixed type association scan. |
| `relationships.scatter_profile` | planned | analysis/plot | artifact | Numeric pair profile. |
| `relationships.pairplot` | planned | plot | artifact | Pairwise plot matrix. |
| `relationships.crosstab` | planned | analysis | artifact | Categorical crosstab. |
| `relationships.chi_square` | planned | analysis | artifact | Categorical association test. |
| `relationships.anova` | planned | analysis | artifact | Numeric by categorical association. |
| `relationships.mutual_information` | planned | analysis | artifact | Mutual information scan. |
| `relationships.partial_correlation` | research | analysis | artifact | Partial correlation. |
| `relationships.vif` | planned | analysis | artifact | Variance inflation factor. |
| `relationships.cluster_columns` | planned | analysis/plot | artifact | Cluster similar columns. |
| `relationships.duplicate_columns` | planned | analysis | artifact | Duplicate or near-duplicate columns. |
| `relationships.interaction_scan` | research | analysis | artifact | Candidate interaction effects. |

### Target-Aware Analysis

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `target.candidates` | built | analysis/plot | artifact | Candidate target detection. |
| `target.balance` | built | analysis/plot | artifact | Target distribution and imbalance. |
| `target.associations` | built | analysis/plot | artifact | Feature associations with target. |
| `target.importance` | built | analysis/plot | artifact | Model-based target importance. |
| `target.leakage_scan` | next | analysis | artifact | Leakage risk scan. |
| `target.missingness_by_target` | planned | analysis/plot | artifact | Missingness vs target. |
| `target.numeric_by_target` | planned | analysis/plot | artifact | Numeric distributions by target. |
| `target.category_by_target` | planned | analysis/plot | artifact | Category rates by target. |
| `target.time_by_target` | planned | analysis/plot | artifact | Target over time. |
| `target.segment_performance` | planned | analysis | artifact | Target metric by segment. |
| `target.lift_table` | planned | analysis/plot | artifact | Lift/gains table for scored data. |
| `target.calibration_profile` | planned | analysis/plot | artifact | Probability calibration profile. |

### Drift, Comparison, And Experiment Analysis

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `compare.states` | next | analysis | artifact | Compare two states. |
| `compare.datasets` | planned | analysis | artifact | Compare two trees/datasets. |
| `compare.schema` | planned | analysis | artifact | Schema difference. |
| `compare.distribution` | planned | analysis/plot | artifact | Distribution difference. |
| `compare.population_stability` | planned | analysis/plot | artifact | PSI. |
| `compare.ks_test` | planned | analysis | artifact | Kolmogorov-Smirnov test. |
| `compare.chi_square` | planned | analysis | artifact | Categorical distribution difference. |
| `compare.mean_difference` | planned | analysis | artifact | T-test/effect size. |
| `compare.effect_size` | planned | analysis | artifact | Cohen's d and related measures. |
| `experiment.ab_summary` | planned | analysis | artifact | A/B test summary. |
| `experiment.power` | research | analysis | artifact | Power and sample size. |
| `experiment.sequential_monitor` | research | analysis | artifact | Sequential testing view. |
| `causal.propensity_balance` | research | analysis/plot | artifact | Propensity and covariate balance. |
| `causal.treatment_effect` | research | analysis | artifact | Treatment effect estimation. |

## Plot And Visual Output Options

Plot options should be executable directly, batchable when useful, and usable as
visual outputs for analysis actions. The UI should allow pre-filters and
pre-transforms like clip/log before plot generation without forcing permanent
data changes unless the user chooses to create a branch.

### Univariate Plots

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `plot.histogram` | next | plot | artifact | Histogram for numeric column. |
| `plot.histogram_batch` | next | plot | artifact | Histogram for every numeric column. |
| `plot.histogram_grouped` | next | plot | artifact | Histogram split by category. |
| `plot.histogram_overlay` | planned | plot | artifact | Overlay histograms for groups/states. |
| `plot.density` | planned | plot | artifact | KDE/density curve. |
| `plot.ecdf` | planned | plot | artifact | Empirical CDF. |
| `plot.box` | next | plot | artifact | Box plot. |
| `plot.violin` | planned | plot | artifact | Violin plot. |
| `plot.strip` | planned | plot | artifact | Strip plot. |
| `plot.swarm` | later | plot | artifact | Swarm plot. |
| `plot.rug` | later | plot | artifact | Rug plot. |
| `plot.qq` | planned | plot | artifact | Q-Q plot. |
| `plot.bar_counts` | next | plot | artifact | Category count bar chart. |
| `plot.bar_top_k` | next | plot | artifact | Top-k category bar chart. |
| `plot.pareto` | planned | plot | artifact | Pareto chart. |
| `plot.lorenz` | built | plot | artifact | Lorenz curve. |
| `plot.missingness_bar` | built | plot | artifact | Missingness by column. |
| `plot.text_length_histogram` | built | plot | artifact | Text length histogram. |

### Bivariate And Multivariate Plots

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `plot.scatter` | next | plot | artifact | Scatter plot. |
| `plot.scatter_sampled` | planned | plot | artifact | Sampled scatter for large data. |
| `plot.scatter_marginals` | planned | plot | artifact | Scatter with marginal distributions. |
| `plot.hexbin` | planned | plot | artifact | Hexbin density plot. |
| `plot.hist2d` | planned | plot | artifact | 2D histogram. |
| `plot.line` | next | plot | artifact | Line plot. |
| `plot.area` | planned | plot | artifact | Area plot. |
| `plot.bar_grouped` | planned | plot | artifact | Grouped bar chart. |
| `plot.bar_stacked` | planned | plot | artifact | Stacked bar chart. |
| `plot.box_by_category` | next | plot | artifact | Numeric distribution by category. |
| `plot.violin_by_category` | planned | plot | artifact | Violin by category. |
| `plot.heatmap_correlation` | built | plot | artifact | Correlation heatmap. |
| `plot.heatmap_crosstab` | planned | plot | artifact | Categorical crosstab heatmap. |
| `plot.pairplot` | planned | plot | artifact | Pairwise scatter/distribution grid. |
| `plot.parallel_coordinates` | later | plot | artifact | Parallel coordinates. |
| `plot.radar` | later | plot | artifact | Radar chart for small feature sets. |
| `plot.treemap` | later | plot | artifact | Hierarchical categorical quantities. |
| `plot.sankey` | later | plot | artifact | Flow between categories/states. |

### Time Plots

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `plot.records_over_time` | built | plot | artifact | Row count over time. |
| `plot.time_series` | next | plot | artifact | Value over time. |
| `plot.time_series_grouped` | planned | plot | artifact | Grouped time series. |
| `plot.rolling_window` | planned | plot | artifact | Rolling metric over time. |
| `plot.calendar_heatmap` | planned | plot | artifact | Calendar heatmap. |
| `plot.seasonality` | planned | plot | artifact | Seasonal profile. |
| `plot.acf` | planned | plot | artifact | Autocorrelation function. |
| `plot.pacf` | planned | plot | artifact | Partial autocorrelation. |
| `plot.change_points` | research | plot | artifact | Change point visualization. |

### Geospatial Plots

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `plot.geo_scatter` | planned | plot | artifact | Lat/lon scatter. |
| `plot.geo_density` | planned | plot | artifact | Spatial density/heatmap. |
| `plot.geo_choropleth` | planned | plot | artifact | Choropleth by polygon/region. |
| `plot.geo_hexbin` | planned | plot | artifact | Hexbin or H3 map. |
| `plot.geo_path` | later | plot | artifact | Paths/routes over map. |
| `plot.geo_cluster` | later | plot | artifact | Cluster map. |

### Model And Evaluation Plots

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `plot.roc_curve` | planned | plot | artifact | ROC curve. |
| `plot.pr_curve` | planned | plot | artifact | Precision-recall curve. |
| `plot.confusion_matrix` | planned | plot | artifact | Confusion matrix. |
| `plot.calibration_curve` | planned | plot | artifact | Calibration curve. |
| `plot.lift_curve` | planned | plot | artifact | Lift/gains curve. |
| `plot.residuals` | planned | plot | artifact | Residual plot. |
| `plot.predicted_vs_actual` | planned | plot | artifact | Regression actual vs predicted. |
| `plot.feature_importance` | built | plot | artifact | Feature importance bar in target lens. |
| `plot.permutation_importance` | planned | plot | artifact | Permutation importance. |
| `plot.shap_summary` | research | plot | artifact | SHAP summary. |
| `plot.partial_dependence` | research | plot | artifact | PDP. |
| `plot.ice` | research | plot | artifact | ICE curves. |
| `plot.learning_curve` | planned | plot | artifact | Learning curve. |
| `plot.validation_curve` | planned | plot | artifact | Validation curve. |

## Modeling Options

Modeling should be ledgered with explicit training state, target, feature set,
split strategy, random seed, hyperparameters, metrics, artifacts, and generated
prediction states.

### Modeling Setup

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `model.set_target` | planned | model | tree | Mark target column. |
| `model.set_features` | planned | model | tree | Mark feature columns. |
| `model.set_id_columns` | planned | model | tree | Mark ID/group columns. |
| `model.set_weight_column` | planned | model | tree | Mark sample weight column. |
| `model.set_time_column` | planned | model | tree | Mark time column. |
| `model.infer_task` | planned | analysis | artifact | Infer classification/regression/forecasting task. |
| `model.train_test_split` | planned | transform | state | Create train/test split indicators. |
| `model.time_split` | planned | transform | state | Time-based split. |
| `model.group_split` | planned | transform | state | Group-aware split. |
| `model.stratified_split` | planned | transform | state | Stratified split. |
| `model.cross_validation_plan` | planned | analysis | artifact | Define CV strategy. |
| `model.preprocessing_pipeline` | planned | model | artifact | Build preprocessing pipeline. |
| `model.baseline_plan` | next | model | artifact | Suggest baseline models. |

### Baselines And Supervised Models

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `model.baseline_mean` | planned | model | artifact | Regression mean baseline. |
| `model.baseline_median` | planned | model | artifact | Regression median baseline. |
| `model.baseline_majority_class` | planned | model | artifact | Classification majority baseline. |
| `model.baseline_stratified` | planned | model | artifact | Stratified random baseline. |
| `model.linear_regression` | planned | model | artifact | Linear regression. |
| `model.ridge` | planned | model | artifact | Ridge regression/classification. |
| `model.lasso` | planned | model | artifact | Lasso regression. |
| `model.elastic_net` | planned | model | artifact | Elastic Net. |
| `model.logistic_regression` | planned | model | artifact | Logistic regression. |
| `model.knn` | later | model | artifact | K-nearest neighbors. |
| `model.naive_bayes` | later | model | artifact | Naive Bayes. |
| `model.decision_tree` | planned | model | artifact | Decision tree. |
| `model.random_forest` | planned | model | artifact | Random forest. |
| `model.extra_trees` | planned | model | artifact | Extra Trees. |
| `model.gradient_boosting` | planned | model | artifact | Scikit-learn gradient boosting. |
| `model.hist_gradient_boosting` | planned | model | artifact | Histogram gradient boosting. |
| `model.xgboost` | later | model | artifact | XGBoost integration. |
| `model.lightgbm` | later | model | artifact | LightGBM integration. |
| `model.catboost` | later | model | artifact | CatBoost integration. |
| `model.svm` | later | model | artifact | Support vector machine. |
| `model.neural_mlp` | later | model | artifact | Basic neural network. |

### Unsupervised And Specialty Models

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `model.kmeans` | planned | model | artifact/state | K-means clustering plus cluster labels. |
| `model.dbscan` | planned | model | artifact/state | DBSCAN clustering. |
| `model.hdbscan` | later | model | artifact/state | HDBSCAN clustering. |
| `model.gaussian_mixture` | planned | model | artifact/state | Gaussian mixture clustering. |
| `model.pca` | planned | model/feature | artifact/state | PCA components and projection. |
| `model.umap` | later | model/feature | artifact/state | UMAP projection. |
| `model.tsne` | later | model/feature | artifact/state | t-SNE projection. |
| `model.isolation_forest` | planned | model | artifact/state | Anomaly scores/labels. |
| `model.one_class_svm` | later | model | artifact/state | One-class SVM. |
| `model.topic_lda` | research | model | artifact/state | Topic modeling. |
| `model.recommender_baseline` | research | model | artifact | Basic recommender model. |
| `model.survival_cox` | research | model | artifact | Cox survival model. |

### Forecasting

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `forecast.naive` | planned | model | artifact | Naive forecast. |
| `forecast.seasonal_naive` | planned | model | artifact | Seasonal naive forecast. |
| `forecast.moving_average` | planned | model | artifact | Moving average forecast. |
| `forecast.exponential_smoothing` | planned | model | artifact | Exponential smoothing. |
| `forecast.arima` | research | model | artifact | ARIMA/SARIMA. |
| `forecast.prophet` | later | model | artifact | Prophet integration. |
| `forecast.gradient_boosting` | planned | model | artifact | Feature-based ML forecast. |
| `forecast.backtest` | planned | analysis | artifact | Rolling-origin backtest. |
| `forecast.reconcile_hierarchy` | research | model | artifact | Hierarchical reconciliation. |

### Evaluation, Tuning, And Explainability

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `model.evaluate_classification` | planned | analysis | artifact | Classification metrics. |
| `model.evaluate_regression` | planned | analysis | artifact | Regression metrics. |
| `model.evaluate_forecast` | planned | analysis | artifact | Forecast metrics. |
| `model.evaluate_clustering` | planned | analysis | artifact | Clustering metrics. |
| `model.compare` | planned | analysis | artifact | Compare trained models. |
| `model.cross_validate` | planned | model/analysis | artifact | Cross-validated metrics. |
| `model.hyperparameter_search` | later | model | artifact | Grid/random/Bayesian search. |
| `model.threshold_tuning` | planned | analysis | artifact | Classification threshold tuning. |
| `model.calibrate_probabilities` | planned | model | artifact | Probability calibration. |
| `model.permutation_importance` | planned | analysis/plot | artifact | Permutation importance. |
| `model.partial_dependence` | research | analysis/plot | artifact | Partial dependence. |
| `model.shap` | research | analysis/plot | artifact | SHAP explanations. |
| `model.error_analysis` | planned | analysis | artifact | Segment-level model errors. |
| `model.fairness_report` | research | analysis | artifact | Fairness metrics by group. |
| `model.save_artifact` | planned | save | artifact | Save model artifact. |
| `model.load_artifact` | planned | save | none | Load model artifact. |
| `model.predict` | planned | model | state_and_artifact | Add predictions to a new state. |

## Reporting, Export, And Storytelling

The tree/web should eventually turn analysis paths into reports without losing
the exact provenance of each output.

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `report.branch_markdown` | planned | export | artifact | Export selected branch as Markdown. |
| `report.tree_markdown` | planned | export | artifact | Export whole tree as Markdown. |
| `report.branch_html` | planned | export | artifact | Export selected branch as HTML. |
| `report.tree_html` | planned | export | artifact | Export whole tree as HTML. |
| `report.executive_summary` | planned | export | artifact | Auto-generate executive summary from chosen nodes. |
| `report.data_quality` | planned | export | artifact | Data quality report. |
| `report.model_card` | planned | export | artifact | Model card. |
| `report.dataset_card` | planned | export | artifact | Dataset card. |
| `report.export_plots` | planned | export | artifact | Export selected plots as PNG/SVG/HTML. |
| `report.export_tables` | planned | export | artifact | Export selected tables. |
| `report.notebook_snippet` | planned | export | artifact | Generate code snippet to recreate state/output. |
| `report.replay_script` | next | export | artifact | Generate script to replay selected path. |
| `report.share_bundle` | later | export | artifact | Bundle metadata, selected data, and artifacts. |

## Recommendation Engine Options

Recommendations should be generated from state metadata, selected columns,
current user intent, prior actions, and ledger context.

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `recommend.top_next_actions` | built | analysis | none | Existing ranked recommendations. |
| `recommend.for_selected_column` | next | analysis | none | Actions relevant to selected column. |
| `recommend.for_selected_state` | built | analysis | none | Recommendations for selected tree state. |
| `recommend.for_goal` | planned | analysis | none | Recommendations based on user goal. |
| `recommend.after_action` | planned | analysis | none | Next actions after a run. |
| `recommend.batch_candidates` | next | analysis | none | Batch actions, such as histograms for all numeric columns. |
| `recommend.cleaning_plan` | built | analysis | artifact | Existing cleaning preview should become first-class plan. |
| `recommend.feature_plan` | planned | analysis | artifact | Feature engineering suggestions. |
| `recommend.modeling_plan` | planned | analysis | artifact | Modeling readiness and baseline suggestions. |
| `recommend.save_checkpoint` | next | save | artifact/tree | Suggest materializing important branch states. |
| `recommend.branch_cleanup` | planned | analysis | artifact | Suggest naming, notes, or branch pruning. |
| `recommend.learn_local_preferences` | research | web | web | Learn from local user behavior without external telemetry. |

## Notebook And Code Execution Options

The widget should prefer structured commands over arbitrary code execution. Code
generation should be transparent and copyable, but execution should happen
through registered actions.

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `code.copy_action_call` | next | export | none | Copy Python call for selected action. |
| `code.insert_action_cell` | planned | export | none | Insert notebook cell with action call where supported. |
| `code.copy_replay_path` | next | export | none | Copy code to recreate selected state. |
| `code.generate_pipeline` | planned | export | artifact | Generate reusable pipeline from branch. |
| `code.show_parameters` | next | view | none | Show exact params used by an action. |
| `code.show_source_diff` | planned | view | none | Show data/code diff for action result. |
| `code.safe_expression_filter` | planned | filter | state | Guarded expression-based filtering. |
| `code.advanced_python_action` | research | transform/analysis | state/artifact | User-defined function with explicit trust boundary. |

## Security, Privacy, And Governance Options

These are essential because the web/brain saves metadata and sometimes data
outside the kernel.

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `privacy.scan_sensitive_columns` | planned | analysis | artifact | Detect potential PII/sensitive columns. |
| `privacy.mask_columns` | planned | transform | state | Mask sensitive values. |
| `privacy.hash_columns` | planned | transform | state | Hash identifiers. |
| `privacy.redact_metadata` | planned | save | tree | Remove sensitive values from metadata. |
| `privacy.save_policy` | next | save | web | Configure what can be autosaved. |
| `privacy.data_snapshot_policy` | next | save | web | Explicit policy for Parquet materialization. |
| `privacy.encryption` | later | save | artifact | Encrypt saved metadata/data. |
| `privacy.audit_log` | planned | web | web | Record save/load/delete events. |
| `governance.data_contract` | planned | analysis | artifact | Contract definition and validation. |
| `governance.approval_marker` | later | web | tree | Mark branch/model/report as approved. |

## Extension And Plugin Options

stateframe should be open enough that new cleaning options, transforms, plots, and
models can be added without rewriting the core widget.

| Option id | Status | Kind | Ledger behavior | Description |
| --- | --- | --- | --- | --- |
| `registry.register_action` | next | web | web | Register a Python action with parameter schema. |
| `registry.unregister_action` | planned | web | web | Remove action from registry. |
| `registry.list_actions` | next | web | none | List available actions. |
| `registry.validate_action` | next | analysis | none | Validate action spec. |
| `registry.register_renderer` | next | web | web | Register visual/table/model renderer. |
| `registry.register_recommender` | planned | web | web | Register recommendation rule. |
| `registry.register_transform` | next | web | web | Register state-producing transform. |
| `registry.register_model` | planned | web | web | Register model action. |
| `registry.register_backend` | later | web | web | Register pandas/polars/duckdb/spark backend. |
| `registry.package_plugin` | later | export | artifact | Package a third-party action bundle. |
| `registry.import_plugin` | later | web | web | Import action bundle. |

## Histogram Interaction Target

This is the concrete target workflow that should guide the first clickable
action build.

User story:

1. User selects `sold_price` in the viewer or tree state.
2. UI recommends `Histogram`.
3. User opens the histogram action form.
4. User optionally adds a pre-filter: `sold_date` in year `2025`.
5. User optionally chooses a pre-transform: `clip` at 1st/99th percentile or
   `log1p`.
6. User chooses bins, grouping, scale, and whether to batch across numeric
   columns.
7. User clicks `Run`.
8. stateframe records the exact action under the selected state.
9. Output appears in the widget and in the tree detail panel.
10. User can later replay, export, or promote the pre-filter/transform to a
    real branch state.

Suggested spec:

```python
ActionSpec(
    id="plot.histogram",
    title="Histogram",
    family="plots",
    kind="plot",
    scope=["column", "columns", "state"],
    compatible_semantic_types=["numeric", "amount", "percentage", "proportion"],
    parameters=[
        ColumnParam("column", required=True),
        BooleanParam("batch_numeric", default=False),
        IntegerParam("bins", default="auto", min=5, max=200),
        EnumParam("scale", values=["linear", "log_count"], default="linear"),
        EnumParam("value_transform", values=["none", "log1p", "log", "sqrt"], default="none"),
        ObjectParam("clip", fields=["lower", "upper", "method"], optional=True),
        FilterParam("pre_filter", optional=True),
        ColumnParam("group_by", optional=True),
        BooleanParam("record_filtered_state", default=False),
    ],
    output_types=["visual", "metric_table", "insight"],
    ledger_behavior="artifact",
    replay_behavior="deterministic",
    can_batch=True,
    can_preview=True,
    cost="low",
)
```

Important design choice:

- If `record_filtered_state=False`, the filter/clip/log choices are recorded as
  part of the plot artifact only.
- If `record_filtered_state=True`, stateframe first creates a child state for the
  filter/transform, then records the histogram under that child state.

That distinction keeps quick exploration lightweight while still allowing users
to promote important analysis paths into durable branches.

## Suggested Build Order

This order gets us to the "click useful things from the UI" dream quickly while
keeping the architecture clean.

1. Build the generic `ActionSpec` and action registry.
2. Build parameter schema objects and UI form rendering.
3. Add widget-to-Python command bridge for structured actions.
4. Promote current lenses into registered actions.
5. Implement `plot.histogram` with pre-filter and pre-transform options.
6. Implement `viewer.save_branch_form` so branch naming happens in the widget.
7. Implement batch actions for all numeric/categorical columns.
8. Implement transform actions for `numeric.clip`, `numeric.log1p`,
   `category.top_k_other`, `columns.clean_names`, and `footprint.apply_plan`.
9. Attach rich plot artifacts to ledger entries.
10. Built: project-level `web.open` and snapshot-backed saved state restore.
11. Add plugin registration so external contributors can extend the registry.
12. Add modeling setup and baseline model actions after the data action system is
    stable.

## MVP Clickable Action Bundle

The first impressive UI release does not need every action above. It needs a
small set that proves the pattern.

High-impact MVP actions:

- `plot.histogram`
- `plot.histogram_batch`
- `plot.bar_counts`
- `plot.box`
- `plot.scatter`
- `relationships.correlation`
- `quality.missingness_matrix`
- `numeric.clip`
- `numeric.log1p`
- `category.top_k_other`
- `columns.clean_names`
- `footprint.apply_plan`
- `tree.save_state_data`
- `tree.replay_state`
- `web.restore_state`

With those in place, stateframe can demonstrate the full loop:

```text
select state -> choose action -> set params -> preview -> run
             -> attach artifact or create branch -> save -> restore later
```

That loop is the core of the larger dream.
