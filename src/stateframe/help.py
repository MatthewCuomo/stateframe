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


class StateframeHelp(str):
    """String help text that renders cleanly in notebooks."""

    def _repr_markdown_(self) -> str:
        return f"```text\n{str(self)}\n```"

    def __repr__(self) -> str:
        return str(self)


def help() -> StateframeHelp:
    """Return the stateframe quick-start guide."""

    return StateframeHelp(QUICK_START)


__all__ = ["QUICK_START", "StateframeHelp", "help"]
