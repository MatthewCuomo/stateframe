function render({ model, el, signal }) {
  let payload = model.get("payload") || {};
  let state = normalizeState(model.get("state"), payload);
  let viewer = normalizeViewer(model.get("viewer"));
  let files = normalizeFiles(model.get("files"));
  let commandStatus = model.get("command_status") || {};
  const ui = {
    saveBranchOpen: false,
    branchName: "",
    branchMessage: "",
    focus: null,
    activeMatchIndex: 0,
    lastGlobalSearch: "",
  };

  el.classList.add("stateframe-web-host");
  el.style.setProperty("--stateframe-web-height", `${payload.view?.height || 640}px`);

  const root = document.createElement("div");
  root.className = "stateframe-web";
  el.replaceChildren(root);

  function setState(patch) {
    captureFocus(root, ui);
    state = normalizeState({ ...state, ...patch }, payload);
    model.set("state", state);
    model.save_changes();
    draw();
  }

  function setViewerState(patch) {
    captureFocus(root, ui);
    const viewerPayload = viewer.payload || {};
    viewer = normalizeViewer({
      ...viewer,
      state: normalizeViewerState({ ...(viewer.state || {}), ...patch }, viewerPayload),
    });
    model.set("viewer", viewer);
    model.save_changes();
    draw();
  }

  function setUi(patch) {
    captureFocus(root, ui);
    Object.assign(ui, patch);
    draw();
  }

  function sendCommand(action, extra = {}) {
    model.set("command", {
      nonce: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      action,
      selectedTreeId: state.selectedTreeId,
      selectedEntryId: state.selectedEntryId,
      ...extra,
    });
    model.save_changes();
  }

  function openSelectedViewer() {
    viewer = { status: "loading", payload: null, state: {}, message: "Loading selected state" };
    model.set("viewer", viewer);
    model.save_changes();
    setState({ viewMode: "viewer" });
    sendCommand("open_viewer", {
      height: payload.view?.height || 640,
      maxRows: 500,
    });
  }

  function onPayloadChange() {
    payload = model.get("payload") || {};
    state = normalizeState(model.get("state"), payload);
    draw();
  }

  function onStateChange() {
    state = normalizeState(model.get("state"), payload);
    draw();
  }

  function onViewerChange() {
    viewer = normalizeViewer(model.get("viewer"));
    draw();
  }

  function onFilesChange() {
    files = normalizeFiles(model.get("files"));
    draw();
  }

  function onCommandStatusChange() {
    commandStatus = model.get("command_status") || {};
    draw();
  }

  model.on("change:payload", onPayloadChange);
  model.on("change:state", onStateChange);
  model.on("change:viewer", onViewerChange);
  model.on("change:files", onFilesChange);
  model.on("change:command_status", onCommandStatusChange);
  signal.addEventListener("abort", () => {
    model.off("change:payload", onPayloadChange);
    model.off("change:state", onStateChange);
    model.off("change:viewer", onViewerChange);
    model.off("change:files", onFilesChange);
    model.off("change:command_status", onCommandStatusChange);
  });

  function draw() {
    const trees = filteredTrees(payload.trees || [], state);
    const selected =
      getTree(payload.trees || [], state.selectedTreeId)
      || trees[0]
      || payload.trees?.[0]
      || null;
    const selectedEntry =
      getEntry(selected, state.selectedEntryId)
      || getEntry(selected, defaultEntryId(selected))
      || null;

    root.innerHTML = "";
    root.appendChild(renderToolbar(payload, state, setState, sendCommand, commandStatus, setUi, files));

    if (state.viewMode === "viewer") {
      root.appendChild(renderEmbeddedViewer(
        viewer,
        commandStatus,
        setViewerState,
        sendCommand,
        setState,
        ui,
        setUi,
      ));
      requestAnimationFrame(() => restoreFocus(root, ui));
      return;
    }

    if (state.viewMode === "files") {
      root.appendChild(renderFileBrowser(files, commandStatus, setState, sendCommand));
      requestAnimationFrame(() => restoreFocus(root, ui));
      return;
    }

    root.appendChild(renderStats(payload));
    const body = document.createElement("div");
    body.className = "stateframe-web-body";
    body.appendChild(renderTreeList(trees, selected, setState));
    body.appendChild(renderDetail(payload, selected, selectedEntry, setState, openSelectedViewer));
    root.appendChild(body);
    requestAnimationFrame(() => restoreFocus(root, ui));
  }

  draw();
}

function normalizeState(raw, payload) {
  const trees = payload.trees || [];
  const ids = new Set(trees.map((tree) => tree.tree_id));
  const selected = ids.has(raw?.selectedTreeId)
    ? raw.selectedTreeId
    : trees[0]?.tree_id || null;
  const selectedTree = getTree(trees, selected);
  const entryIds = new Set((selectedTree?.tree_detail?.entries || []).map((entry) => entry.id));
  const selectedEntry = entryIds.has(raw?.selectedEntryId)
    ? raw.selectedEntryId
    : defaultEntryId(selectedTree);
  const sorts = new Set(["updated", "name", "entries", "states"]);
  const modes = new Set(["web", "viewer", "files"]);
  return {
    selectedTreeId: selected,
    selectedEntryId: selectedEntry,
    viewMode: modes.has(raw?.viewMode) ? raw.viewMode : "web",
    selectedFilePath: raw?.selectedFilePath || null,
    search: raw?.search || "",
    sort: sorts.has(raw?.sort) ? raw.sort : "updated",
  };
}

function normalizeViewer(raw) {
  const payload = raw?.payload || null;
  return {
    status: raw?.status || (payload ? "ready" : "empty"),
    payload,
    state: payload ? normalizeViewerState(raw?.state, payload) : {},
    message: raw?.message || "",
    lastSavedEntryId: raw?.lastSavedEntryId || null,
  };
}

function normalizeViewerState(raw, payload) {
  const allIds = (payload.columns || []).map((column) => column.id);
  const rawOrder = Array.isArray(raw?.columnOrder) ? raw.columnOrder : [];
  const columnOrder = [
    ...rawOrder.filter((id) => allIds.includes(id)),
    ...allIds.filter((id) => !rawOrder.includes(id)),
  ];
  const hiddenColumnIds = Array.isArray(raw?.hiddenColumnIds)
    ? raw.hiddenColumnIds.filter((id) => allIds.includes(id))
    : [];
  const sorts = Array.isArray(raw?.sorts)
    ? raw.sorts.filter((sort) => allIds.includes(sort.id) && ["asc", "desc"].includes(sort.direction))
    : [];
  return {
    columnOrder,
    hiddenColumnIds,
    sorts,
    filters: raw?.filters || {},
    globalSearch: raw?.globalSearch || "",
    selectedColumnId: allIds.includes(raw?.selectedColumnId) ? raw.selectedColumnId : allIds[0] || null,
    showIndex: raw?.showIndex !== false,
    widths: raw?.widths || {},
  };
}

function normalizeFiles(raw) {
  return {
    status: raw?.status || "ready",
    purpose: raw?.purpose || "open",
    current_path: raw?.current_path || ".",
    parent_path: raw?.parent_path || null,
    entries: Array.isArray(raw?.entries) ? raw.entries : [],
    entry_count: Number(raw?.entry_count || 0),
    truncated: Boolean(raw?.truncated),
    supported_data_suffixes: Array.isArray(raw?.supported_data_suffixes) ? raw.supported_data_suffixes : [],
    workspace: raw?.workspace || {},
    message: raw?.message || "",
  };
}

function renderToolbar(payload, state, setState, sendCommand, commandStatus, setUi, files) {
  const toolbar = document.createElement("div");
  toolbar.className = "stateframe-web-toolbar";

  const titleGroup = document.createElement("div");
  titleGroup.className = "stateframe-web-title-group";
  const title = document.createElement("div");
  title.className = "stateframe-web-title";
  title.textContent = state.viewMode === "viewer"
    ? "stateframe embedded viewer"
    : state.viewMode === "files"
      ? "stateframe file browser"
      : payload.title || "stateframe workspace web";
  const subtitle = document.createElement("div");
  subtitle.className = "stateframe-web-subtitle";
  const workspaceName = payload.workspace?.name || payload.settings?.name || "workspace";
  subtitle.textContent = state.viewMode === "viewer"
    ? statusText(commandStatus) || "Open state from web, shape it, then save a branch"
    : state.viewMode === "files"
      ? `${workspaceName} / ${files.current_path || "."}`
    : `${workspaceName} / ${payload.settings?.root || ""}`;
  titleGroup.append(title, subtitle);

  const controls = document.createElement("div");
  controls.className = "stateframe-web-controls";

  if (state.viewMode === "viewer") {
    controls.classList.add("is-viewer");
    controls.append(
      button("Back", () => setState({ viewMode: "web" })),
      button("Save Branch", () => setUi({ saveBranchOpen: true })),
      button("Refresh", () => sendCommand("refresh")),
    );
  } else if (state.viewMode === "files") {
    controls.classList.add("is-viewer");
    const up = button("Up", () => sendCommand("browse_files", { path: files.parent_path || "." }));
    up.disabled = !files.parent_path;
    controls.append(
      button("Back", () => setState({ viewMode: "web" })),
      up,
      button("Refresh", () => sendCommand("browse_files", { path: files.current_path || "." })),
    );
  } else {
    const search = document.createElement("input");
    search.className = "stateframe-web-input";
    search.type = "search";
    search.placeholder = "Search trees, sources, columns";
    search.value = state.search || "";
    search.addEventListener("input", () => setState({ search: search.value }));

    const sort = document.createElement("select");
    sort.className = "stateframe-web-select";
    for (const [value, label] of [
      ["updated", "Recently updated"],
      ["name", "Name"],
      ["entries", "Entries"],
      ["states", "States"],
    ]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      sort.appendChild(option);
    }
    sort.value = state.sort;
    sort.addEventListener("change", () => setState({ sort: sort.value }));
    controls.append(
      search,
      sort,
      button("Get Data", () => {
        setState({ viewMode: "files" });
        sendCommand("browse_files", { path: files.current_path || "." });
      }),
      button("Refresh", () => sendCommand("refresh")),
    );
  }

  toolbar.append(titleGroup, controls);
  return toolbar;
}

function renderStats(payload) {
  const trees = payload.trees || [];
  const entries = sum(trees, "entry_count");
  const states = sum(trees, "state_count");
  const snapshots = trees.reduce((total, tree) => total + (tree.data_snapshots?.length || 0), 0);

  const row = document.createElement("div");
  row.className = "stateframe-web-stats";
  row.append(
    statCard("Trees", formatInt(trees.length)),
    statCard("Entries", formatInt(entries)),
    statCard("States", formatInt(states)),
    statCard("Snapshots", formatInt(snapshots)),
  );
  return row;
}

function statCard(label, value) {
  const card = document.createElement("div");
  card.className = "stateframe-web-stat";
  const valueEl = document.createElement("div");
  valueEl.className = "stateframe-web-stat-value";
  valueEl.textContent = value;
  const labelEl = document.createElement("div");
  labelEl.className = "stateframe-web-stat-label";
  labelEl.textContent = label;
  card.append(valueEl, labelEl);
  return card;
}

function renderTreeList(trees, selected, setState) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-panel";
  const header = document.createElement("div");
  header.className = "stateframe-web-panel-header";
  header.textContent = "Dataset Trees";
  panel.appendChild(header);

  if (!trees.length) {
    panel.appendChild(empty("No matching trees."));
    return panel;
  }

  const list = document.createElement("div");
  list.className = "stateframe-web-tree-list";
  for (const tree of trees) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "stateframe-web-tree-item";
    if (tree.tree_id === selected?.tree_id) item.classList.add("is-selected");
    item.addEventListener("click", () => setState({
      selectedTreeId: tree.tree_id,
      selectedEntryId: defaultEntryId(tree),
    }));

    const title = document.createElement("div");
    title.className = "stateframe-web-tree-title";
    title.textContent = tree.tree_name || tree.dataset_name || tree.tree_id;
    const meta = document.createElement("div");
    meta.className = "stateframe-web-tree-meta";
    meta.textContent = `${formatInt(tree.summary?.row_count || 0)} rows x ${formatInt(tree.summary?.column_count || 0)} columns`;
    const footer = document.createElement("div");
    footer.className = "stateframe-web-tree-footer";
    footer.append(
      pill(`${formatInt(tree.entry_count || 0)} entries`),
      pill(`${formatInt(tree.state_count || 0)} states`),
    );
    const snapshotCount = tree.tree_detail?.stats?.snapshot_count || tree.data_snapshots?.length || 0;
    if (snapshotCount) footer.append(pill(`${formatInt(snapshotCount)} snapshots`));
    item.append(title, meta, footer);
    list.appendChild(item);
  }
  panel.appendChild(list);
  return panel;
}

function renderFileBrowser(files, commandStatus, setState, sendCommand) {
  const shell = document.createElement("div");
  shell.className = "stateframe-web-files";

  const header = document.createElement("div");
  header.className = "stateframe-web-files-header";
  const title = document.createElement("div");
  title.className = "stateframe-web-files-title";
  title.textContent = files.current_path || ".";
  const meta = document.createElement("div");
  meta.className = "stateframe-web-files-meta";
  meta.textContent = `${formatInt(files.entry_count)} item${files.entry_count === 1 ? "" : "s"} / supported data: ${files.supported_data_suffixes.join(", ")}`;
  const actions = document.createElement("div");
  actions.className = "stateframe-web-action-row";
  const root = button("Workspace Root", () => sendCommand("browse_files", { path: "." }));
  const up = button("Up", () => sendCommand("browse_files", { path: files.parent_path || "." }));
  up.disabled = !files.parent_path;
  actions.append(root, up);
  header.append(title, meta, actions);
  shell.appendChild(header);

  if (commandStatus?.status === "loading" && commandStatus.action === "browse_files") {
    shell.appendChild(empty("Loading workspace folder..."));
    return shell;
  }
  if (commandStatus?.status === "loading" && commandStatus.action === "scan_file") {
    shell.appendChild(empty("Scanning selected dataset..."));
    return shell;
  }
  if (commandStatus?.status === "error") {
    const error = empty(commandStatus.message || "File action failed.");
    error.classList.add("is-error");
    shell.appendChild(error);
  }
  if (files.truncated) {
    const warning = document.createElement("div");
    warning.className = "stateframe-web-warning";
    warning.textContent = "This folder has more entries than the browser limit. Narrow the folder before scanning.";
    shell.appendChild(warning);
  }

  const list = document.createElement("div");
  list.className = "stateframe-web-file-list";
  if (files.parent_path) {
    list.appendChild(renderFileEntry(
      {
        name: "..",
        path: files.parent_path,
        kind: "directory",
        can_save_here: true,
      },
      setState,
      sendCommand,
    ));
  }
  for (const entry of files.entries || []) {
    list.appendChild(renderFileEntry(entry, setState, sendCommand));
  }
  if (!list.children.length) {
    shell.appendChild(empty("No files are visible in this workspace folder."));
  } else {
    shell.appendChild(list);
  }
  return shell;
}

function renderFileEntry(entry, setState, sendCommand) {
  const item = document.createElement("div");
  item.tabIndex = 0;
  item.setAttribute("role", "button");
  item.className = "stateframe-web-file-item";
  if (entry.kind === "directory") item.classList.add("is-directory");
  if (entry.can_scan) item.classList.add("is-data");
  const openEntry = () => {
    if (entry.kind === "directory") {
      sendCommand("browse_files", { path: entry.path || "." });
    } else {
      setState({ selectedFilePath: entry.path });
    }
  };
  item.addEventListener("click", openEntry);
  item.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openEntry();
    }
  });

  const main = document.createElement("div");
  main.className = "stateframe-web-file-main";
  const name = document.createElement("div");
  name.className = "stateframe-web-file-name";
  name.textContent = entry.name || entry.path || "";
  const meta = document.createElement("div");
  meta.className = "stateframe-web-file-meta";
  const kind = entry.kind === "directory" ? "folder" : entry.data_kind || entry.suffix || "file";
  meta.textContent = entry.kind === "directory"
    ? `${kind} / ${entry.path || "."}`
    : `${kind} / ${formatBytes(entry.size_bytes || 0)} / ${entry.path || ""}`;
  main.append(name, meta);

  const badges = document.createElement("div");
  badges.className = "stateframe-web-file-badges";
  badges.append(pill(entry.kind === "directory" ? "folder" : "file"));
  if (entry.can_scan) badges.append(pill("scan ready"));
  if (entry.can_save_here) badges.append(pill("save target"));

  const actions = document.createElement("div");
  actions.className = "stateframe-web-file-actions";
  if (entry.kind === "directory") {
    const open = button("Open", (event) => {
      event.stopPropagation();
      sendCommand("browse_files", { path: entry.path || "." });
    });
    actions.append(open);
  } else {
    const scan = button("Scan", (event) => {
      event.stopPropagation();
      sendCommand("scan_file", { path: entry.path });
    });
    scan.disabled = !entry.can_scan;
    actions.append(scan);
  }

  item.append(main, badges, actions);
  return item;
}

function renderDetail(payload, tree, selectedEntry, setState, openSelectedViewer) {
  const panel = document.createElement("aside");
  panel.className = "stateframe-web-detail";

  if (!tree) {
    panel.appendChild(empty("Select a tree to inspect it."));
    return panel;
  }

  const title = document.createElement("div");
  title.className = "stateframe-web-detail-title";
  title.textContent = tree.tree_name || tree.dataset_name || tree.tree_id;
  const subtitle = document.createElement("div");
  subtitle.className = "stateframe-web-detail-subtitle";
  subtitle.textContent = tree.tree_id;
  panel.append(title, subtitle);

  if (tree.tree_detail?.load_error) {
    const warning = document.createElement("div");
    warning.className = "stateframe-web-warning";
    warning.textContent = tree.tree_detail.load_error;
    panel.appendChild(warning);
  }

  panel.appendChild(section("Tree Entries", renderEntries(tree, selectedEntry, setState)));
  if (selectedEntry) {
    panel.appendChild(section("Selected State", renderEntryDetail(tree, selectedEntry, openSelectedViewer)));
  }
  panel.appendChild(section("Summary", keyValueList({
    Dataset: tree.dataset_name || "",
    Rows: formatInt(tree.summary?.row_count || 0),
    Columns: formatInt(tree.summary?.column_count || 0),
    Entries: formatInt(tree.entry_count || 0),
    States: formatInt(tree.state_count || 0),
    Target: tree.target || "",
    Time: tree.time || "",
    Updated: formatDate(tree.updated_at),
  })));
  panel.appendChild(section("Paths", keyValueList({
    Tree: tree.tree_path || "",
    Data: tree.data_dir || "",
    Source: sourceText(tree.source),
  })));
  if (tree.data_snapshots?.length) {
    panel.appendChild(section("Data Snapshots", renderSnapshots(tree.data_snapshots)));
  }
  panel.appendChild(section("Source Metadata", jsonBlock(tree.source || {})));
  return panel;
}

function renderEntries(tree, selectedEntry, setState) {
  const entries = tree.tree_detail?.entries || [];
  const list = document.createElement("div");
  list.className = "stateframe-web-entry-list";
  if (!entries.length) return empty("No saved tree entries are available yet.");

  for (const entry of entries) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "stateframe-web-entry-item";
    if (entry.id === selectedEntry?.id) item.classList.add("is-selected");
    if (entry.is_active) item.classList.add("is-active");
    item.style.setProperty("--entry-depth", String(Math.min(Number(entry.depth || 0), 8)));
    item.addEventListener("click", () => setState({ selectedEntryId: entry.id }));

    const top = document.createElement("div");
    top.className = "stateframe-web-entry-top";
    top.append(kindBadge(entry.kind), textSpan(entry.title || entry.operation || entry.id, "stateframe-web-entry-title"));
    const meta = document.createElement("div");
    meta.className = "stateframe-web-entry-meta";
    const stateText = entry.has_state ? "state" : "asset/no state";
    const childText = `${formatInt(entry.child_count || 0)} child${Number(entry.child_count || 0) === 1 ? "" : "ren"}`;
    meta.textContent = `${entry.operation || entry.kind || "entry"} / ${stateText} / ${childText}`;
    const footer = document.createElement("div");
    footer.className = "stateframe-web-entry-footer";
    if (entry.has_snapshot) footer.append(pill("pull ready"));
    else if (canReplayFromSource(tree, entry)) footer.append(pill("replay ready"));
    if (entry.is_active) footer.append(pill("active"));
    if (entry.note) footer.append(pill("note"));
    item.append(top, meta, footer);
    list.appendChild(item);
  }
  return list;
}

function renderEntryDetail(tree, entry, openSelectedViewer) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-entry-detail";
  if (entry.path?.length) {
    const path = document.createElement("div");
    path.className = "stateframe-web-path";
    for (const step of entry.path) path.appendChild(pill(step.title || step.operation || step.id));
    wrap.appendChild(path);
  }

  const actions = document.createElement("div");
  actions.className = "stateframe-web-action-row";
  const canOpen = entry.has_state && (entry.has_snapshot || canReplayFromSource(tree, entry) || entry.state?.has_data);
  const open = button("Open Viewer", openSelectedViewer);
  open.disabled = !canOpen;
  actions.append(open, codePill("df = web.pull_selected()"));
  wrap.appendChild(actions);

  wrap.appendChild(keyValueList({
    Entry: entry.id || "",
    Parent: entry.parent_id || "",
    Kind: entry.kind || "",
    Operation: entry.operation || "",
    Status: entry.status || "",
    Time: formatDate(entry.timestamp),
    State: entry.state_id || "",
  }));

  if (entry.state) {
    wrap.appendChild(section("Data State", keyValueList({
      Label: entry.state.label || "",
      Rows: formatInt(entry.state.row_count || 0),
      Columns: formatInt(entry.state.column_count || 0),
      Memory: formatBytes(entry.state.memory_bytes || 0),
      Materialized: entry.state.has_data ? "in saved tree" : "metadata only",
    })));
  }
  wrap.appendChild(hydrationCallout(tree, entry));
  if (entry.note) {
    const note = document.createElement("div");
    note.className = "stateframe-web-note";
    note.textContent = entry.note;
    wrap.appendChild(section("Note", note));
  }
  if (entry.params && Object.keys(entry.params).length) wrap.appendChild(section("Params", jsonBlock(entry.params)));
  if (entry.artifacts?.length) wrap.appendChild(section("Artifacts", jsonBlock(entry.artifacts)));
  return wrap;
}

function renderEmbeddedViewer(viewer, commandStatus, setViewerState, sendCommand, setState, ui, setUi) {
  const shell = document.createElement("div");
  shell.className = "stateframe-web-viewer";

  if (viewer.status === "loading") {
    shell.appendChild(empty("Loading selected state into the viewer..."));
    return shell;
  }
  if (viewer.status === "error") {
    const box = empty(viewer.message || commandStatus.message || "Could not open the selected state.");
    box.classList.add("is-error");
    shell.appendChild(box);
    return shell;
  }
  if (!viewer.payload) {
    shell.appendChild(empty("No embedded viewer is loaded yet. Go back, select a state, then open the viewer."));
    return shell;
  }

  const payload = viewer.payload;
  const viewerState = normalizeViewerState(viewer.state, payload);
  const computed = computeViewerRows(payload, viewerState);
  const query = viewerState.globalSearch || "";
  if (query !== ui.lastGlobalSearch) {
    ui.activeMatchIndex = 0;
    ui.lastGlobalSearch = query;
  }
  if (!computed.matches.length) {
    ui.activeMatchIndex = 0;
  } else {
    ui.activeMatchIndex = Math.min(ui.activeMatchIndex, computed.matches.length - 1);
  }
  const visibleColumns = visibleViewerColumns(payload, viewerState);
  const selectedColumn = getViewerColumn(payload, viewerState.selectedColumnId) || visibleColumns[0] || payload.columns?.[0];

  const top = document.createElement("div");
  top.className = "stateframe-web-viewer-top";
  const title = document.createElement("div");
  title.className = "stateframe-web-viewer-title";
  title.textContent = payload.title || "Selected dataframe state";
  const meta = document.createElement("div");
  meta.className = "stateframe-web-viewer-meta";
  meta.textContent = `${formatInt(computed.indices.length)} of ${formatInt(payload.view?.displayed_row_count || 0)} preview rows / source ${formatInt(payload.view?.row_count || 0)} rows`;

  const search = document.createElement("input");
  search.className = "stateframe-web-input";
  search.type = "search";
  search.placeholder = "Find and filter visible data";
  search.dataset.focusKey = "embedded-viewer-search";
  search.value = viewerState.globalSearch || "";
  search.addEventListener("input", () => setViewerState({ globalSearch: search.value }));

  const matchCount = document.createElement("span");
  matchCount.className = "stateframe-web-match-count";
  matchCount.textContent = viewerState.globalSearch
    ? (computed.matches.length ? `${ui.activeMatchIndex + 1}/${computed.matches.length}` : "0 matches")
    : "Find";
  const previousMatch = button("Prev", () => navigateEmbeddedMatch(-1, computed, ui, setUi, setViewerState, viewerState));
  previousMatch.disabled = !computed.matches.length;
  const nextMatch = button("Next", () => navigateEmbeddedMatch(1, computed, ui, setUi, setViewerState, viewerState));
  nextMatch.disabled = !computed.matches.length;
  const save = button("Save Branch", () => setUi({ saveBranchOpen: true }));
  const clear = button("Clear", () => setViewerState({
    hiddenColumnIds: [],
    filters: {},
    globalSearch: "",
    sorts: [],
  }));
  const loadFull = button("Load Full", () => {
    sendCommand("open_viewer", {
      height: payload.view?.height || 640,
      maxRows: "all",
      viewerState,
    });
  });
  loadFull.disabled = !payload.view?.truncated;
  loadFull.title = payload.view?.truncated
    ? "Send all rows for this selected state to the browser preview."
    : "All rows are already loaded in the browser preview.";
  top.append(title, meta, search, matchCount, previousMatch, nextMatch, clear, loadFull, save);
  shell.appendChild(top);

  if (commandStatus?.status === "saved") {
    const saved = document.createElement("div");
    saved.className = "stateframe-web-status is-saved";
    saved.textContent = `Saved: ${commandStatus.title || commandStatus.entry_id || "branch"}`;
    shell.appendChild(saved);
  } else if (commandStatus?.status === "error") {
    const error = document.createElement("div");
    error.className = "stateframe-web-status is-error";
    error.textContent = commandStatus.message || "Action failed";
    shell.appendChild(error);
  }

  const body = document.createElement("div");
  body.className = "stateframe-web-viewer-body";
  body.append(
    renderViewerColumns(payload, viewerState, setViewerState),
    renderViewerGrid(payload, viewerState, computed, visibleColumns, setViewerState, ui),
    renderViewerInspector(payload, viewerState, selectedColumn, setViewerState),
  );
  shell.appendChild(body);

  if (ui.saveBranchOpen) {
    shell.appendChild(renderSaveBranchDialog(viewerState, sendCommand, ui, setUi));
  }
  return shell;
}

function renderViewerColumns(payload, state, setViewerState) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-viewer-columns";
  const header = document.createElement("div");
  header.className = "stateframe-web-panel-header";
  header.textContent = "Columns";
  panel.appendChild(header);

  const ordered = orderedViewerColumns(payload, state);
  const hidden = new Set(state.hiddenColumnIds || []);
  const list = document.createElement("div");
  list.className = "stateframe-web-viewer-column-list";
  ordered.forEach((column, index) => {
    const row = document.createElement("div");
    row.className = "stateframe-web-viewer-column";
    if (column.id === state.selectedColumnId) row.classList.add("is-selected");
    if (hidden.has(column.id)) row.classList.add("is-hidden");
    const name = document.createElement("button");
    name.type = "button";
    name.className = "stateframe-web-column-name";
    name.textContent = column.display_name || column.source_name || column.id;
    name.addEventListener("click", () => setViewerState({ selectedColumnId: column.id }));
    row.append(
      name,
      tinyButton("Up", () => setViewerState({ columnOrder: moveId(state.columnOrder, column.id, -1) }), index === 0),
      tinyButton("Down", () => setViewerState({ columnOrder: moveId(state.columnOrder, column.id, 1) }), index === ordered.length - 1),
      tinyButton(hidden.has(column.id) ? "Load" : "Offload", () => {
        const next = hidden.has(column.id)
          ? state.hiddenColumnIds.filter((id) => id !== column.id)
          : [...state.hiddenColumnIds, column.id];
        setViewerState({ hiddenColumnIds: next });
      }),
    );
    list.appendChild(row);
  });
  panel.appendChild(list);
  return panel;
}

function renderViewerGrid(payload, state, computed, visibleColumns, setViewerState, ui) {
  const wrap = document.createElement("section");
  wrap.className = "stateframe-web-viewer-grid";
  const table = document.createElement("table");
  table.className = "stateframe-web-table";
  const activeMatch = computed.matches[ui.activeMatchIndex] || null;
  const searchNeedle = String(state.globalSearch || "").trim().toLowerCase();
  const thead = document.createElement("thead");
  const header = document.createElement("tr");
  if (state.showIndex) header.appendChild(th("#"));
  for (const column of visibleColumns) {
    const cell = th(column.display_name || column.source_name || column.id);
    cell.addEventListener("click", () => setViewerState({
      selectedColumnId: column.id,
      sorts: nextSorts(state.sorts, column.id),
    }));
    header.appendChild(cell);
  }
  thead.appendChild(header);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  const limit = 500;
  const activeVirtualIndex = activeMatch?.virtualIndex ?? 0;
  const start = activeVirtualIndex >= limit ? Math.max(0, activeVirtualIndex - 25) : 0;
  const rows = computed.indices.slice(start, start + limit);
  for (const rowIndex of rows) {
    const tr = document.createElement("tr");
    if (state.showIndex) tr.appendChild(td(payload.index?.[rowIndex] ?? rowIndex));
    for (const column of visibleColumns) {
      const value = valueFor(payload, rowIndex, column);
      const cell = td(value);
      if (searchNeedle && cellMatches(value, searchNeedle)) {
        cell.classList.add("is-search-match");
      }
      if (
        activeMatch
        && activeMatch.rowIndex === rowIndex
        && activeMatch.columnId === column.id
      ) {
        cell.classList.add("is-active-match");
      }
      tr.appendChild(cell);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  if (computed.indices.length > limit) {
    const note = document.createElement("div");
    note.className = "stateframe-web-grid-note";
    const end = Math.min(computed.indices.length, start + limit);
    note.textContent = `Showing rows ${formatInt(start + 1)}-${formatInt(end)} of ${formatInt(computed.indices.length)} matched preview rows. Save branch still applies the full viewer state in Python.`;
    wrap.appendChild(note);
  }
  return wrap;
}

function renderViewerInspector(payload, state, column, setViewerState) {
  const inspector = document.createElement("aside");
  inspector.className = "stateframe-web-viewer-inspector";
  if (!column) {
    inspector.appendChild(empty("Select a column."));
    return inspector;
  }

  const title = document.createElement("div");
  title.className = "stateframe-web-viewer-inspector-title";
  title.textContent = column.display_name || column.source_name || column.id;
  const meta = document.createElement("div");
  meta.className = "stateframe-web-viewer-meta";
  meta.textContent = `${column.semantic_type || "unknown"} / ${column.dtype || ""}`;
  inspector.append(title, meta);

  inspector.appendChild(renderViewerStats(column));

  const actions = document.createElement("div");
  actions.className = "stateframe-web-action-row";
  actions.append(
    button("Sort Asc", () => setViewerState({ sorts: [{ id: column.id, direction: "asc" }] })),
    button("Sort Desc", () => setViewerState({ sorts: [{ id: column.id, direction: "desc" }] })),
  );
  inspector.appendChild(actions);

  inspector.appendChild(section("Filter", renderViewerFilter(column, state, setViewerState)));
  if (column.histogram) inspector.appendChild(section("Spread", renderHistogram(column.histogram)));
  if (column.binary_profile) {
    inspector.appendChild(section("Binary Flag", keyValueList({
      Kind: column.binary_profile.kind,
      Confidence: formatPercent(column.binary_profile.confidence),
      Nulls: column.binary_profile.null_policy,
      Ambiguous: column.binary_profile.ambiguous ? "yes" : "no",
    })));
  }
  if (column.datetime_range) inspector.appendChild(section("Time Range", keyValueList(column.datetime_range)));
  if (column.top_values?.length) inspector.appendChild(section("Top Values", renderTopValues(column.top_values)));
  if (column.issues?.length) inspector.appendChild(section("Issues", renderBullets(column.issues.map((issue) => issue.title))));
  if (column.insights?.length) inspector.appendChild(section("Insights", renderBullets(column.insights.map((insight) => insight.message))));
  if (column.metrics && Object.keys(column.metrics).length) inspector.appendChild(section("Metrics", keyValueList(column.metrics)));
  if (column.recommendations?.length) inspector.appendChild(section("Recommendations", renderColumnRecommendations(column.recommendations)));
  return inspector;
}

function renderViewerStats(column) {
  const stats = document.createElement("div");
  stats.className = "stateframe-web-stats-grid";
  const items = [
    ["Missing", `${formatInt(column.missing_count)} (${formatPercent(column.missing_ratio)})`],
    ["Unique", `${formatInt(column.distinct_count)} (${formatPercent(column.distinct_ratio)})`],
    ["Non-null", formatInt(column.non_null_count)],
    ["Role", column.role || "feature"],
    ["Confidence", formatPercent(column.semantic_confidence)],
  ];
  for (const [label, value] of items) {
    const card = document.createElement("div");
    card.className = "stateframe-web-mini-stat";
    const statLabel = document.createElement("div");
    statLabel.className = "stateframe-web-mini-stat-label";
    statLabel.textContent = label;
    const statValue = document.createElement("div");
    statValue.className = "stateframe-web-mini-stat-value";
    statValue.textContent = value;
    card.append(statLabel, statValue);
    stats.appendChild(card);
  }
  return stats;
}

function renderViewerFilter(column, state, setViewerState) {
  const filter = state.filters?.[column.id] || {};
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-filter";
  const semantic = column.semantic_type || "";
  if (semantic.includes("numeric") || ["amount", "percentage", "proportion"].includes(semantic)) {
    const min = filterInput("Min", filter.min ?? "", (value) => setColumnFilter(column.id, { ...filter, kind: "numeric", min: value }, state, setViewerState), `filter-${column.id}-min`);
    const max = filterInput("Max", filter.max ?? "", (value) => setColumnFilter(column.id, { ...filter, kind: "numeric", max: value }, state, setViewerState), `filter-${column.id}-max`);
    wrap.append(min, max);
  } else if (semantic.includes("datetime")) {
    const min = filterInput("Start", filter.min ?? "", (value) => setColumnFilter(column.id, { ...filter, kind: "datetime", min: value }, state, setViewerState), `filter-${column.id}-start`);
    const max = filterInput("End", filter.max ?? "", (value) => setColumnFilter(column.id, { ...filter, kind: "datetime", max: value }, state, setViewerState), `filter-${column.id}-end`);
    wrap.append(min, max);
  } else {
    const mode = document.createElement("select");
    mode.className = "stateframe-web-select";
    for (const value of ["contains", "equals", "starts"]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      mode.appendChild(option);
    }
    mode.value = filter.mode || "contains";
    mode.addEventListener("change", () => setColumnFilter(column.id, { ...filter, kind: "text", mode: mode.value }, state, setViewerState));
    const text = filterInput("Value", filter.value ?? "", (value) => setColumnFilter(column.id, { ...filter, kind: "text", mode: mode.value, value }, state, setViewerState), `filter-${column.id}-value`);
    wrap.append(mode, text);
  }
  wrap.append(button("Clear Filter", () => clearColumnFilter(column.id, state, setViewerState)));
  return wrap;
}

function renderColumnRecommendations(recommendations) {
  const list = document.createElement("div");
  list.className = "stateframe-web-recs";
  for (const rec of recommendations.slice(0, 6)) {
    const item = document.createElement("div");
    item.className = "stateframe-web-rec";
    item.append(
      textSpan(rec.title || rec.id || "recommendation", "stateframe-web-rec-title"),
      codePill(rec.code || rec.lens || rec.id || ""),
    );
    list.appendChild(item);
  }
  return list;
}

function renderHistogram(histogram) {
  const chart = document.createElement("div");
  chart.className = "stateframe-web-histogram";
  for (const bin of histogram.bins || []) {
    const bar = document.createElement("div");
    bar.className = "stateframe-web-histogram-bar";
    const height = histogram.max_count ? Math.max(4, (bin.count / histogram.max_count) * 72) : 4;
    bar.style.height = `${height}px`;
    bar.title = `${formatNumber(bin.lower)} to ${formatNumber(bin.upper)}: ${formatInt(bin.count)}`;
    chart.appendChild(bar);
  }
  return chart;
}

function renderTopValues(topValues) {
  const list = document.createElement("div");
  list.className = "stateframe-web-top-values";
  for (const item of topValues.slice(0, 12)) {
    const row = document.createElement("div");
    row.className = "stateframe-web-top-value";
    const value = document.createElement("span");
    value.className = "stateframe-web-top-value-name";
    value.textContent = formatCell(item.value);
    const count = document.createElement("span");
    count.className = "stateframe-web-top-value-count";
    count.textContent = `${formatInt(item.count)} ${item.ratio !== undefined ? formatPercent(item.ratio) : ""}`;
    row.append(value, count);
    list.appendChild(row);
  }
  return list;
}

function renderBullets(items) {
  const list = document.createElement("ul");
  list.className = "stateframe-web-bullets";
  for (const item of items.slice(0, 8)) {
    const li = document.createElement("li");
    li.textContent = String(item || "");
    list.appendChild(li);
  }
  return list;
}

function renderSaveBranchDialog(viewerState, sendCommand, ui, setUi) {
  const overlay = document.createElement("div");
  overlay.className = "stateframe-web-dialog-overlay";
  const dialog = document.createElement("div");
  dialog.className = "stateframe-web-dialog";
  const title = document.createElement("div");
  title.className = "stateframe-web-dialog-title";
  title.textContent = "Save Branch";
  const name = document.createElement("input");
  name.className = "stateframe-web-input";
  name.placeholder = "Branch name";
  name.value = ui.branchName || "";
  name.dataset.focusKey = "save-branch-name";
  name.addEventListener("input", (event) => { ui.branchName = event.target.value; });
  const message = document.createElement("textarea");
  message.className = "stateframe-web-textarea";
  message.placeholder = "Message";
  message.value = ui.branchMessage || "";
  message.dataset.focusKey = "save-branch-message";
  message.addEventListener("input", (event) => { ui.branchMessage = event.target.value; });
  const actions = document.createElement("div");
  actions.className = "stateframe-web-dialog-actions";
  actions.append(
    button("Cancel", () => setUi({ saveBranchOpen: false })),
    button("Save", () => {
      sendCommand("save_viewer_branch", {
        name: ui.branchName || "",
        message: ui.branchMessage || "",
        viewerState,
      });
      setUi({ saveBranchOpen: false, branchName: "", branchMessage: "" });
    }),
  );
  dialog.append(title, name, message, actions);
  overlay.appendChild(dialog);
  return overlay;
}

function computeViewerRows(payload, state) {
  const indices = [];
  const columns = payload.columns || [];
  const query = String(state.globalSearch || "").trim().toLowerCase();
  for (let rowIndex = 0; rowIndex < (payload.rows || []).length; rowIndex += 1) {
    if (query && !columns.some((column) => String(valueFor(payload, rowIndex, column) ?? "").toLowerCase().includes(query))) continue;
    if (!passesFilters(payload, state, rowIndex)) continue;
    indices.push(rowIndex);
  }
  const sorts = state.sorts || [];
  if (sorts.length) {
    indices.sort((a, b) => compareRows(payload, a, b, sorts));
  }
  return {
    indices,
    matches: query ? findViewerMatches(payload, visibleViewerColumns(payload, state), indices, query) : [],
  };
}

function findViewerMatches(payload, visibleColumns, indices, needle) {
  const matches = [];
  for (let virtualIndex = 0; virtualIndex < indices.length; virtualIndex += 1) {
    const rowIndex = indices[virtualIndex];
    for (const column of visibleColumns) {
      if (cellMatches(valueFor(payload, rowIndex, column), needle)) {
        matches.push({ rowIndex, virtualIndex, columnId: column.id });
      }
    }
  }
  return matches;
}

function navigateEmbeddedMatch(delta, computed, ui, setUi, setViewerState, viewerState) {
  if (!computed.matches.length) return;
  const nextIndex = positiveModulo(ui.activeMatchIndex + delta, computed.matches.length);
  const match = computed.matches[nextIndex];
  setViewerState({ selectedColumnId: match.columnId });
  setUi({ activeMatchIndex: nextIndex });
}

function passesFilters(payload, state, rowIndex) {
  for (const [columnId, filter] of Object.entries(state.filters || {})) {
    const column = getViewerColumn(payload, columnId);
    if (!column || !filter || !Object.keys(filter).length) continue;
    const raw = valueFor(payload, rowIndex, column);
    const text = String(raw ?? "");
    if (filter.kind === "numeric") {
      const value = Number(raw);
      if (filter.min !== undefined && filter.min !== "" && !(value >= Number(filter.min))) return false;
      if (filter.max !== undefined && filter.max !== "" && !(value <= Number(filter.max))) return false;
    } else if (filter.kind === "datetime") {
      const value = new Date(raw).getTime();
      if (filter.min && !(value >= new Date(filter.min).getTime())) return false;
      if (filter.max && !(value <= new Date(filter.max).getTime())) return false;
    } else {
      const needle = String(filter.value || "").toLowerCase();
      if (!needle) continue;
      const haystack = text.toLowerCase();
      if (filter.mode === "equals" && haystack !== needle) return false;
      if (filter.mode === "starts" && !haystack.startsWith(needle)) return false;
      if ((!filter.mode || filter.mode === "contains") && !haystack.includes(needle)) return false;
    }
  }
  return true;
}

function compareRows(payload, a, b, sorts) {
  for (const sort of sorts) {
    const column = getViewerColumn(payload, sort.id);
    if (!column) continue;
    const av = valueFor(payload, a, column);
    const bv = valueFor(payload, b, column);
    const direction = sort.direction === "desc" ? -1 : 1;
    const result = compareValues(av, bv);
    if (result !== 0) return result * direction;
  }
  return a - b;
}

function compareValues(a, b) {
  const an = Number(a);
  const bn = Number(b);
  if (!Number.isNaN(an) && !Number.isNaN(bn)) return an === bn ? 0 : an < bn ? -1 : 1;
  return String(a ?? "").localeCompare(String(b ?? ""));
}

function cellMatches(value, needle) {
  if (!needle) return false;
  return String(value ?? "").toLowerCase().includes(needle);
}

function positiveModulo(value, modulo) {
  return ((value % modulo) + modulo) % modulo;
}

function orderedViewerColumns(payload, state) {
  const byId = new Map((payload.columns || []).map((column) => [column.id, column]));
  return (state.columnOrder || []).map((id) => byId.get(id)).filter(Boolean);
}

function visibleViewerColumns(payload, state) {
  const hidden = new Set(state.hiddenColumnIds || []);
  return orderedViewerColumns(payload, state).filter((column) => !hidden.has(column.id));
}

function getViewerColumn(payload, id) {
  return (payload.columns || []).find((column) => column.id === id) || null;
}

function valueFor(payload, rowIndex, column) {
  const index = (payload.columns || []).findIndex((item) => item.id === column.id);
  return payload.rows?.[rowIndex]?.[index];
}

function setColumnFilter(columnId, filter, state, setViewerState) {
  setViewerState({ filters: { ...(state.filters || {}), [columnId]: filter } });
}

function clearColumnFilter(columnId, state, setViewerState) {
  const next = { ...(state.filters || {}) };
  delete next[columnId];
  setViewerState({ filters: next });
}

function nextSorts(sorts, columnId) {
  const current = (sorts || []).find((sort) => sort.id === columnId);
  if (!current) return [{ id: columnId, direction: "asc" }];
  if (current.direction === "asc") return [{ id: columnId, direction: "desc" }];
  return [];
}

function moveId(ids, id, delta) {
  const result = [...ids];
  const index = result.indexOf(id);
  const next = index + delta;
  if (index < 0 || next < 0 || next >= result.length) return result;
  result.splice(index, 1);
  result.splice(next, 0, id);
  return result;
}

function filterInput(placeholder, value, onInput, focusKey) {
  const input = document.createElement("input");
  input.className = "stateframe-web-input";
  input.placeholder = placeholder;
  input.value = value;
  if (focusKey) input.dataset.focusKey = focusKey;
  input.addEventListener("input", () => onInput(input.value));
  return input;
}

function captureFocus(root, ui) {
  const active = root.ownerDocument.activeElement;
  if (active && root.contains(active) && active.dataset?.focusKey) {
    ui.focus = {
      key: active.dataset.focusKey,
      start: readSelection(active).start,
      end: readSelection(active).end,
    };
  } else {
    ui.focus = null;
  }
}

function restoreFocus(root, ui) {
  if (!ui.focus?.key) return;
  const target = root.querySelector(`[data-focus-key="${cssEscape(ui.focus.key)}"]`);
  if (!target) return;
  target.focus({ preventScroll: true });
  if (
    typeof target.setSelectionRange === "function"
    && ui.focus.start !== null
    && ui.focus.end !== null
  ) {
    target.setSelectionRange(ui.focus.start, ui.focus.end);
  }
}

function readSelection(element) {
  try {
    return {
      start: element.selectionStart,
      end: element.selectionEnd,
    };
  } catch (_error) {
    return { start: null, end: null };
  }
}

function cssEscape(value) {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(value);
  }
  return String(value).replace(/["\\]/g, "\\$&");
}

function hydrationCallout(tree, entry) {
  const box = document.createElement("div");
  box.className = "stateframe-web-callout";
  const title = document.createElement("div");
  title.className = "stateframe-web-callout-title";
  const body = document.createElement("div");
  body.className = "stateframe-web-callout-body";
  if (entry.has_snapshot) {
    title.textContent = "Ready to pull";
    body.textContent = "Open the viewer here, or run df = web.pull_selected() in the next cell.";
  } else if (canReplayFromSource(tree, entry)) {
    title.textContent = "Ready to replay";
    body.textContent = "stateframe can reload the base source and replay the saved path for this state.";
  } else {
    title.textContent = "Metadata only";
    body.textContent = "This point needs an editable source path or data snapshot before it can hydrate.";
  }
  box.append(title, body);
  return box;
}

function section(title, child) {
  const wrap = document.createElement("section");
  wrap.className = "stateframe-web-section";
  const heading = document.createElement("div");
  heading.className = "stateframe-web-section-title";
  heading.textContent = title;
  wrap.append(heading, child);
  return wrap;
}

function keyValueList(values) {
  const list = document.createElement("dl");
  list.className = "stateframe-web-kv";
  for (const [key, value] of Object.entries(values)) {
    const dt = document.createElement("dt");
    dt.textContent = key;
    const dd = document.createElement("dd");
    dd.textContent = String(value ?? "");
    list.append(dt, dd);
  }
  return list;
}

function renderSnapshots(snapshots) {
  const list = document.createElement("div");
  list.className = "stateframe-web-snapshots";
  for (const snapshot of snapshots) {
    const item = document.createElement("div");
    item.className = "stateframe-web-snapshot";
    item.textContent = snapshot.path || snapshot.metadata_path || "data snapshot";
    list.appendChild(item);
  }
  return list;
}

function jsonBlock(value) {
  const pre = document.createElement("pre");
  pre.className = "stateframe-web-json";
  pre.textContent = JSON.stringify(value, null, 2);
  return pre;
}

function filteredTrees(trees, state) {
  const query = (state.search || "").trim().toLowerCase();
  let result = trees.filter((tree) => {
    if (!query) return true;
    const haystack = [
      tree.tree_name,
      tree.dataset_name,
      tree.tree_id,
      tree.source?.path,
      tree.source?.absolute_path,
      ...(tree.tree_detail?.entries || []).map((entry) => `${entry.title} ${entry.operation} ${entry.note}`),
      ...(tree.summary?.columns || []),
    ].join(" ").toLowerCase();
    return haystack.includes(query);
  });
  if (state.sort === "name") result = [...result].sort((a, b) => String(a.tree_name || "").localeCompare(String(b.tree_name || "")));
  else if (state.sort === "entries") result = [...result].sort((a, b) => (b.entry_count || 0) - (a.entry_count || 0));
  else if (state.sort === "states") result = [...result].sort((a, b) => (b.state_count || 0) - (a.state_count || 0));
  else result = [...result].sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
  return result;
}

function getTree(trees, id) {
  return trees.find((tree) => tree.tree_id === id) || null;
}

function getEntry(tree, id) {
  if (!tree || !id) return null;
  return (tree.tree_detail?.entries || []).find((entry) => entry.id === id) || null;
}

function defaultEntryId(tree) {
  const entries = tree?.tree_detail?.entries || [];
  if (!entries.length) return null;
  const ids = new Set(entries.map((entry) => entry.id));
  const active = tree?.tree_detail?.active_entry_id || tree?.active_entry_id;
  const root = tree?.tree_detail?.root_entry_id || tree?.root_entry_id;
  if (ids.has(active)) return active;
  if (ids.has(root)) return root;
  return entries[0].id || null;
}

function kindBadge(kind) {
  const el = document.createElement("span");
  el.className = "stateframe-web-kind";
  el.textContent = String(kind || "entry").toUpperCase();
  return el;
}

function textSpan(text, className) {
  const el = document.createElement("span");
  el.className = className;
  el.textContent = text;
  return el;
}

function canReplayFromSource(tree, entry) {
  return Boolean(entry && tree?.source?.kind === "file" && (tree?.source?.path || tree?.source?.absolute_path));
}

function pill(text) {
  const el = document.createElement("span");
  el.className = "stateframe-web-pill";
  el.textContent = text;
  return el;
}

function codePill(text) {
  const el = document.createElement("code");
  el.className = "stateframe-web-code-pill";
  el.textContent = text;
  return el;
}

function button(label, onClick) {
  const el = document.createElement("button");
  el.type = "button";
  el.className = "stateframe-web-button";
  el.textContent = label;
  el.addEventListener("click", onClick);
  return el;
}

function tinyButton(label, onClick, disabled = false) {
  const el = button(label, onClick);
  el.classList.add("is-tiny");
  el.disabled = disabled;
  return el;
}

function th(value) {
  const cell = document.createElement("th");
  cell.textContent = String(value ?? "");
  return cell;
}

function td(value) {
  const cell = document.createElement("td");
  cell.textContent = formatCell(value);
  return cell;
}

function empty(text) {
  const el = document.createElement("div");
  el.className = "stateframe-web-empty";
  el.textContent = text;
  return el;
}

function sum(items, key) {
  return items.reduce((total, item) => total + Number(item[key] || 0), 0);
}

function sourceText(source) {
  if (!source) return "";
  if (source.path) return source.path;
  if (source.kind) return source.kind;
  return "";
}

function statusText(status) {
  if (!status?.status) return "";
  if (status.status === "error") return status.message || "Action failed";
  return status.message || "";
}

function formatCell(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return text.length > 160 ? `${text.slice(0, 157)}...` : text;
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value ?? "");
  return number.toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return `${(number * 100).toFixed(1)}%`;
}

function formatInt(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const scaled = bytes / (1024 ** index);
  return `${scaled.toFixed(index === 0 ? 0 : 2)} ${units[index]}`;
}

export default { render };
