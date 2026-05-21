"""Small user-facing help text for stateframe."""

from __future__ import annotations


QUICK_START = """Stateframe quick start:
(Stateframe is native to ipynb, python in notebook format. A UI widget supports the basis of stateframe's function.)


1. Configure a Workspace  -->

   sf.workspace.configure(root="PATH_TO_PROJECT_ROOT", name="my-project")
   sf.workspace.init()

- This is the creation of your 'cloud' space. All dataloads and resulting states, as well as their analysis assets can be managed here. Configure once at the project root, then later notebooks below that root can reconnect with sf.workspace.connect().


__________


- After the workspace exists, your workflow will often be opening a new notebook, importing stateframe as sf, and running:


2. Open the Web  -->

   sf.workspace.connect()
   web = sf.web(height=720)
   web


__________


But, in order to load data and build a tree to manage in the web, you will scan and save a tree:


3. [SAVE DATA IN THE SYSTEM]  -->

   scan = sf.scan_path(
       "combined_sales_2015_2025_Sep.csv",
       name="realestate_raw",
   )

   scan.save_tree()


__________


- Once you have saved a tree, open up the web and check the initial stateframe in the viewer.

- Make changes to the stateframe in the viewer, then save a new branch.

- Now, anytime you open the web, that new state is available to pull.


__________


4. Pull Data from the Web

- From the web, select a tree, then a state. Now run:

   df = web.pull()
   df.head()


- Creation of a new dataframe with web.pull() will give you the dataframe of the state selected in the UI."""


GETDATA_GUIDE = """Stateframe Get Data and query-source setup:

Stateframe can scan local files directly, and it can also start a tree from any
existing Python code path that returns tabular data. The Query Data UI is a
wrapper around your code: the widget collects a text query and optional JSON
params, stateframe calls your registered provider in the current Python kernel,
then stateframe scans and saves the returned data.

Your provider owns credentials, drivers, SDK clients, SQL dialects, API calls,
access rules, retries, and row fetching. Stateframe owns only the provider
contract, import wiring, dataframe coercion, scan tree, and lineage metadata.
Saved connections store non-secret wiring: source id, display name, import
path, enabled flag, and query/params storage defaults.


1. Adapt your existing data entry point

If you already have code such as get_dataframe(sql), run_query(sql, params), or
client.fetch_report(payload), wrap it in a function with this shape:

   def run_company_query(query, params=None, **kwargs):
       ...
       return dataframe_like_result

The first argument is the text from the UI query box. It might be SQL, a report
name, a search expression, or another company-specific command. The optional
params argument comes from the UI Params JSON box. Return one of these:

   - a pandas DataFrame
   - an object with .to_pandas()
   - a supported local data path
   - sf.QueryResult(data=..., metadata={...}, name="optional_name")


2. Create a repo-local Python source file

   # company_query_source.py
   import pandas as pd
   import stateframe as sf

   from my_company_data import connect, execute_query

   def run_company_query(query, params=None, **kwargs):
       conn = connect()
       try:
           rows, columns = execute_query(conn, query, params=params or {})
           return sf.QueryResult(
               data=pd.DataFrame(rows, columns=columns),
               metadata={"system": "company-data"},
           )
       finally:
           conn.close()

   def register():
       return sf.sources.register(
           "company_warehouse",
           run_company_query,
           display_name="Company warehouse",
           description="Internal query source",
       )

The source id in sf.sources.register(...) must match the source id saved in the
connection. The file should live under the stateframe workspace root or be
importable on Python's module path.


3. Save the connection once

   sf.sources.save_connection(
       "company_warehouse",
       "company_query_source.py:register",
       display_name="Company warehouse",
       description="Internal query source",
       store_query=True,
       store_params=False,
   )

You can also do this from the UI:

   sf.web() -> Get Data -> Connections -> New
   sf.web() -> Get Data -> Query Data -> Configure Connection

Use an import path like one of these:

   company_query_source.py:register
   src/company_query_source.py:register
   company_query_source:register

After it is saved, future sf.web() and sf.query(...) calls auto-import the
connection. You do not need to import the file manually in every notebook.


4. Query it into a scan tree from the UI

   sf.workspace.connect()
   web = sf.web(height=720)
   web

In the widget:

   Get Data -> Query Data -> choose Company warehouse
            -> name the result
            -> paste the query text
            -> optionally paste params JSON
            -> Run Query

Stateframe sends the query text and params to your provider, waits for it to
return, converts the result into a DataFrame, scans it, saves a tree, refreshes
the web, and selects the new tree. The current UI shows run status while the
provider executes; it does not stream partial rows before the provider returns.


5. Query it into a scan tree from Python

   scan = sf.query(
       "company_warehouse",
       \"\"\"
       select *
       from analytics.customers
       where signup_date >= %(start)s
       \"\"\",
       params={"start": "2025-01-01"},
       name="customers_2025",
       save_tree=True,
   )

   scan.summary()
   scan.recommendations().top(10)

Connection storage defaults are reflected in the UI checkboxes. For direct
sf.query(...) calls, pass store_query=False or store_params=False explicitly
when the query text or params are sensitive.


6. Quick one-cell function registration is still supported

   def run_company_query(query, params=None, **kwargs):
       return pd.read_sql(query, company_connection, params=params)

   sf.sources.register(
       "warehouse",
       run_company_query,
       display_name="Company warehouse",
   )

This works for the current Python process, but it is not remembered after the
kernel restarts unless you save a connection profile with an import path.


7. Build a full provider when you need richer behavior

   class CompanyDataSource(sf.DataSource):
       def __init__(self, connection):
           super().__init__(
               "warehouse",
               display_name="Company warehouse",
               description="Internal analytics source",
           )
           self.connection = connection

       def list_objects(self, path=None):
           return [
               sf.DataObject(name="customers", path="analytics.customers"),
               sf.DataObject(name="orders", path="analytics.orders"),
           ]

       def preview(self, query, params=None, limit=100, **kwargs):
           limited = f"select * from ({query}) as q limit {int(limit)}"
           return sf.QueryResult(data=pd.read_sql(limited, self.connection, params=params))

       def execute(self, query, params=None, **kwargs):
           df = pd.read_sql(query, self.connection, params=params)
           return sf.QueryResult(
               data=df,
               metadata={"engine": "company-sql"},
           )

   sf.sources.register(CompanyDataSource(company_connection))

The Query Data run path calls execute(...). preview(...) and list_objects(...)
are available for Python use and richer provider integrations.


8. Keep secrets and drivers outside stateframe

Stateframe does not need credentials and does not install your warehouse, API,
or company SDK driver. Install those dependencies in the same environment as
the notebook kernel, and keep secrets in your provider, environment variables,
keyring, notebook session, or company SDK.

Stateframe stores source id, optional query text, optional params, param names,
execution time, provider class, row/column counts, provider metadata, and a
query fingerprint so the dataset root can be audited later.

Use these flags when query text or params are sensitive:

   scan = sf.query(
       "warehouse",
       sensitive_query,
       params=sensitive_params,
       store_query=False,
       store_params=False,
   )


9. Why this architecture works

Files and queries share the same downstream model: the result starts a tree,
viewer changes become branches, and plots/reports can become leaf artifacts.
Stateframe owns the orchestration. Your provider owns the system-specific
details needed to turn a query request into tabular data."""


TREE_WORKFLOW_GUIDE = """Stateframe tree pull/add workflow:

This guide is for moving between the UI tree and normal notebook code. The
basic pattern is:

   1. Select a branch/state/leaf in the UI.
   2. Pull it into a notebook cell.
   3. Do normal Python work.
   4. Add the result back to the same tree as a branch or leaf.


1. Open the workspace UI

   sf.workspace.connect()
   web = sf.web(height=720)
   web

The most recently opened web widget becomes the active UI for sf.pull().


2. Pull the selected item from the UI

Select a dataframe state in the tree, then run:

   df = sf.pull()

If the selected item is a dataframe state, sf.pull() returns a pandas
DataFrame. If the selected item is an output leaf, such as a plot/code/report
leaf, sf.pull() returns a renderable output object. Put it as the final
expression in a notebook cell to display it:

   sf.pull()


3. Pull a specific item by id

Every tree entry has a stable ledger id. The UI shows copyable pull code beside
each branch and leaf:

   df = sf.pull("state-entry_abc123")
   plot = sf.pull("plot_abc123")

Dataframe states return DataFrames. Plot/code/report leaves return renderable
output objects. This is the preferred way to jump directly to a saved point
without relying on what is currently selected in the UI.


4. Pull from the web object directly

The web object also supports the older selected-state helpers:

   df = web.pull_selected()
   df = web.pull()

Use sf.pull(...) when you want one public doorway for both dataframe states and
output leaves. Use web.pull() when you specifically want the current dataframe
viewer state and optionally want viewer edits recorded as a branch.


5. Add a dataframe branch from normal code

Use sf.branch(...) when your notebook code creates a new DataFrame and you want
that DataFrame added back into the tree as a new branch:

   custom = sf.branch(web)
   df = custom.input()

   output = df[df["city"] == "Jupiter"].copy()
   output["price_per_sqft"] = output["price"] / output["sqft"]

   custom.save_data(
       output,
       name="Jupiter price features",
       message="Filtered Jupiter and added price per sqft.",
       code=\"\"\"
output = df[df["city"] == "Jupiter"].copy()
output["price_per_sqft"] = output["price"] / output["sqft"]
\"\"\",
   )

The saved code should use df as the input DataFrame and assign the result to
output when you want the transform to be replayable later.


6. Add a plot/report/artifact leaf from normal code

If your code produces a plot, report, file, or other non-dataframe output, save
it as a leaf:

   custom = sf.branch(web)
   df = custom.input()

   fig = px.histogram(df, x="price")

   custom.save_plot(
       fig,
       name="Price distribution",
       message="Histogram of selected branch prices.",
       code=\"\"\"
fig = px.histogram(df, x="price")
\"\"\",
   )

Leaves sit under the selected branch and are meant to represent analysis
outputs: plots, reports, terminal output, notebooks snippets, and similar end
points.


7. Capture an entire code cell as a leaf

For quick notebook work, use sf.leaf(...) as a context manager:

   with sf.leaf(web, name="Jupiter price readout"):
       fig = px.histogram(df, x="price")
       fig.show()
       print("Jupiter price distribution")

In IPython/Jupyter, the cell magic captures everything in the cell:

   %%sf_leaf --parent Jupiter --name "Jupiter price readout"
   fig = px.histogram(df, x="price")
   fig.show()
   print("Jupiter price distribution")

The leaf stores the code and previews of captured outputs. If save mode is on,
stateframe can also persist output files under stateframe_saves/.


8. Save mode for durable outputs

Use save mode when you want the artifact or dataframe materialized on disk in
addition to the tree metadata:

   with sf.save_mode():
       with sf.leaf(web, name="Saved plot"):
           fig = px.histogram(df, x="price")
           fig.show()

For data states, use:

   sf.save.data(web, name="selected_state_snapshot")

Stateframe prefers saved Parquet/artifact files when pulling later. If no saved
file exists, it tries to replay the tree path from metadata.


9. What to remember

   sf.pull()                  -> pull/render the selected UI item
   sf.pull("entry_id")        -> pull/render a stable branch or leaf
   sf.branch(web).save_data() -> add a dataframe branch
   sf.branch(web).save_plot() -> add a plot leaf
   sf.leaf(web)               -> capture arbitrary code/output as a leaf

Branches are dataframe states. Leaves are output artifacts that hang under a
branch: plots, reports, terminal output, and custom code results."""


class StateframeHelp(str):
    """String help text that renders cleanly in notebooks."""

    def _repr_markdown_(self) -> str:
        return f"```text\n{str(self)}\n```"

    def __repr__(self) -> str:
        return str(self)


class StateframeHelpNamespace:
    """Callable help namespace exposed as ``sf.help``."""

    def __call__(self) -> StateframeHelp:
        """Return the stateframe quick-start guide."""

        return StateframeHelp(QUICK_START)

    def get_data(self) -> StateframeHelp:
        """Return the Get Data and custom query-source guide."""

        return StateframeHelp(GETDATA_GUIDE)

    def getdata(self) -> StateframeHelp:
        """Alias for ``get_data``."""

        return self.get_data()

    def tree_workflow(self) -> StateframeHelp:
        """Return the pull/add tree workflow guide."""

        return StateframeHelp(TREE_WORKFLOW_GUIDE)

    def pull_tree(self) -> StateframeHelp:
        """Alias for ``tree_workflow``."""

        return self.tree_workflow()


help = StateframeHelpNamespace()


def help_getdata() -> StateframeHelp:
    """Return the Get Data and custom query-source guide."""

    return help.get_data()


def help_tree() -> StateframeHelp:
    """Return the tree pull/add workflow guide."""

    return help.tree_workflow()


__all__ = [
    "GETDATA_GUIDE",
    "QUICK_START",
    "TREE_WORKFLOW_GUIDE",
    "StateframeHelp",
    "StateframeHelpNamespace",
    "help",
    "help_getdata",
    "help_tree",
]
