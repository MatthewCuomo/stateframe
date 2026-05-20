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

Stateframe can scan local files directly, and it can also start a tree from a
query result. The query system is a wrapper: stateframe defines the provider
interface and tree lineage, while you provide the code that talks to your
company warehouse, lakehouse, API, or internal service.


1. Register a quick function source

   import pandas as pd
   import stateframe as sf

   def run_company_query(query, params=None, **kwargs):
       # Put your company connection/session/client code here.
       # Return a pandas DataFrame, a to_pandas() object, or sf.QueryResult.
       return pd.read_sql(query, company_connection, params=params)

   sf.sources.register(
       "warehouse",
       run_company_query,
       display_name="Company warehouse",
       description="Internal analytics warehouse",
   )


2. Query it into a scan tree

   scan = sf.query(
       "warehouse",
       \"\"\"
       select *
       from analytics.customers
       where signup_date >= :start
       \"\"\",
       params={"start": "2025-01-01"},
       name="customers_2025",
       save_tree=True,
   )

   scan.summary()
   scan.recommendations().top(10)


3. Build a full provider when you need richer behavior

   class CompanyWarehouse(sf.DataSource):
       def __init__(self, connection):
           super().__init__(
               "warehouse",
               display_name="Company warehouse",
               description="Internal analytics warehouse",
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

   sf.sources.register(CompanyWarehouse(company_connection))


4. Keep secrets out of stateframe metadata

Stateframe stores source id, query text, params, execution time, provider class,
row/column counts, and a query fingerprint so the dataset root can be audited
or replayed later. It does not need credentials. Keep credentials in your own
provider, environment variables, keyring, notebook session, or company SDK.

Use these flags when query text or params are sensitive:

   scan = sf.query(
       "warehouse",
       sensitive_query,
       params=sensitive_params,
       store_query=False,
       store_params=False,
   )


5. How this fits the UI

The workspace web can show registered sources and later expose a Query Data
panel. The intended flow is:

   Get Data -> Query Data -> choose registered source -> preview -> run query
            -> stateframe creates a saved tree from the returned DataFrame

Files and queries share the same downstream model: the result starts a tree,
viewer changes become branches, and plots/reports can become leaf artifacts."""


class StateframeHelp(str):
    """String help text that renders cleanly in notebooks."""

    def _repr_markdown_(self) -> str:
        return f"```text\n{str(self)}\n```"

    def __repr__(self) -> str:
        return str(self)


def help() -> StateframeHelp:
    """Return the stateframe quick-start guide."""

    return StateframeHelp(QUICK_START)


def help_getdata() -> StateframeHelp:
    """Return the Get Data and custom query-source guide."""

    return StateframeHelp(GETDATA_GUIDE)


__all__ = ["GETDATA_GUIDE", "QUICK_START", "StateframeHelp", "help", "help_getdata"]
