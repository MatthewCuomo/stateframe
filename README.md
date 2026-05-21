# stateframe

[![CI](https://github.com/MatthewCuomo/stateframe/actions/workflows/ci.yml/badge.svg)](https://github.com/MatthewCuomo/stateframe/actions/workflows/ci.yml)

`stateframe` is an adaptive EDA library. It starts with a broad scan, infers what
kind of dataset it is looking at, ranks risks and opportunities, and recommends
the next useful diagnostic lenses.

This repo is still early, but the first deterministic scan engine is now in
place.

## Install

```powershell
pip install stateframe
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

## What The First Pass Does

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
scan.run("relationships.correlation")
scan.run("grain.keys")
scan.run("footprint.optimize")
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
state. Plot leaves store the plot spec, viewer draft summary, replay code, and a
PNG preview artifact.

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

Visual leaves store the declarative spec, Plotly HTML/JSON artifact, source
state, filters, options, notes, and replay code.

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
returned dataset, paste SQL, and run it into a saved tree. Use
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
