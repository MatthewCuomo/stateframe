# stateframe Ledger, Viewer, Pull, Tree, And Save Commands

This document summarizes the current notebook-native workflow surface for
`stateframe`: opening data, shaping it in the viewer, pulling UI states back into
Python, navigating the analysis tree, running analysis from tree nodes, and
saving metadata/data checkpoints.

The mental model:

```text
scan data -> open viewer -> adjust UI state -> pull dataframe state
          -> inspect tree -> branch from any state -> save tree/data
```

## 1. Start A Scan

Basic scan:

```python
import stateframe as sf

scan = sf.scan(df)
```

Recommended when you have a meaningful dataset name:

```python
scan = sf.scan(
    df,
    name="realestate",
    target="sold_price",
    time="sold_date",
)
```

Recommended when you want restart-safe replay without saving every branch as
Parquet:

```python
scan = sf.scan_path(
    "data/realestate.csv",
    name="realestate",
    target="sold_price",
    time="sold_date",
)
```

If you already loaded the dataframe yourself, attach the base data path:

```python
realestate = pd.read_csv("data/realestate.csv")

scan = sf.scan(
    realestate,
    name="realestate",
    target="sold_price",
    time="sold_date",
    source_path="data/realestate.csv",
)
```

What happens internally:

- The input is coerced to a pandas DataFrame.
- Source metadata is captured when possible. File/path sources are replayable;
  raw in-memory DataFrame sources need `source_path=...` or an optional data
  snapshot for restart-safe restore.
- A `Profile` object is created.
- A `LensLedger` starts automatically with an initial `scan` entry.
- The profile is registered in the current workspace web, so `sf.web()`,
  `sf.workspace.list_trees()`, and `sf.save.tree()` can discover it later.

## 2. Open The DataFrame Viewer

From a scan:

```python
viewer = scan.view(height=720, max_rows=25_000)
viewer
```

Or directly:

```python
viewer = sf.view(df, name="realestate", height=720, max_rows=25_000)
viewer
```

Useful viewer helpers:

```python
viewer.current_state()
viewer.selected_column()
```

What happens internally:

- The widget receives a JSON payload with rows, columns, profiles, issues,
  recommendations, and current ledger metadata.
- Widget state is synced back to Python through traitlets.
- Filtering, sorting, hidden columns, selected column, global search, and column
  order live in `viewer.state`.

## 3. Pull A Viewer State Back Into Python

After making UI changes in the viewer, use `pull`.

Default:

```python
filtered = viewer.pull()
```

Recommended:

```python
martin_county = viewer.pull(
    name="Martin County",
    message="Filtered to Martin County and reordered price columns",
)
```

With a longer note:

```python
martin_county = viewer.pull(
    name="Martin County",
    message="Filtered to Martin County",
    note="This is the baseline branch for focused county-level real estate analysis.",
)
```

Preview without recording in the tree:

```python
preview = viewer.pull(record=False)
```

Compatibility alias:

```python
filtered = viewer.filtered_dataframe()
```

`filtered_dataframe()` still exists, but `pull()` is the preferred convention.

What happens internally:

- `apply_view_state(...)` reconstructs a DataFrame from the original scan data
  using the current widget state.
- `viewer.pull(...)` records that DataFrame as a ledger `state` entry.
- Pulls from the same viewer attach under the state that viewer was opened
  from. They do not automatically chain under the previous pull. To continue
  from a pulled state, select that state in the tree and call
  `tree.view_selected(...)`.
- The ledger entry stores:
  - operation: `viewer.pull`
  - UI filters
  - sort state
  - column order
  - hidden columns
  - selected column
  - output name
  - message/note
  - row/column counts and memory metadata
- The actual DataFrame checkpoint is held in memory until explicitly saved with
  `sf.save.data(...)` or `scan.save_data(...)`.

## 4. Explicitly Save The Current Viewer State

If you only want to record the UI-shaped state and do not need the DataFrame
returned:

```python
entry = viewer.save_current_view(
    name="martin_county",
    title="Martin County branch",
    message="Saved the UI-shaped Martin County subset",
)
```

Alias:

```python
entry = viewer.record_current_view(
    name="martin_county",
    message="Saved current viewer state",
)
```

The viewer also has a notebook UI path for this now: click **Save branch** in
the viewer toolbar, enter a branch name and optional message, then save. That
records the current viewer state to the ledger and saves the tree metadata.

What happens internally:

- The frontend sends a small `branch_request` to Python.
- Python applies the current viewer state to the backing DataFrame.
- A ledger `state` entry is recorded with operation `viewer.save_branch`.
- The tree is saved so the branch appears in the workspace web after refresh.

## 5. Open The Analysis Tree

From a scan:

```python
tree = scan.tree_view(height=720)
tree
```

Alias:

```python
tree = scan.ledger_view(height=720)
```

From the top-level API:

```python
tree = sf.tree_view(scan, height=720)
tree
```

Refresh after new pulls, saves, notes, or analysis:

```python
tree.refresh()
```

What happens internally:

- The tree widget is built from `scan.ledger.to_dict(...)`.
- Each ledger entry has a parent, so pulls and analyses form a tree.
- The selected tree node is synced back to Python.

## 6. Inspect Or Checkout The Selected Tree State

Click a node in the tree, then:

```python
tree.selected_entry_id()
tree.selected_entry()
tree.selected_state_id()
```

Return the selected node's DataFrame:

```python
selected_df = tree.checkout_selected()
```

Build a fresh scan/profile for the selected state:

```python
selected_scan = tree.selected_profile()
selected_scan.summary()
selected_scan.recommendations().top(10)
```

What happens internally:

- `checkout_selected()` uses the selected ledger entry/state id.
- The ledger returns the in-memory DataFrame checkpoint for that state.
- `selected_profile()` scans that checked-out DataFrame so recommendations
  reflect the selected state, not necessarily the original full dataset.

## 7. Open A Viewer From A Tree Node

Click a state node in the tree, then:

```python
branch_viewer = tree.view_selected(height=720)
branch_viewer
```

Make UI changes, then pull a new branch from that selected state:

```python
martin_adjusted_2 = branch_viewer.pull(
    name="martin_adjusted_2",
    message="Started from Martin County and made a second adjustment path",
)

tree.refresh()
```

If the selected node was `Martin County`, the new pull becomes a child of
`Martin County`. If `martin_adjusted` is also a child of `Martin County`, then
`martin_adjusted_2` becomes its sibling.

What happens internally:

- `tree.view_selected()` checks out the selected state.
- It opens a new viewer from that checked-out DataFrame.
- Pulls from that viewer are recorded back onto the original scan ledger.
- The pull's parent is the tree node that was selected when the viewer opened.

## 8. Run Analysis From A Tree Node

Click a node in the tree, then run a lens against that selected state:

```python
result = tree.run_selected("distribution.numeric", column="list_price")
tree.refresh()
```

Run the first recommendation for the selected state:

```python
result = tree.run_recommendation(1)
tree.refresh()
```

See selected-state recommendations:

```python
tree.recommendations().top(10)
```

What happens internally:

- `tree.run_selected(...)` checks out the selected DataFrame state.
- It builds a temporary profile for that state.
- It runs the lens against that temporary profile.
- It records the lens result under the selected node in the original ledger.

Current limitation:

- Recommendations shown in the widget are visible but not yet clickable actions.
- For now, click the node, then run `tree.run_selected(...)` or
  `tree.run_recommendation(...)` in a notebook cell.

## 9. Direct Ledger Commands On A Scan

Record a custom state:

```python
entry = scan.record_state(
    df2,
    title="Added engineered features",
    operation="features.add",
    note="Created rolling price features.",
)
```

Record a note:

```python
scan.record_note(
    "Modeling decision",
    "Use the Martin County branch as the baseline for target-aware analysis.",
)
```

Activate a branch point:

```python
scan.activate(entry.id)
```

Checkout a state by entry id or state id:

```python
df_back = scan.checkout(entry.id)
```

Get tree/path/report data:

```python
scan.ledger_tree()
scan.ledger_path()
scan.ledger_report("eda-ledger.md")
```

## 10. Custom Code Branches

Use this when you pull a state into a notebook, write your own Python, and want
that work to become a real branch instead of disappearing into a linear cell.

From a web-selected state:

```python
branch = sf.branch(web)
df = branch.input()

output = df[df["city"] == "Jupiter"].copy()
output["price_per_sqft"] = output["price"] / output["sqft"]

entry = branch.save_data(
    output,
    name="Jupiter price features",
    message="Filtered Jupiter and added price per sqft.",
    code="""
output = df[df["city"] == "Jupiter"].copy()
output["price_per_sqft"] = output["price"] / output["sqft"]
""",
)
```

From a scan/profile:

```python
branch = sf.branch(scan)
df = branch.input()

output = df.assign(log_price=np.log1p(df["sold_price"]))

entry = branch.save_data(
    output,
    name="log price feature",
    message="Added log1p sold price.",
    code='output = df.assign(log_price=np.log1p(df["sold_price"]))',
)
```

From a DataFrame that was pulled out of stateframe:

```python
df = web.pull_selected()
branch = sf.branch(df)
```

For replayable custom transforms, the stored code should follow this convention:

- `df` is the input DataFrame.
- `output` is the resulting DataFrame.
- Any imports the code needs should be included in the code string, except
  `pandas as pd` and `numpy as np`, which are provided during replay.

Record a custom plot, report, or analysis output:

```python
branch = sf.branch(web)
df = branch.input()

fig = px.histogram(df, x="sold_price")

entry = branch.save_plot(
    {"format": "plotly", "name": "sold_price histogram"},
    name="Sold price histogram",
    message="Distribution of sold price on the selected branch.",
    code="""
fig = px.histogram(df, x="sold_price")
artifact = fig
""",
)
```

What happens internally:

- `sf.branch(...)` resolves the parent tree node from a scan, web selection,
  viewer, or pulled DataFrame context.
- `branch.input()` returns the selected parent state as a DataFrame.
- `branch.save_data(...)` records a new ledger `state` child with operation
  `custom.transform`.
- The ledger stores the output name, message, parent id, and code in the tree
  metadata.
- If the code follows the `df -> output` convention, metadata-only replay can
  rebuild the branch from the original source path.
- `branch.save_plot(...)`, `branch.save_report(...)`, and
  `branch.save_artifact(...)` record non-DataFrame branch outputs under the
  selected state.
- Branch saves autosave the tree by default, so the workspace web can see them
  after refresh.

## 11. Cell Capture And Push

Use `%%sf_cell` when the cell itself starts from `sf.pull(...)`. Stateframe
infers dependency edges from those pull statements. If the cell creates a
DataFrame named `output`, it is recorded as a new branch; stdout, dataframe
previews, matplotlib figures, and Plotly figures are recorded as a code leaf:

```python
%%sf_cell --name "Jupiter price model" --save
df = sf.pull("state-entry_abc123")

output = df.assign(price_per_sqft=df["price"] / df["sqft"])
fig = px.histogram(output, x="price_per_sqft")
```

Multiple pulls are supported:

```python
%%sf_cell --name "Compare sibling branches"
left = sf.pull("state-entry_left")
right = sf.pull("state-entry_right")

output = left.merge(right, on="meter_number", suffixes=("_left", "_right"))
```

The branch is placed under the first pulled state and all pulled inputs are
stored in `entry.params["dependencies"]`.

For users without IPython magics:

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

For the shortest normal-code path:

```python
df = sf.pull("state-entry_abc123")
output = df.assign(price_per_sqft=df["price"] / df["sqft"])
entry = sf.push(output, name="Jupiter price model", save=True)
```

`sf.push(...)` uses recent `sf.pull(...)` calls as dependency edges. Pass
`parents=[df1, df2]` to be explicit for multi-input outputs.

## 12. Save And Run Reusable Flows

A flow is a reusable path extracted from a concrete tree:

```python
flow = sf.flow.from_tree(
    "meter A",
    name="meter inspection",
    entry_id="state-entry_abc123",
)
```

Run it on a new dataframe:

```python
result = flow.run(new_meter_df, name="meter B inspection")
```

When the source tree started from `sf.query(...)`, rerun the same query with new
parameters:

```python
result = flow.run(
    params={"meter_number": "MTR-912"},
    name="meter MTR-912 inspection",
)
```

The workspace web object exposes backend hooks for UI commands:

```python
web.save_selected_path_as_flow("meter inspection")
web.run_selected_flow("meter inspection", params={"meter_number": "MTR-912"})
```

## 13. Configure The Workspace

Default behavior creates `.stateframe/` in the current working directory. This is
the workspace memory for the project:

- `.stateframe/workspace.json` stores workspace settings.
- `.stateframe/web.json` stores the project-level web of all known trees.
- `.stateframe/trees/<tree_id>/tree.json` stores each dataset lifecycle tree.
- `.stateframe/data/<tree_id>/...` stores optional Parquet checkpoints.

Initialize a workspace once at the main project root:

```python
sf.workspace.configure(
    root="C:/path/to/DataScienceBase",
    name="my-data-science-base",
)
sf.workspace.init()
```

Then, from any nested notebook under that project root, connect upward to the
same workspace:

```python
sf.workspace.connect()

web = sf.web(height=720)
web
```

One-line notebook startup:

```python
web = sf.connect_web(height=720)
web
```

With explicit directories at initialization time:

```python
sf.workspace.configure(
    name="florida-real-estate-eda",
    tree_dir="analysis-trees",
    data_dir="analysis-data",
)
```

Inspect current save settings:

```python
sf.save.settings()
sf.workspace.settings()
```

What happens internally:

- The workspace name is stored separately from tree names.
- `sf.workspace.connect()` searches parent folders for
  `.stateframe/workspace.json`, like Git finding a repository root.
- Each scan gets a stable `tree_id`.
- Each tree also has an editable `tree_name`.
- Tree source paths under the workspace root are saved relative to that root, so
  notebooks can live in nested folders without breaking replay.
- If `name=` is omitted, stateframe makes a best-effort attempt to inherit the
  dataframe variable name used in `sf.scan(realestate)`.
- `sf.save.configure(session_name=...)` remains as a compatibility alias for
  setting the active workspace name.

## 14. Save Tree Metadata

Save all live scans/profiles in the current Python process:

```python
sf.save.tree()
```

Save specific scans:

```python
sf.save.tree(realestate_scan, weather_scan)
```

This writes one tree file per scan and updates `.stateframe/web.json`.

Save one scan:

```python
scan.save_tree()
```

Load saved metadata:

```python
payload = sf.save.load_tree(tree="realestate")
```

Inspect the web:

```python
web = sf.web(height=720)
web
sf.workspace.list_trees()
sf.workspace.web()
```

`sf.web()` opens the notebook widget for browsing all workspace trees.
`sf.workspace.web()` returns the raw persisted metadata dictionary.

Click a dataset tree in the web, then click a saved point inside that tree:

```python
web.selected_tree_id()
web.selected_entry_id()
web.selected_state_id()
web.selected_state_metadata()
```

The web widget is now the main one-stop UI. From it you can:

- select a dataset tree
- select a state inside that tree
- open the selected state in the embedded viewer
- filter, sort, reorder, and offload columns in that viewer
- click **Save Branch** to add a new child state to the same tree
- go back to the tree/web view and continue navigating

The equivalent Python method for the embedded UI action is:

```python
web.open_selected_viewer()
```

Pull the selected point into the notebook when it has a saved Parquet snapshot
or can be replayed from the root source:

```python
branch = web.pull_selected()
```

Short alias:

```python
branch = web.pull()
```

What happens internally:

- If the selected entry has a `data_snapshot` artifact, stateframe reads that
  Parquet file.
- Otherwise stateframe reloads the base source path and replays each saved
  operation from the root to the selected entry.
- Currently replay supports viewer pull/save-branch operations, replayable
  custom transforms, lenses/notes as no-op data steps, and root file loads.
- If the tree started from an in-memory DataFrame with no `source_path`, stateframe
  will ask you to set the tree source path before replay.

The older separate viewer method remains available:

```python
branch_viewer = web.view_selected(height=720)
branch_viewer
```

Pulls from `branch_viewer` are recorded under the selected saved tree node in a
restored live profile. Save that tree again after adding new branches:

```python
branch = branch_viewer.pull(
    name="new_branch",
    message="Started from a web-restored state",
)

branch_viewer.record_profile.save_tree()
```

Rename a tree without changing its stable id:

```python
scan.rename_tree("Florida Real Estate")
```

Update the editable base source path if the data file moved:

```python
scan.set_source_path("new-data/realestate.csv")
```

Or from the web selection:

```python
web.set_selected_tree_source_path("new-data/realestate.csv")
```

What `save.tree` writes:

- workspace settings
- stable tree id
- editable tree name
- save timestamp
- working directory
- dataset names
- source metadata
- profile summary/config/facts/recommendations
- complete ledger entries
- state metadata
- attached artifacts

What `save.tree` does not yet do:

- It does not materialize DataFrame data by itself.
- It does not guarantee arbitrary custom code is safe or portable. Custom
  transforms are replayable when recorded with code that follows the
  `df -> output` convention.
- Future transform registry actions still need dedicated replay handlers.
- In-memory DataFrame roots need `source_path=...` or `set_source_path(...)`
  before metadata-only restore can work.

## 15. Save Data Checkpoints

Save the selected tree state as Parquet:

```python
sf.save.data(tree, name="martin_adjusted_2")
```

Save a scan's active state:

```python
scan.save_data(name="current_branch")
```

Save a specific ledger entry:

```python
sf.save.data(scan, entry_id=entry.id, name="feature_branch")
```

Save a specific state id:

```python
sf.save.data(scan, state_id=state_id, name="materialized_state")
```

Load a Parquet checkpoint:

```python
df_saved = sf.save.load_data("analysis-data/florida-real-estate-eda/realestate/martin_adjusted_2.parquet")
```

What happens internally:

- The selected or specified state is checked out from the ledger.
- The DataFrame is written to Parquet.
- A small JSON sidecar is written next to it.
- A `data_snapshot` artifact is attached back to the ledger entry.
- By default, the tree metadata is saved again so the artifact reference is
  persisted.

## 16. Multi-Dataset Current State

Current supported pattern:

```python
realestate_scan = sf.scan(realestate, name="realestate")
weather_scan = sf.scan(weather, name="weather")

sf.save.tree()
```

This saves both scans as separate tree files and registers both in the
workspace web.

Current limitation:

- Each scan has its own ledger.
- The tree UI currently opens one scan/profile at a time.
- The project-level web UI now visualizes all saved trees, but cross-tree joins
  and merged lineage are still future work.

Needed next:

- richer dataset registry
- graph/DAG lineage for joins and merges
- clickable widget actions for running transforms/analyses without a follow-up
  Python cell

## 17. Current Persistence Reality

What is durable now:

- `sf.save.tree(...)` saves robust JSON metadata.
- `sf.save.data(...)` saves Parquet checkpoints.
- `.stateframe/web.json` persists the workspace-level tree registry.
- saved Parquet artifacts are referenced from ledger entries.
- `sf.web()` can browse persisted workspace trees and select saved entries.
- `web.pull_selected()` can load a selected saved data snapshot back into the
  notebook.
- `web.pull_selected()` can also replay saved viewer branches from an editable
  base source path without a data snapshot.
- `sf.branch(...)` can record user-code DataFrame branches and replay them when
  the saved code follows the `df -> output` convention.
- `sf.branch(...)` can record plot/report/artifact branches under a state.

What is still live-session only:

- The active widget object.
- Direct frontend assignment to a notebook variable. Click the desired point,
  then run `branch = web.pull_selected()`.
- Plot/report asset rendering inside the web is still early. Plot/report
  branches are recorded and visible as artifacts, but rich in-widget rerendering
  is a future pass.

Recommended workflow today:

```python
sf.workspace.configure(name="florida-real-estate-eda")

scan = sf.scan_path(
    "data/realestate.csv",
    name="realestate",
    target="sold_price",
    time="sold_date",
)
scan.save_tree()

web = sf.web(height=720)
web

# Select a state in the web, open the embedded viewer, save branches in the UI,
# then pull the selected point when you want a notebook variable.
branch = web.pull_selected()
```

This gives you both:

- metadata lineage in `tree.json`
- replayable selected states from the saved source path
