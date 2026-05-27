# stateframe

[![CI](https://github.com/MatthewCuomo/stateframe/actions/workflows/ci.yml/badge.svg)](https://github.com/MatthewCuomo/stateframe/actions/workflows/ci.yml)

`stateframe` is an adaptive EDA workbench for DataFrames. It starts with a broad
scan, infers what kind of dataset it is looking at, ranks risks and
opportunities, and turns those next steps into replayable cleaning, modeling,
visualization, and notebook provenance flows.

The project is still pre-1.0, but the current release is centered on the
workspace web UI: inspect a dataframe, branch useful states, clean or prepare
features, run modeling experiments, save visual/model leaves, and pull any
tracked state back into Python.

## Install

```powershell
pip install stateframe
```

For modeling experiments, estimator comparisons, and SHAP/permutation
explainability, install the machine-learning extra:

```powershell
pip install "stateframe[ml]"
```

XGBoost remains optional for users who want that estimator:

```powershell
pip install xgboost
```

```python
import pandas as pd
import stateframe as sf

df = pd.DataFrame({
    "customer_id": [1, 2, 3, 4],
    "signup_date": ["2024-01-01", "2024-01-02", "2024-01-10", "2024-01-11"],
    "churn": ["No", "No", "Yes", "No"],
    "email_opt_in": ["Y", "N", "Y", None],
    "total_charges": ["10.00", " ", "30.00", "40.00"],
})

scan = sf.scan(df, target="churn")

scan.summary()
scan.target_profile.summary()
scan.time_candidates()
scan.binary_flags()
scan.insights()
scan.recommendations().top(10)
scan.use_suggested().summary()
```

`sf.profile(...)` remains available as an alias-style entry point for users who
prefer the older name.

## Core Scan

- Profiles dataset shape, memory, duplicate rows, missing cells, and inferred
  column type counts.
- Builds rich column profiles with physical dtype, semantic type, confidence,
  alternative hypotheses, top values, missing-like strings, examples, and
  type-specific metrics.
- Separates dtype from semantic meaning: IDs, binary flags, datetime-like
  strings, numeric-like strings, text, URLs, email-like values, amounts,
  percentages, geographic columns, constants, and mostly-missing columns.
- Detects clean binary flags, nullable binary flags, and ambiguous `1/null`
  style flags.
- Suggests target columns and infers binary classification, multiclass
  classification, regression, time-aware EDA, text exploration, or
  unsupervised EDA.
- Detects likely time columns and routes them toward cadence analysis.
- Generates structured issues, insights, evidence facts, shape hypotheses, and
  ranked recommendations.
- Produces a conservative suggested config that can drive future reports or
  transformations.
- Reads common local file inputs: CSV, CSV.GZ, TSV, UCI `.data`, JSON, GeoJSON,
  parquet, Excel, and simple zip packages.

## Cleaning And Transform Operations

Cleaning plans are previewable operation specs rather than opaque helper calls:

```python
plan = scan.cleaning_plan()
plan.preview()
plan.operation_preview()

cleaned = plan.apply(binary_null_policy="treat_as_false")
clipped = plan.apply(outlier_policy="clip")
```

Actions include binary flag unification, ambiguous binary review, missing-like
tokens, true-null treatment, duplicate-row review, mixed-format datetime
parsing, numeric parsing, category variant review, numeric outlier
review/treatment, latitude/longitude anomaly review, and mass/manual column
renaming. Each action carries controls, risk, affected rows, examples, and
replay metadata.

Reusable transform helpers are also available for modeling prep:

```python
df2 = sf.clean_column_names(df, separator="_", case="lower")
df2 = sf.rename_columns(df2, {"old_name": "friendly_name"})
df2 = sf.impute_missing(df2, strategies={"price": "median"}, add_indicators=True)
df2 = sf.one_hot_encode(df2, ["county"], max_categories=20)
df2 = sf.scale_numeric(df2, ["price", "sqft"], method="robust")
df2 = sf.add_date_features(df2, ["sold_date"], features=["year", "quarter", "month"])
```

## Modeling Readiness

Modeling plans turn scan findings into editable feature-prep actions:

```python
scan = sf.scan(df, target="sold", goal="modeling")

plan = scan.modeling_plan()
plan.preview()
plan.operation_preview()

features = plan.apply()
scaled_features = plan.apply(scale="standard")
```

The planner reviews target setup, drops identifier/constant columns, imputes
missing features with optional indicators, one-hot encodes low-cardinality
categories, derives date features, suggests optional ratio features such as
price per square foot, and exposes optional scaling for models that need
comparable numeric ranges. It is also available as
`sf.modeling_plan(df)` and `scan.run("modeling.readiness")`.

For target-aware smoke testing, run a quick baseline lens:

```python
baseline = scan.run("modeling.baseline")
baseline.data["baseline_score"]
baseline.data["model_score"]
```

For configurable experiments, install `stateframe[ml]` and use a replayable
modeling spec. The experiment runner handles preprocessing, holdout splits,
cross-validation, optional grid search, estimator parameters, metrics, and
SHAP/permutation observability:

```python
result = scan.modeling_experiment({
    "estimator": "random_forest",
    "validation": {"strategy": "holdout_and_cv", "cv_folds": 5},
    "search": {"enabled": True},
    "explanation": {"enabled": True, "method": "auto"},
})

result.metrics
result.explanation["top_features"]
result.explanation["beeswarm"]
result.explanation["records"][0]["top_contributions"]
```

Supported experiment families include random forests, XGBoost when installed,
KNN, linear/logistic models, and clustering with k-means, agglomerative
clustering, or DBSCAN. The workspace modeling view exposes the same split,
fold, preprocessing, tuning, estimator, and observability controls. Supervised
classification results include precision, recall, F1, support, confusion
matrix, ROC and precision-recall curve data when available; SHAP results include
global feature rankings, beeswarm-ready rows, and per-record contribution lists
for individual row inspection. If SHAP is unavailable or unsuitable for a
specific model, automatic explanation falls back to permutation or model-native
importance. The web workbench renders these as first-class report panels:
metric tiles, confusion matrices, ROC/precision-recall curves, SHAP feature
bars, beeswarm-style distributions, and expandable per-record contribution
views.

## Lenses

Recommended analyses are executable:

```python
scan.run("quality.missingness")
scan.run("quality.type_coercion")
scan.run("time.cadence", column="signup_date")
scan.run("distribution.numeric", column="total_charges")
scan.run("categorical.value_counts", column="segment")
scan.run("binary.flags")
scan.run("target.balance")
scan.run("target.associations")
scan.run("target.best_splits")
scan.run("relationships.correlation")
scan.run("grain.keys")
scan.run("footprint.optimize")
scan.run("modeling.readiness")
scan.run("modeling.baseline")
```

You can also run the highest-ranked low/medium-cost recommendations:

```python
scan.run_top_recommendations(n=5, max_cost="medium")
```

## Interactive Web UI

The interactive UI ships with the base install. Stateframe is web-first:
`sf.web()` opens the full workspace, while `sf.view(...)` and
`scan.tree_view(...)` are focused launches into the same web UI. Use it directly
in VS Code, JupyterLab, or any notebook frontend that supports widgets:

```powershell
pip install stateframe
```

Then open a sortable, filterable, searchable dataframe viewer with column
reordering, hide/show controls, CSV export, and a stateframe-powered column
inspector. These calls open the shared web UI directly in viewer mode:

```python
viewer = sf.view(df, target="churn")

scan = sf.scan(df, target="churn")
scan.view()
```

Open the same web UI focused on one analysis tree to inspect the ledger,
state checkpoints, active path, plot leaves, and next options from each step:

```python
tree = scan.tree_view(height=720)
tree

tree.selected_entry()
df_at_selected_state = tree.checkout_selected()
```

The viewer keeps its UI state synced back to Python:

```python
viewer.current_state()
viewer.selected_column()
filtered = viewer.pull()
```

Calling `pull()` records the current UI-shaped DataFrame as a ledger checkpoint
by default, including filters, sorting, hidden columns, and column order. Add a
logical name and commit-style message when the branch matters:

```python
realestate_filtered = viewer.pull(
    name="realestate_filtered",
    message="County filter and reordered price columns",
)

tree = scan.tree_view(height=720)
tree
```

Pulls from the same viewer attach under the state that viewer was opened from.
To continue from a pulled state, select it in the tree and open a new viewer
with `tree.view_selected(...)`.

You can also save the current viewer state from the UI: click **Save branch** in
the viewer toolbar, enter a branch name and optional message, and stateframe
records/saves that branch without requiring a separate `viewer.pull(...)` cell.

Click any state in the tree, then reopen that exact dataframe state in the
viewer and pull a new branch from there:

```python
branch_viewer = tree.view_selected(height=720)
branch_viewer

martin_waterfront = branch_viewer.pull(
    name="martin_waterfront",
    message="Started from the Martin County branch and filtered waterfront rows",
)

tree.refresh()
```

Run analysis against the selected tree state and record the lens result beneath
that state:

```python
result = tree.run_selected("distribution.numeric", column="list_price")

# Or run the first recommendation for the selected state:
result = tree.run_recommendation(1)

tree.refresh()
```

The embedded workspace viewer also distinguishes saved data branches from plot
leaves. When a selected state is open in `sf.web()`, the top bar shows the saved
lineage plus the current unsaved viewer draft. Use the inspector's **Visualize**
section to save a first-click column plot as a leaf under the selected data
state. Use **Clean** or **Model** from a selected state to edit per-action
controls and apply previewed operation plans as new dataframe branches. Plot
leaves store the plot spec, viewer draft summary, replay code, and a PNG
preview artifact.

The larger Plotly visual builder is available from the workspace web and from an
opened dataframe state. Select a state and click **Visualizer** to open a
dashboard-style builder with a plot library, field wells, column browser,
filters, grouped/collapsible options, render previews, and **Save Leaf**:

```python
web = sf.web(height=720)
web.open_visualizer()

spec = {
    "kind": "bar",
    "title": "Segment sales",
    "fields": {"x": "segment", "y": "amount", "color": "segment"},
    "options": {"aggregation": "sum"},
    "filters": [{"column": "amount", "op": "greater_equal", "value": "100"}],
}

preview_artifact = web.render_visualizer(spec)
saved_leaf = web.render_visualizer(spec, save=True, note="## Readout\nSegment mix.")
```

The visualizer also suggests starter specs from the profile so broad chart
coverage stays approachable:

```python
for suggestion in scan.visual_recommendations(limit=6):
    print(suggestion.title, suggestion.spec.kind, suggestion.reason)

fig = sf.visualize(scan, scan.visual_recommendations()[0].spec.to_dict())
```

Visual leaves store the declarative spec, Plotly HTML/JSON artifact, source
state, filters, options, notes, and replay code. Visual specs include analyst
controls such as data min/max chops, date bucketing, axis transforms, sample or
dedupe-before-plot controls, missing-category display, histogram binning by
count/width/quantile, numeric X-axis binning for grouped box plots and bars,
top/bottom category handling, percent-of-total or percent-within-group value
transforms, rank transforms, weighted means, percentile aggregations, value
labels, rolling or cumulative line values, axis reversal, tick formatting, range
sliders, palettes, facet wrapping and shared-axis controls, and reference lines
or bands. The catalog spans distributions, comparisons, time trends,
composition, density plots, geographic maps, and multivariate views including
strip plots, density heatmaps/contours, sunbursts, choropleths, geo scatter
maps, parallel coordinates, parallel categories, Pareto charts, waterfall
charts, funnels, radar charts, Q-Q plots, autocorrelation bars, and cumulative
concentration/Lorenz-style curves. The workspace visual inspector keeps this
large option set navigable with basic/advanced/expert control modes, control
search, collapsible groups, and relevance filtering based on the selected
visual and bound fields.

The catalog also includes lollipop charts, slope charts, bump charts, and
calendar heatmaps for ranked comparisons, before/after change, rank movement,
and day-level intensity patterns. For multivariate review, it includes a
dedicated correlation heatmap and PCA scatter projection alongside scatter
matrices and parallel-coordinate views.

### Code leaves

Use code leaves to track arbitrary notebook analysis under a branch without
turning it into a dataframe branch:

```python
with sf.leaf(scan, parent="Jupiter", name="Jupiter price notes", save=True) as leaf:
    df = leaf.df
    print("Jupiter price distribution")
    output = df[["price"]].describe()
```

In Jupyter/IPython, load the extension once and capture a whole cell:

```python
%load_ext stateframe
```

```python
%%sf_leaf --source scan --parent Jupiter --name "Jupiter price plot" --save
fig = px.histogram(df, x="price")
fig.show()
print("Jupiter price distribution")
```

The cell magic injects `df` from the selected parent branch when possible. Code
leaves capture terminal output, dataframe previews, matplotlib images, and
Plotly payloads. With `--save` or `sf.save_mode(True)`, durable output files are
stored under `stateframe_saves/` at the workspace root.

For cells that start by pulling one or more saved states, use `%%sf_cell`.
Stateframe infers the parent branch from the `sf.pull(...)` line, saves a
dataframe named `output` as a new branch, and records every pulled input as a
dependency edge. If more than one pull is used, the branch is placed under the
first pulled state and the full dependency list is stored on the entry:

```python
%%sf_cell --name "Jupiter price model" --save
df = sf.pull("state-entry_abc123")

output = df.assign(price_per_sqft=df["price"] / df["sqft"])
fig = px.histogram(output, x="price_per_sqft")
```

The plain-Python equivalent works in editors, scripts, and notebook frontends
without cell magic support:

```python
sf.cell(
    """
df = sf.pull("state-entry_abc123")
output = df.assign(price_per_sqft=df["price"] / df["sqft"])
""",
    name="Jupiter price model",
    save=True,
    namespace=globals(),
)
```

For the shortest code path, pull a state, make a dataframe, then push it:

```python
df = sf.pull("state-entry_abc123")
output = df.assign(price_per_sqft=df["price"] / df["sqft"])

sf.push(output, name="Jupiter price model", save=True)
```

`sf.push(...)` uses recent `sf.pull(...)` calls as dependencies. Pass
`parents=[df1, df2]` when you want to be explicit about multi-input work.

### Reusable flows

Any saved path can be promoted into a reusable flow. A flow stores the replayable
steps from the root to the selected entry, including viewer states and custom
cell transforms:

```python
flow = sf.flow.from_tree(
    "meter A",
    name="meter inspection",
    entry_id="state-entry_abc123",
)
```

Run that flow on a new dataframe:

```python
result = flow.run(new_meter_df, name="meter B inspection")
result.data
```

Or rerun the original query root with new parameters when the tree started from
`sf.query(...)`:

```python
result = flow.run(params={"meter_number": "MTR-912"}, name="meter MTR-912")
```

Workspace web objects expose the same backend hooks:

```python
web.save_selected_path_as_flow("meter inspection")
web.run_selected_flow("meter inspection", params={"meter_number": "MTR-912"})
```

## Saving Trees And Data

By default, stateframe creates a workspace under `.stateframe/` in the current working
directory. The workspace contains a project web index, one saved tree per
initial dataset, and optional Parquet data checkpoints.

Initialize the workspace once at the main project folder:

```python
sf.workspace.configure(
    root="C:/path/to/DataScienceBase",
    name="my-data-science-base",
)
sf.workspace.init()
```

Then, from any notebook under that folder, connect upward to the nearest
workspace and open the web:

```python
sf.workspace.connect()
web = sf.web(height=720)
web

# Equivalent one-liner:
web = sf.connect_web(height=720)
```

Tree names inherit the scanned dataframe name when stateframe can infer it, or the
explicit `name=` passed to `sf.scan`. Names are editable without changing the
stable tree id:

```python
realestate = pd.read_csv("realestate.csv")
scan = sf.scan(realestate)

scan.rename_tree("Florida Real Estate")
```

For replay after a kernel restart, start from a path or attach the path to the
scan. This lets stateframe rebuild states from metadata instead of requiring a
Parquet snapshot:

```python
scan = sf.scan_path(
    "florida_realestate/data/realestate.csv",
    name="realestate",
    target="sold_price",
    time="sold_date",
)

# Equivalent when you already loaded the frame yourself:
scan = sf.scan(
    realestate,
    name="realestate",
    source_path="data/realestate.csv",
)
```

When the source file lives under the workspace root, stateframe stores the path
relative to that root, so notebooks can move around inside the project without
breaking replay.

If the base file moves, update the tree's editable source path without changing
the tree id:

```python
scan.set_source_path("new-data/realestate.csv")

# Or from a web selection:
web.set_selected_tree_source_path("new-data/realestate.csv")
```

Save the live tree metadata for all scans in the current process:

```python
sf.save.tree()
```

Or save one scan's tree metadata:

```python
scan.save_tree()
```

See the workspace web:

```python
web = sf.web(height=720)
web
sf.workspace.list_trees()
sf.workspace.web()
```

`sf.web()` opens the notebook widget. `sf.workspace.web()` returns the raw
backend metadata dictionary. In the widget, click a tree, then click a saved
entry/state inside that tree. The web is the main one-stop UI: open the
selected state in the embedded viewer, filter/sort/reorder/offload columns,
then click **Save Branch** to add a new child state to the tree.

To clean up the workspace web, use **Delete Mode** in the widget. Select trees
from the tree list or branches/leaves from the selected tree, then confirm the
delete action. Branch deletes remove the selected branch and its descendants
from the saved tree metadata; tree deletes remove the tree from the web index
by default while leaving saved data/artifact files on disk. The same cleanup is
available from Python:

```python
sf.workspace.delete_tree("Florida Real Estate")
sf.workspace.delete_tree_entries("Florida Real Estate", ["state-entry_abc123"])
```

The workspace also exposes a scoped file browser for dataset selection and
future save-as flows:

```python
sf.workspace.list_files()
sf.workspace.list_files("data")
sf.workspace.file_info("data/realestate.csv")
sf.workspace.validate_save_path("reports/price-plot.png")
```

Inside `sf.web()`, use **Get Data** to browse under the configured workspace
root and scan a supported data file into a saved tree. The browser is lazy and
workspace-scoped, so UI file operations stay inside the project root.

For company warehouses, APIs, lakehouses, or custom query systems, save a
connection profile that points to your repo-local Python wiring file. The
connection stores the import path, not credentials, and `sf.web()`/`sf.query()`
auto-import it later:

```python
# company_query_source.py
def run_company_query(query, params=None, **kwargs):
    return pd.read_sql(query, company_connection, params=params)

def register():
    return sf.sources.register(
        "warehouse",
        run_company_query,
        display_name="Company warehouse",
    )

sf.sources.save_connection(
    "warehouse",
    "company_query_source.py:register",
    display_name="Company warehouse",
)

scan = sf.query(
    "warehouse",
    "select * from analytics.customers where signup_date >= :start",
    params={"start": "2025-01-01"},
    name="customers_2025",
    save_tree=True,
)
```

Inside the widget, use **Get Data -> Query Data** to choose the source, name the
returned dataset, paste SQL, and run it into a saved tree. Saved query trees
materialize the returned root dataframe as Parquet so the viewer and `sf.pull()`
can reopen it later without rerunning the query. Pass `save_result=False` to
`sf.query(...)` when you want query metadata without a local data snapshot. Use
`sf.help.get_data()` or `sf.help_getdata()` for the full provider adapter
contract, UI flow, custom source classes, previews, object browsing, and
sensitive query metadata controls.

When you want the selected state as a notebook variable:

```python
branch = web.pull_selected()

# Short alias:
branch = web.pull()
```

`web.pull_selected()` first uses a saved Parquet snapshot when one exists. If no
snapshot exists, it reloads the tree's base source path and replays the saved
viewer operations along the selected path.

For the simplest notebook handoff, use `sf.pull(...)`:

```python
# Pull whatever state or output leaf is selected in the active UI.
thing = sf.pull()

# Pull a stable branch or leaf by its copied id.
thing = sf.pull("state-entry_abc123")
plot = sf.pull("plot_abc123")
```

Dataframe states return pandas DataFrames. Output leaves return a renderable
object, so a plot leaf displays in the notebook cell when `sf.pull("plot_...")`
is the final expression. The web UI surfaces the full pull code beside each
entry and leaf, with a copy button.

You can also open the same web-backed viewer focused on the selected state:

```python
branch_viewer = web.view_selected(height=720)
```

Custom notebook code can become a branch too. Create a recorder from the web,
scan, viewer, or a DataFrame pulled from stateframe, then save the output:

```python
custom = sf.branch(web)
df = custom.input()

output = df[df["city"] == "Jupiter"].copy()
output["price_per_sqft"] = output["price"] / output["sqft"]

custom.save_data(
    output,
    name="Jupiter price features",
    message="Filtered Jupiter and added price per sqft.",
    code="""
output = df[df["city"] == "Jupiter"].copy()
output["price_per_sqft"] = output["price"] / output["sqft"]
""",
)
```

For replayable custom transforms, saved code uses `df` as the input DataFrame
and assigns the resulting DataFrame to `output`. Plot/report branches can be
recorded with `custom.save_plot(...)`, `custom.save_report(...)`, or
`custom.save_artifact(...)`.

Materialize the selected tree state as an optional Parquet checkpoint for speed:

```python
sf.save.data(tree, name="martin_adjusted_2")
```

or save the active state from a scan:

```python
scan.save_data(name="current_branch")
```

`save.tree` records the metadata and lineage. `save.data` writes a Parquet file
and attaches that data snapshot back to the ledger entry so future restore work
can start from the saved checkpoint instead of replaying every step.

## Transform Helpers

Binary flag normalization and conservative type conversions are available as
copy-returning helpers:

```python
df2 = sf.unify_binary_flags(df, scan=scan)
df3 = sf.apply_suggested_conversions(df, scan.use_suggested())
```

Ambiguous nullable flags are preserved by default so stateframe does not silently
decide that null means false.

## Footprint Optimization

Preview safe memory optimizations before changing dtypes:

```python
plan = scan.footprint_plan()
plan.preview()
df_small = plan.apply()
```

Or apply the conservative defaults directly:

```python
df_small = sf.optimize_footprint(df)
```

The optimizer can convert repeated labels to `category`, downcast integer
columns, convert whole-number floats to nullable integers, and downcast floats
only when values round-trip through `float32` within tolerance.

## Lens Ledger

Every scan starts a lightweight ledger, and each executed lens appends to it:

```python
scan = sf.scan(df, target="sold_price")
scan.run("distribution.numeric", column="sold_price")
scan.run("footprint.optimize")
scan.record_note("Modeling baseline", "Use this branch for target-aware work.")

scan.ledger_tree()
scan.ledger_report("eda-ledger.md")
scan.tree_view(height=720)
```

Transform-style helpers can create dataframe checkpoints:

```python
df_small = scan.optimize_footprint()
df_back = scan.checkout(scan.ledger.active_entry_id)
```

The ledger is designed to act like a data-science activity log: a tree of scans,
lenses, notes, checkpoints, available next options, and reportable evidence.

## CLI

```powershell
stateframe profile path/to/data.csv --target churn --mode standard
```

The CLI accepts the same local file families as `sf.scan(...)`.
