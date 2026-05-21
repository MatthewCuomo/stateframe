function render({ model, el, signal }) {
  let payload = model.get("payload") || {};
  let state = normalizeState(model.get("state"), payload);
  let viewer = normalizeViewer(model.get("viewer"));
  let visualizer = normalizeVisualizer(model.get("visualizer"));
  let files = normalizeFiles(model.get("files"));
  let commandStatus = model.get("command_status") || {};
  const ui = {
    saveBranchOpen: false,
    branchName: "",
    branchMessage: "",
    focus: null,
    scroll: Object.create(null),
    pendingViewerMatch: null,
    leafNoteDrafts: Object.create(null),
    activeMatchIndex: 0,
    lastGlobalSearch: "",
    lineageOpen: false,
    visualOptionOpen: Object.create(null),
    queryName: "",
    queryText: "",
    queryParamsJson: "",
    queryStoreQuery: null,
    queryStoreParams: null,
    queryError: "",
    connectionDraft: null,
    webSearchDraft: state.search || "",
    webSearchTimer: null,
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

  function setVisualizerState(patch) {
    captureFocus(root, ui);
    const visualPayload = visualizer.payload || {};
    visualizer = normalizeVisualizer({
      ...visualizer,
      state: normalizeVisualizerState({ ...(visualizer.state || {}), ...patch }, visualPayload),
    });
    model.set("visualizer", visualizer);
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
      saveMode: Boolean(state.saveMode),
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

  function openSelectedVisualizer(extra = {}) {
    visualizer = { status: "loading", payload: null, state: {}, preview: null, message: "Loading visualizer" };
    model.set("visualizer", visualizer);
    model.save_changes();
    setState({ viewMode: "visualizer" });
    sendCommand("open_visualizer", {
      height: payload.view?.height || 640,
      maxRows: 500,
      ...extra,
    });
  }

  function onPayloadChange() {
    captureFocus(root, ui);
    payload = model.get("payload") || {};
    state = normalizeState(model.get("state"), payload);
    if (focusedKey(root) !== "web-search") ui.webSearchDraft = state.search || "";
    draw();
  }

  function onStateChange() {
    captureFocus(root, ui);
    state = normalizeState(model.get("state"), payload);
    if (focusedKey(root) !== "web-search") ui.webSearchDraft = state.search || "";
    draw();
  }

  function onViewerChange() {
    captureFocus(root, ui);
    viewer = normalizeViewer(model.get("viewer"));
    draw();
  }

  function onVisualizerChange() {
    captureFocus(root, ui);
    visualizer = normalizeVisualizer(model.get("visualizer"));
    draw();
  }

  function onFilesChange() {
    captureFocus(root, ui);
    files = normalizeFiles(model.get("files"));
    draw();
  }

  function onCommandStatusChange() {
    captureFocus(root, ui);
    commandStatus = model.get("command_status") || {};
    draw();
  }

  model.on("change:payload", onPayloadChange);
  model.on("change:state", onStateChange);
  model.on("change:viewer", onViewerChange);
  model.on("change:visualizer", onVisualizerChange);
  model.on("change:files", onFilesChange);
  model.on("change:command_status", onCommandStatusChange);
  signal.addEventListener("abort", () => {
    model.off("change:payload", onPayloadChange);
    model.off("change:state", onStateChange);
    model.off("change:viewer", onViewerChange);
    model.off("change:visualizer", onVisualizerChange);
    model.off("change:files", onFilesChange);
    model.off("change:command_status", onCommandStatusChange);
    if (ui.webSearchTimer) clearTimeout(ui.webSearchTimer);
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
    root.appendChild(renderToolbar(payload, state, setState, sendCommand, commandStatus, setUi, files, ui));

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
      queueRestoreUiState(root, ui);
      return;
    }

    if (state.viewMode === "visualizer") {
      root.appendChild(renderVisualizer(
        visualizer,
        commandStatus,
        setVisualizerState,
        sendCommand,
        setState,
        ui,
        setUi,
      ));
      queueRestoreUiState(root, ui);
      return;
    }

    if (state.viewMode === "get_data") {
      root.appendChild(renderGetData(payload, files, commandStatus, state, setState, sendCommand, ui, setUi));
      queueRestoreUiState(root, ui);
      return;
    }

    if (state.viewMode === "files") {
      root.appendChild(renderFileBrowser(files, commandStatus, setState, sendCommand));
      queueRestoreUiState(root, ui);
      return;
    }

    if (state.viewMode === "leaf") {
      root.appendChild(renderLeafOutput(selected, selectedEntry, setState, sendCommand, commandStatus, ui));
      queueRestoreUiState(root, ui);
      return;
    }

    root.appendChild(renderStats(payload));
    const body = document.createElement("div");
    body.className = "stateframe-web-body";
    body.style.setProperty("--stateframe-web-left-width", `${state.panelWidths.webLeft}px`);
    body.appendChild(renderTreeList(trees, selected, state, setState));
    body.appendChild(horizontalPanelResizer({
      className: "stateframe-web-panel-resizer",
      label: "Resize tree browser panels",
      value: state.panelWidths.webLeft,
      min: 260,
      max: 720,
      onPreview: (width) => body.style.setProperty("--stateframe-web-left-width", `${width}px`),
      onCommit: (width) => setState({ panelWidths: { ...state.panelWidths, webLeft: width } }),
    }));
    body.appendChild(renderDetail(payload, selected, selectedEntry, state, setState, openSelectedViewer, openSelectedVisualizer));
    root.appendChild(body);
    queueRestoreUiState(root, ui);
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
  const deleteTreeIds = Array.isArray(raw?.deleteTreeIds)
    ? raw.deleteTreeIds.filter((id) => ids.has(id))
    : [];
  const deleteEntryIds = Array.isArray(raw?.deleteEntryIds)
    ? raw.deleteEntryIds.filter((id) => entryIds.has(id) && id !== (selectedTree?.tree_detail?.root_entry_id || selectedTree?.root_entry_id))
    : [];
  const sorts = new Set(["updated", "name", "entries", "states"]);
  const modes = new Set(["web", "viewer", "visualizer", "get_data", "files", "leaf"]);
  const tabs = new Set(["files", "query", "connections"]);
  const sourceIds = new Set((payload.sources || []).map((source) => source.id));
  const connectionIds = new Set((payload.source_connections || []).map((source) => source.id));
  return {
    selectedTreeId: selected,
    selectedEntryId: selectedEntry,
    viewMode: modes.has(raw?.viewMode) ? raw.viewMode : "web",
    getDataTab: tabs.has(raw?.getDataTab) ? raw.getDataTab : "files",
    querySourceId: sourceIds.has(raw?.querySourceId) || connectionIds.has(raw?.querySourceId)
      ? raw.querySourceId
      : (payload.sources?.[0]?.id || payload.source_connections?.[0]?.id || ""),
    selectedFilePath: raw?.selectedFilePath || null,
    collapsedEntryIds: Array.isArray(raw?.collapsedEntryIds)
      ? raw.collapsedEntryIds.filter((id) => entryIds.has(id))
      : [],
    panelWidths: {
      webLeft: clampNumber(raw?.panelWidths?.webLeft, 340, 260, 720),
    },
    saveMode: Boolean(raw?.saveMode),
    deleteMode: Boolean(raw?.deleteMode),
    deleteTreeIds,
    deleteEntryIds,
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

function normalizeVisualizer(raw) {
  const payload = raw?.payload || null;
  return {
    status: raw?.status || (payload ? "ready" : "empty"),
    payload,
    state: payload ? normalizeVisualizerState(raw?.state, payload) : {},
    preview: raw?.preview || null,
    message: raw?.message || "",
  };
}

function normalizeVisualizerState(raw, payload) {
  const catalog = payload?.catalog || {};
  const plotTypes = Array.isArray(catalog.plot_types) ? catalog.plot_types : [];
  const ids = new Set(plotTypes.map((item) => item.id));
  const kind = ids.has(raw?.kind) ? raw.kind : plotTypes[0]?.id || "histogram";
  const definition = plotTypes.find((item) => item.id === kind) || plotTypes[0] || {};
  const columns = new Set((payload?.columns || []).map((column) => column.id));
  const fields = {};
  for (const field of definition.fields || []) {
    const value = raw?.fields?.[field.slot];
    if (field.multiple) {
      const values = Array.isArray(value)
        ? value.filter((column) => columns.has(column))
        : String(value || "").split(",").map((item) => item.trim()).filter((column) => columns.has(column));
      if (values.length) fields[field.slot] = values;
    } else if (columns.has(value)) {
      fields[field.slot] = value;
    }
  }
  if (!Object.keys(fields).length) {
    const first = defaultVisualColumn(payload, definition);
    if (first) {
      const firstField = (definition.fields || []).find((field) => field.required) || (definition.fields || [])[0];
      if (firstField) fields[firstField.slot] = first;
    }
  }
  return {
    kind,
    fields,
    filters: Array.isArray(raw?.filters) ? raw.filters : [],
    options: raw?.options || {},
    title: raw?.title || "",
    note: raw?.note || "",
    collapsedPanels: {
      library: Boolean(raw?.collapsedPanels?.library),
      inspector: Boolean(raw?.collapsedPanels?.inspector),
    },
    panelWidths: {
      library: clampNumber(raw?.panelWidths?.library, 260, 200, 440),
      inspector: clampNumber(raw?.panelWidths?.inspector, 360, 260, 640),
    },
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
    collapsedPanels: {
      columns: Boolean(raw?.collapsedPanels?.columns),
      inspector: Boolean(raw?.collapsedPanels?.inspector),
    },
    panelWidths: {
      columns: clampNumber(raw?.panelWidths?.columns, 240, 180, 440),
      inspector: clampNumber(raw?.panelWidths?.inspector, 320, 240, 600),
    },
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

function renderToolbar(payload, state, setState, sendCommand, commandStatus, setUi, files, ui) {
  const toolbar = document.createElement("div");
  toolbar.className = "stateframe-web-toolbar";

  const titleGroup = document.createElement("div");
  titleGroup.className = "stateframe-web-title-group";
  const title = document.createElement("div");
  title.className = "stateframe-web-title";
  title.textContent = state.viewMode === "viewer"
    ? "stateframe embedded viewer"
    : state.viewMode === "visualizer"
      ? "stateframe visualizer"
      : state.viewMode === "get_data" || state.viewMode === "files"
        ? "stateframe get data"
        : state.viewMode === "leaf"
          ? "stateframe leaf"
          : payload.title || "stateframe workspace web";
  const subtitle = document.createElement("div");
  subtitle.className = "stateframe-web-subtitle";
  const workspaceName = payload.workspace?.name || payload.settings?.name || "workspace";
  subtitle.textContent = state.viewMode === "viewer"
    ? statusText(commandStatus) || "Open state from web, shape it, then save a branch"
    : state.viewMode === "visualizer"
      ? statusText(commandStatus) || "Build Plotly visuals from tracked dataframe states"
      : state.viewMode === "get_data" || state.viewMode === "files"
        ? statusText(commandStatus) || `${workspaceName} / ${files.current_path || "."}`
        : statusText(commandStatus) || `${workspaceName} / ${payload.settings?.root || ""}`;
  titleGroup.append(title, subtitle);

  const controls = document.createElement("div");
  controls.className = "stateframe-web-controls";

  if (state.viewMode === "viewer") {
    controls.classList.add("is-viewer");
    controls.append(
      button("Back", () => setState({ viewMode: "web" })),
      button(state.saveMode ? "Save Mode On" : "Save Mode Off", () => setState({ saveMode: !state.saveMode })),
      button("Save Branch", () => setUi({ saveBranchOpen: true })),
      button("Refresh", () => sendCommand("refresh")),
    );
  } else if (state.viewMode === "visualizer") {
    controls.classList.add("is-viewer");
    controls.append(
      button("Back", () => setState({ viewMode: "web" })),
      button(state.saveMode ? "Save Mode On" : "Save Mode Off", () => setState({ saveMode: !state.saveMode })),
      button("Refresh", () => sendCommand("refresh")),
    );
  } else if (state.viewMode === "leaf") {
    controls.classList.add("is-viewer");
    controls.append(
      button("Back", () => setState({ viewMode: "web" })),
      button(state.saveMode ? "Save Mode On" : "Save Mode Off", () => setState({ saveMode: !state.saveMode })),
      button("Refresh", () => sendCommand("refresh")),
    );
  } else if (state.viewMode === "get_data") {
    controls.classList.add("is-viewer");
    controls.append(
      button("Back", () => setState({ viewMode: "web" })),
      button("Refresh Sources", () => sendCommand("refresh_sources")),
      button("Refresh Files", () => sendCommand("browse_files", {
        path: files.current_path || ".",
        viewMode: "get_data",
      })),
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
    const canDelete = payload.view?.launch_mode !== "single_profile";
    const deleteCount = deleteSelectionCount(state);
    const search = document.createElement("input");
    search.className = "stateframe-web-input";
    search.type = "search";
    search.placeholder = "Search trees, sources, columns";
    search.dataset.focusKey = "web-search";
    search.value = ui.webSearchDraft ?? state.search ?? "";
    search.addEventListener("input", () => {
      ui.webSearchDraft = search.value;
      if (ui.webSearchTimer) clearTimeout(ui.webSearchTimer);
      ui.webSearchTimer = setTimeout(() => {
        ui.webSearchTimer = null;
        setState({ search: ui.webSearchDraft || "" });
      }, 160);
    });

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
    );
    if (state.deleteMode) {
      const deleteButton = button(`Delete ${deleteCount || ""}`.trim(), () => {
        if (!deleteCount) return;
        const summary = deleteSelectionLabel(state);
        if (!window.confirm(`Delete ${summary}? This removes the selected items from the workspace web. Saved data/artifact files stay on disk.`)) {
          return;
        }
        sendCommand("delete_selected", {
          treeId: state.selectedTreeId,
          treeIds: state.deleteTreeIds || [],
          entryIds: state.deleteEntryIds || [],
        });
      });
      deleteButton.disabled = !deleteCount || (commandStatus?.status === "loading" && commandStatus?.action === "delete_selected");
      deleteButton.classList.add("is-danger");
      controls.append(
        deleteButton,
        button("Cancel Delete", () => setState({ deleteMode: false, deleteTreeIds: [], deleteEntryIds: [] })),
      );
    } else {
      controls.append(
        button(state.saveMode ? "Save Mode On" : "Save Mode Off", () => setState({ saveMode: !state.saveMode })),
        button("Visualizer", () => {
          setState({ viewMode: "visualizer" });
          sendCommand("open_visualizer", { height: payload.view?.height || 640, maxRows: 500 });
        }),
        button("Get Data", () => {
          setState({ viewMode: "get_data", getDataTab: "files" });
          sendCommand("browse_files", { path: files.current_path || ".", viewMode: "get_data" });
        }),
      );
      if (canDelete) controls.append(button("Delete Mode", () => setState({ deleteMode: true, deleteTreeIds: [], deleteEntryIds: [] })));
      controls.append(button("Refresh", () => sendCommand("refresh")));
    }
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

function renderTreeList(trees, selected, state, setState) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-panel";
  panel.dataset.scrollKey = "web-tree-list";
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
    if ((state.deleteTreeIds || []).includes(tree.tree_id)) item.classList.add("is-delete-selected");
    item.addEventListener("click", () => {
      if (state.deleteMode) {
        setState({ deleteTreeIds: toggleArrayValue(state.deleteTreeIds || [], tree.tree_id) });
      } else {
        setState({
          selectedTreeId: tree.tree_id,
          selectedEntryId: defaultEntryId(tree),
          deleteEntryIds: [],
        });
      }
    });

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
    if (state.deleteMode) {
      const marker = document.createElement("span");
      marker.className = "stateframe-web-delete-marker";
      marker.textContent = (state.deleteTreeIds || []).includes(tree.tree_id) ? "Selected for delete" : "Select tree";
      footer.append(marker);
    }
    item.append(title, meta, footer);
    list.appendChild(item);
  }
  panel.appendChild(list);
  return panel;
}

function renderGetData(payload, files, commandStatus, state, setState, sendCommand, ui, setUi) {
  const shell = document.createElement("div");
  shell.className = "stateframe-web-getdata";
  shell.dataset.scrollKey = "get-data";

  const tabs = document.createElement("div");
  tabs.className = "stateframe-web-tabs";
  for (const [tab, label] of [
    ["files", "Files"],
    ["query", "Query Data"],
    ["connections", "Connections"],
  ]) {
    const item = button(label, () => setState({ getDataTab: tab }));
    item.classList.add("is-tab");
    if (state.getDataTab === tab) item.classList.add("is-active");
    tabs.appendChild(item);
  }
  shell.appendChild(tabs);

  if (state.getDataTab === "query") {
    shell.appendChild(renderQueryData(payload, commandStatus, state, setState, sendCommand, ui, setUi));
  } else if (state.getDataTab === "connections") {
    shell.appendChild(renderConnectionConfig(payload, commandStatus, state, setState, sendCommand, ui, setUi));
  } else {
    shell.appendChild(renderFileBrowser(files, commandStatus, setState, sendCommand, { viewMode: "get_data" }));
  }
  return shell;
}

function renderFileBrowser(files, commandStatus, setState, sendCommand, options = {}) {
  const shell = document.createElement("div");
  shell.className = "stateframe-web-files";
  shell.dataset.scrollKey = "file-browser";

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
  const browsePayload = (path) => ({
    path,
    viewMode: options.viewMode || "files",
    getDataTab: options.viewMode === "get_data" ? "files" : undefined,
  });
  const root = button("Workspace Root", () => sendCommand("browse_files", browsePayload(".")));
  const up = button("Up", () => sendCommand("browse_files", browsePayload(files.parent_path || ".")));
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
      options,
    ));
  }
  for (const entry of files.entries || []) {
    list.appendChild(renderFileEntry(entry, setState, sendCommand, options));
  }
  if (!list.children.length) {
    shell.appendChild(empty("No files are visible in this workspace folder."));
  } else {
    shell.appendChild(list);
  }
  return shell;
}

function renderFileEntry(entry, setState, sendCommand, options = {}) {
  const item = document.createElement("div");
  item.tabIndex = 0;
  item.setAttribute("role", "button");
  item.className = "stateframe-web-file-item";
  if (entry.kind === "directory") item.classList.add("is-directory");
  if (entry.can_scan) item.classList.add("is-data");
  const openEntry = () => {
    if (entry.kind === "directory") {
      sendCommand("browse_files", {
        path: entry.path || ".",
        viewMode: options.viewMode || "files",
        getDataTab: options.viewMode === "get_data" ? "files" : undefined,
      });
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
      sendCommand("browse_files", {
        path: entry.path || ".",
        viewMode: options.viewMode || "files",
        getDataTab: options.viewMode === "get_data" ? "files" : undefined,
      });
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

function renderQueryData(payload, commandStatus, state, setState, sendCommand, ui, setUi) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-query-panel";
  const sources = payload.sources || [];
  const connections = payload.source_connections || [];
  const selectedSourceId = state.querySourceId || sources[0]?.id || "";
  const selectedSource = sources.find((source) => source.id === selectedSourceId) || null;
  const selectedConnection = connections.find((connection) => connection.id === selectedSourceId) || null;
  if (ui.queryStoreQuery === null) ui.queryStoreQuery = selectedConnection?.store_query !== false;
  if (ui.queryStoreParams === null) ui.queryStoreParams = selectedConnection?.store_params !== false;

  const header = document.createElement("div");
  header.className = "stateframe-web-query-header";
  header.append(
    textSpan("Query Data", "stateframe-web-query-title"),
    button("Configure Connection", () => {
      ui.connectionDraft = connectionDraftFrom(selectedConnection);
      setState({ getDataTab: "connections" });
    }),
    button("Refresh Sources", () => sendCommand("refresh_sources")),
  );
  panel.appendChild(header);

  if (!sources.length) {
    const emptyBox = empty("No registered query sources are loaded yet.");
    panel.appendChild(emptyBox);
    panel.appendChild(renderConnectionConfig(payload, commandStatus, state, setState, sendCommand, ui, setUi));
    return panel;
  }

  const form = document.createElement("div");
  form.className = "stateframe-web-query-form";
  const sourceSelect = document.createElement("select");
  sourceSelect.className = "stateframe-web-select";
  sourceSelect.dataset.focusKey = "query-source";
  for (const source of sources) {
    const option = document.createElement("option");
    option.value = source.id;
    option.textContent = source.display_name || source.id;
    sourceSelect.appendChild(option);
  }
  sourceSelect.value = selectedSourceId;
  sourceSelect.addEventListener("change", () => {
    ui.queryStoreQuery = null;
    ui.queryStoreParams = null;
    ui.queryError = "";
    setState({ querySourceId: sourceSelect.value });
  });

  const name = document.createElement("input");
  name.className = "stateframe-web-input";
  name.placeholder = "Result tree name";
  name.value = ui.queryName || "";
  name.dataset.focusKey = "query-name";
  name.addEventListener("input", () => { ui.queryName = name.value; });

  const query = document.createElement("textarea");
  query.className = "stateframe-web-textarea stateframe-web-query-text";
  query.placeholder = "select * from schema.table limit 1000";
  query.value = ui.queryText || "";
  query.dataset.focusKey = "query-text";
  query.addEventListener("input", () => { ui.queryText = query.value; });

  const params = document.createElement("textarea");
  params.className = "stateframe-web-textarea stateframe-web-query-params";
  params.placeholder = "{\"start\": \"2025-01-01\"}";
  params.value = ui.queryParamsJson || "";
  params.dataset.focusKey = "query-params";
  params.addEventListener("input", () => { ui.queryParamsJson = params.value; });

  const storeQuery = checkbox("Store query text", ui.queryStoreQuery !== false, (checked) => { ui.queryStoreQuery = checked; });
  const storeParams = checkbox("Store params", ui.queryStoreParams !== false, (checked) => { ui.queryStoreParams = checked; });
  const run = button("Run Query", () => {
    const parsed = parseParamsJson(ui.queryParamsJson || "");
    if (parsed.error) {
      setUi({ queryError: parsed.error });
      return;
    }
    if (!sourceSelect.value) {
      setUi({ queryError: "Choose a query source first." });
      return;
    }
    if (!String(ui.queryText || "").trim()) {
      setUi({ queryError: "Enter a query before running." });
      return;
    }
    sendCommand("query_data", {
      source: sourceSelect.value,
      query: ui.queryText,
      params: parsed.value,
      name: ui.queryName || "",
      storeQuery: ui.queryStoreQuery !== false,
      storeParams: ui.queryStoreParams !== false,
    });
  });
  run.disabled = commandStatus?.status === "loading" && commandStatus.action === "query_data";

  const sourceMeta = document.createElement("div");
  sourceMeta.className = "stateframe-web-query-source-meta";
  sourceMeta.textContent = selectedSource
    ? `${selectedSource.id} / ${selectedSource.class || "provider"}`
    : "No source selected";

  const errorText = ui.queryError || (
    commandStatus?.action === "query_data" && commandStatus.status === "error"
      ? commandStatus.message
      : ""
  );
  form.append(
    labeledControl("Source", sourceSelect),
    sourceMeta,
    labeledControl("Name", name),
    labeledControl("Query", query),
    labeledControl("Params JSON", params),
    inlineControls(storeQuery, storeParams, run),
  );
  if (errorText) {
    const error = empty(errorText);
    error.classList.add("is-error");
    form.appendChild(error);
  } else if (commandStatus?.action === "query_data" && commandStatus.status === "ready") {
    const ready = document.createElement("div");
    ready.className = "stateframe-web-status is-saved";
    ready.textContent = commandStatus.message || "Query complete";
    form.appendChild(ready);
  }
  panel.appendChild(form);
  return panel;
}

function renderConnectionConfig(payload, commandStatus, state, setState, sendCommand, ui, setUi) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-connection-panel";
  const connections = payload.source_connections || [];
  const header = document.createElement("div");
  header.className = "stateframe-web-query-header";
  header.append(
    textSpan("Connections", "stateframe-web-query-title"),
    button("New", () => setUi({ connectionDraft: blankConnectionDraft(), queryError: "" })),
    button("Refresh Sources", () => sendCommand("refresh_sources")),
  );
  panel.appendChild(header);

  if (connections.length) {
    const list = document.createElement("div");
    list.className = "stateframe-web-connection-list";
    for (const connection of connections) {
      const item = document.createElement("div");
      item.className = "stateframe-web-connection-item";
      if (connection.registered) item.classList.add("is-registered");
      if (connection.status === "error") item.classList.add("is-error");
      const main = document.createElement("div");
      main.className = "stateframe-web-connection-main";
      main.append(
        textSpan(connection.display_name || connection.id, "stateframe-web-connection-title"),
        textSpan(`${connection.id} / ${connection.status || "not_loaded"}`, "stateframe-web-connection-meta"),
      );
      if (connection.error) main.appendChild(textSpan(connection.error, "stateframe-web-connection-error"));
      const actions = document.createElement("div");
      actions.className = "stateframe-web-action-row";
      actions.append(
        button("Use", () => {
          if (typeof setState === "function") setState({ getDataTab: "query", querySourceId: connection.id });
        }),
        button("Edit", () => setUi({ connectionDraft: connectionDraftFrom(connection), queryError: "" })),
        button("Delete", () => sendCommand("delete_source_connection", { sourceId: connection.id })),
      );
      item.append(main, actions);
      list.appendChild(item);
    }
    panel.appendChild(list);
  } else {
    panel.appendChild(empty("No saved query connections yet."));
  }

  const draft = ui.connectionDraft || blankConnectionDraft();
  ui.connectionDraft = draft;
  const form = document.createElement("div");
  form.className = "stateframe-web-connection-form";
  const sourceId = inputControl("Source id", draft.id, "connection-id", (value) => { draft.id = value; });
  const displayName = inputControl("Display name", draft.display_name, "connection-display-name", (value) => { draft.display_name = value; });
  const importPath = inputControl("Import path", draft.import_path, "connection-import-path", (value) => { draft.import_path = value; });
  const description = document.createElement("textarea");
  description.className = "stateframe-web-textarea";
  description.placeholder = "Description";
  description.value = draft.description || "";
  description.dataset.focusKey = "connection-description";
  description.addEventListener("input", () => { draft.description = description.value; });
  const enabled = checkbox("Enabled", draft.enabled !== false, (checked) => { draft.enabled = checked; });
  const storeQuery = checkbox("Store query text by default", draft.store_query !== false, (checked) => { draft.store_query = checked; });
  const storeParams = checkbox("Store params by default", draft.store_params !== false, (checked) => { draft.store_params = checked; });
  const save = button("Save Connection", () => {
    if (!String(draft.id || "").trim()) {
      setUi({ queryError: "Source id is required." });
      return;
    }
    if (!String(draft.import_path || "").trim()) {
      setUi({ queryError: "Import path is required." });
      return;
    }
    sendCommand("save_source_connection", {
      sourceId: draft.id,
      displayName: draft.display_name,
      description: draft.description,
      importPath: draft.import_path,
      enabled: draft.enabled !== false,
      storeQuery: draft.store_query !== false,
      storeParams: draft.store_params !== false,
    });
  });
  form.append(
    labeledControl("Source id", sourceId),
    labeledControl("Display name", displayName),
    labeledControl("Import path", importPath),
    labeledControl("Description", description),
    inlineControls(enabled, storeQuery, storeParams, save),
  );
  if (ui.queryError && state.getDataTab === "connections") {
    const error = empty(ui.queryError);
    error.classList.add("is-error");
    form.appendChild(error);
  } else if (commandStatus?.action === "save_source_connection") {
    const status = document.createElement("div");
    status.className = commandStatus.status === "error" ? "stateframe-web-status is-error" : "stateframe-web-status is-saved";
    status.textContent = commandStatus.message || "";
    form.appendChild(status);
  }
  panel.appendChild(form);
  return panel;
}

function renderDetail(payload, tree, selectedEntry, state, setState, openSelectedViewer, openSelectedVisualizer) {
  const panel = document.createElement("aside");
  panel.className = "stateframe-web-detail";
  panel.dataset.scrollKey = "web-detail";

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

  if (state.deleteMode) {
    const notice = document.createElement("div");
    notice.className = "stateframe-web-delete-notice";
    notice.textContent = "Delete mode: select trees on the left, or select branches and leaves below. Deleting a branch removes its descendants from the tree.";
    panel.appendChild(notice);
  }
  panel.appendChild(section("Tree Entries", renderEntries(tree, selectedEntry, state, setState)));
  if (selectedEntry) {
    panel.appendChild(section("Selected State", renderEntryDetail(tree, selectedEntry, openSelectedViewer, openSelectedVisualizer, setState)));
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

function renderEntries(tree, selectedEntry, state, setState) {
  const entries = tree.tree_detail?.entries || [];
  const list = document.createElement("div");
  list.className = "stateframe-web-entry-list";
  if (!entries.length) return empty("No saved tree entries are available yet.");

  const hierarchy = buildEntryHierarchy(entries);
  const collapsed = new Set(state.collapsedEntryIds || []);
  const pathIds = new Set((selectedEntry?.path || []).map((step) => step.id));
  const visited = new Set();

  function appendEntry(entry, depth, trail = new Set()) {
    if (!entry?.id || trail.has(entry.id) || visited.has(entry.id)) return;
    visited.add(entry.id);
    const children = hierarchy.byParent.get(entry.id) || [];
    const hasChildren = children.length > 0;
    const isCollapsed = hasChildren && collapsed.has(entry.id);

    const row = document.createElement("div");
    row.className = "stateframe-web-entry-row";
    if (depth > 0) row.classList.add("is-nested");
    if (hasChildren) row.classList.add("has-children");
    if (isCollapsed) row.classList.add("is-collapsed");
    row.style.setProperty("--entry-depth", String(Math.min(Number(depth || 0), 8)));

    if (hasChildren) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "stateframe-web-entry-toggle";
      toggle.textContent = isCollapsed ? "\u25b8" : "\u25be";
      toggle.title = isCollapsed ? "Expand branch" : "Collapse branch";
      toggle.setAttribute("aria-label", toggle.title);
      toggle.addEventListener("click", (event) => {
        event.stopPropagation();
        toggleEntryCollapse(entry.id, state, setState);
      });
      row.appendChild(toggle);
    } else {
      const spacer = document.createElement("span");
      spacer.className = "stateframe-web-entry-toggle-spacer";
      row.appendChild(spacer);
    }

    const item = document.createElement("button");
    item.type = "button";
    item.className = "stateframe-web-entry-item";
    item.classList.add(...entryKindClasses(entry, "stateframe-web"));
    if (entry.id === selectedEntry?.id) item.classList.add("is-selected");
    if ((state.deleteEntryIds || []).includes(entry.id)) item.classList.add("is-delete-selected");
    if (entry.is_active) item.classList.add("is-active");
    if (pathIds.has(entry.id) && entry.id !== selectedEntry?.id) item.classList.add("is-in-path");
    if (isCollapsed) item.classList.add("is-collapsed");
    item.addEventListener("click", () => {
      if (state.deleteMode) {
        const rootId = tree.tree_detail?.root_entry_id || tree.root_entry_id;
        if (entry.id === rootId) return;
        setState({ deleteEntryIds: toggleArrayValue(state.deleteEntryIds || [], entry.id) });
      } else {
        setState({ selectedEntryId: entry.id });
      }
    });

    const top = document.createElement("div");
    top.className = "stateframe-web-entry-top";
    if (state.deleteMode) {
      const rootId = tree.tree_detail?.root_entry_id || tree.root_entry_id;
      const marker = document.createElement("span");
      marker.className = "stateframe-web-entry-delete-marker";
      marker.textContent = entry.id === rootId
        ? "\u2212"
        : ((state.deleteEntryIds || []).includes(entry.id) ? "\u2713" : "");
      marker.title = entry.id === rootId ? "Delete the whole tree to remove the root scan." : "Select for delete";
      top.append(marker);
    }
    top.append(kindBadge(entry.kind), textSpan(entry.title || entry.operation || entry.id, "stateframe-web-entry-title"));
    const meta = document.createElement("div");
    meta.className = "stateframe-web-entry-meta";
    const stateText = isOutputEntry(entry) ? "output leaf" : entry.has_state ? "state" : "asset/no state";
    const childText = `${formatInt(entry.child_count || 0)} child${Number(entry.child_count || 0) === 1 ? "" : "ren"}`;
    meta.textContent = `${entry.operation || entry.kind || "entry"} / ${stateText} / ${childText}`;
    const thumbnail = renderEntryThumbnail(entry);
    const footer = document.createElement("div");
    footer.className = "stateframe-web-entry-footer";
    if (entry.has_snapshot) footer.append(pill("pull ready"));
    else if (canReplayFromSource(tree, entry)) footer.append(pill("replay ready"));
    if (isCollapsed) footer.append(pill(`${formatInt(descendantCount(entry.id, hierarchy.byParent))} hidden`));
    if (entry.is_active) footer.append(pill("active"));
    if (entry.note) footer.append(pill("note"));
    if (state.deleteMode && (state.deleteEntryIds || []).includes(entry.id)) {
      const descendantTotal = descendantCount(entry.id, hierarchy.byParent);
      footer.append(pill(descendantTotal ? `deletes ${formatInt(descendantTotal)} descendants` : "delete selected"));
    }
    item.append(top, meta);
    if (thumbnail) item.append(thumbnail);
    item.append(footer);
    row.appendChild(item);
    list.appendChild(row);

    if (!isCollapsed) {
      const nextTrail = new Set(trail);
      nextTrail.add(entry.id);
      for (const child of children) appendEntry(child, depth + 1, nextTrail);
    } else {
      markDescendantsVisited(entry.id, hierarchy.byParent, visited);
    }
  }

  for (const root of hierarchy.roots) appendEntry(root, 0);
  for (const entry of entries) {
    if (!visited.has(entry.id)) appendEntry(entry, entry.depth || 0);
  }

  return list;
}

function renderEntryThumbnail(entry) {
  const preview = entryThumbnailPreview(entry);
  if (!preview) return null;
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-entry-thumbnail";
  const image = document.createElement("img");
  image.src = preview.preview_data_url;
  image.alt = preview.alt || entry.title || "stateframe plot preview";
  wrap.appendChild(image);
  return wrap;
}

function entryThumbnailPreview(entry) {
  for (const artifact of entryOutputArtifacts(entry)) {
    if (!artifact || typeof artifact !== "object") continue;
    if (isImageDataUrl(artifact.preview_data_url)) {
      return {
        preview_data_url: artifact.preview_data_url,
        alt: artifact.title || artifact.name || entry.title,
      };
    }
    for (const preview of artifact.previews || []) {
      if (isImageDataUrl(preview?.preview_data_url)) {
        return {
          preview_data_url: preview.preview_data_url,
          alt: preview.name || artifact.title || entry.title,
        };
      }
    }
  }
  return null;
}

function renderEntryDetail(tree, entry, openSelectedViewer, openSelectedVisualizer, setState) {
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
  const outputArtifacts = entryOutputArtifacts(entry);
  const isLeafOutput = isOutputEntry(entry) || outputArtifacts.length > 0;
  const canOpen = !isLeafOutput && entry.has_state && (entry.has_snapshot || canReplayFromSource(tree, entry) || entry.state?.has_data);
  if (!isLeafOutput) {
    const open = button("Open Viewer", openSelectedViewer);
    open.disabled = !canOpen;
    actions.append(open);
    const visualize = button("Visualizer", () => openSelectedVisualizer());
    visualize.disabled = !canOpen;
    actions.append(visualize);
  }
  if (outputArtifacts.length) {
    actions.append(button("Open Leaf", () => setState({ viewMode: "leaf" })));
  }
  actions.append(renderPullReference(entry));
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
    note.className = "stateframe-web-note stateframe-web-markdown";
    note.replaceChildren(renderMarkdown(entry.note));
    wrap.appendChild(section("Note", note));
  }
  if (entry.params && Object.keys(entry.params).length) wrap.appendChild(section("Params", jsonBlock(entry.params)));
  if (entry.artifacts?.length) wrap.appendChild(section("Artifacts", renderArtifacts(entry.artifacts)));
  return wrap;
}

function renderArtifacts(artifacts, { full = false } = {}) {
  const list = document.createElement("div");
  list.className = "stateframe-web-artifacts";
  for (const artifact of artifacts) {
    if (artifact?.kind === "code_leaf") {
      list.appendChild(renderCodeLeafArtifact(artifact, { full: false }));
    } else if (artifact?.kind === "plot" && (artifact.preview_data_url || artifact.html || artifact.plotly_json)) {
      const item = document.createElement("div");
      item.className = "stateframe-web-plot-artifact";
      const title = document.createElement("div");
      title.className = "stateframe-web-plot-artifact-title";
      title.textContent = artifact.title || artifact.plot_id || "Plot";
      item.appendChild(title);
      if (full && artifact.plotly_json) {
        item.appendChild(renderPlotlyFigure(artifact, {
          title: artifact.title || artifact.plot_id || "Plot",
        }));
      } else if (full && artifact.html) {
        const frame = document.createElement("iframe");
        frame.className = "stateframe-web-leaf-iframe";
        frame.sandbox = "allow-scripts allow-same-origin";
        frame.srcdoc = artifact.html;
        item.appendChild(frame);
      } else if (artifact.preview_data_url) {
        const image = document.createElement("img");
        image.className = "stateframe-web-plot-artifact-image";
        image.src = artifact.preview_data_url;
        image.alt = artifact.title || "stateframe plot leaf";
        item.appendChild(image);
      } else {
        const placeholder = document.createElement("div");
        placeholder.className = "stateframe-web-leaf-placeholder";
        placeholder.textContent = full ? "Plotly visual metadata is available, but no HTML preview was saved." : "Interactive Plotly visual. Open the leaf for the full render.";
        item.appendChild(placeholder);
      }
      if (!full) item.appendChild(jsonBlock({ spec: artifact.spec, source_lens: artifact.source_lens }));
      list.appendChild(item);
    } else {
      list.appendChild(jsonBlock(artifact));
    }
  }
  return list;
}

function renderLeafOutput(tree, entry, setState, sendCommand, commandStatus, ui) {
  const shell = document.createElement("div");
  shell.className = "stateframe-web-leaf-view";
  if (!tree || !entry) {
    shell.appendChild(empty("Select a leaf to inspect it."));
    return shell;
  }
  const header = document.createElement("div");
  header.className = "stateframe-web-leaf-header";
  const title = document.createElement("div");
  title.className = "stateframe-web-leaf-title";
  title.textContent = entry.title || entry.operation || entry.id;
  const meta = document.createElement("div");
  meta.className = "stateframe-web-leaf-meta";
  meta.textContent = `${entry.kind || "leaf"} / ${entry.operation || "output"} / ${entry.summary?.dependency || "branch"}`;
  header.append(title, meta, renderPullReference(entry, { compact: true }), button("Back", () => setState({ viewMode: "web" })));
  shell.appendChild(header);

  const artifacts = entryOutputArtifacts(entry);
  if (!artifacts.length) {
    shell.appendChild(empty("This entry does not have a renderable leaf output yet."));
    return shell;
  }
  const body = document.createElement("div");
  body.className = "stateframe-web-leaf-body";
  body.dataset.scrollKey = "leaf-output";
  for (const artifact of artifacts) {
    if (artifact.kind === "code_leaf") body.appendChild(renderCodeLeafArtifact(artifact, { full: true }));
    else body.appendChild(renderArtifacts([artifact], { full: true }));
  }
  body.appendChild(renderLeafNotes(entry, sendCommand, commandStatus, ui));
  body.appendChild(section("Leaf Metadata", renderLeafMetadata(entry)));
  shell.appendChild(body);
  return shell;
}

function renderLeafNotes(entry, sendCommand, commandStatus, ui) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-leaf-notes";
  const title = document.createElement("div");
  title.className = "stateframe-web-leaf-notes-title";
  title.textContent = "Notes";
  const saved = String(entry.note || "");
  const draft = Object.prototype.hasOwnProperty.call(ui.leafNoteDrafts, entry.id)
    ? ui.leafNoteDrafts[entry.id]
    : saved;

  const preview = document.createElement("div");
  preview.className = "stateframe-web-markdown";
  preview.replaceChildren(renderMarkdown(draft || "No notes yet."));

  const editor = document.createElement("textarea");
  editor.className = "stateframe-web-textarea stateframe-web-leaf-note-editor";
  editor.placeholder = "Add notes for this leaf. Markdown is supported.";
  editor.value = draft;
  editor.dataset.focusKey = `leaf-note-${entry.id}`;
  editor.addEventListener("input", () => {
    ui.leafNoteDrafts[entry.id] = editor.value;
    preview.replaceChildren(renderMarkdown(editor.value || "No notes yet."));
  });

  const actions = document.createElement("div");
  actions.className = "stateframe-web-action-row";
  const save = button("Save Notes", () => {
    ui.leafNoteDrafts[entry.id] = editor.value;
    sendCommand("save_entry_note", {
      entryId: entry.id,
      note: editor.value,
    });
  });
  const status = document.createElement("span");
  status.className = "stateframe-web-leaf-note-status";
  if (commandStatus?.action === "save_entry_note") {
    status.textContent = commandStatus.status === "saved"
      ? "Notes saved"
      : commandStatus.status === "error"
        ? commandStatus.message || "Could not save notes"
        : "";
  }
  actions.append(save, status);
  wrap.append(title, preview, editor, actions);
  return wrap;
}

function renderLeafMetadata(entry) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-leaf-metadata";
  wrap.appendChild(keyValueList({
    Entry: entry.id || "",
    Parent: entry.parent_id || "",
    Kind: entry.kind || "",
    Operation: entry.operation || "",
    State: entry.state_id || "",
    Time: formatDate(entry.timestamp),
  }));
  if (entry.code) wrap.appendChild(section("Code", codeBlock(entry.code)));
  if (entry.summary && Object.keys(entry.summary).length) wrap.appendChild(section("Summary", jsonBlock(entry.summary)));
  if (entry.params && Object.keys(entry.params).length) wrap.appendChild(section("Params", jsonBlock(entry.params)));
  return wrap;
}

function renderCodeLeafArtifact(artifact, { full = false } = {}) {
  const item = document.createElement("div");
  item.className = "stateframe-web-code-leaf";
  if (full) item.classList.add("is-full");
  const title = document.createElement("div");
  title.className = "stateframe-web-code-leaf-title";
  title.textContent = artifact.title || "Code leaf";
  const meta = document.createElement("div");
  meta.className = "stateframe-web-code-leaf-meta";
  meta.textContent = `${artifact.dependency || "branch"}${artifact.saved ? " / saved" : " / metadata only"}`;
  item.append(title, meta);
  if (artifact.code && full) item.appendChild(section("Code", codeBlock(artifact.code)));
  for (const preview of artifact.previews || []) {
    item.appendChild(renderLeafPreview(preview, { full }));
  }
  if (artifact.saved_files?.length && full) {
    item.appendChild(section("Saved Files", renderSavedFiles(artifact.saved_files)));
  }
  return item;
}

function renderLeafPreview(preview, { full = false } = {}) {
  if (preview.kind === "terminal") {
    const pre = document.createElement("pre");
    pre.className = "stateframe-web-terminal-preview";
    pre.textContent = [preview.stdout || "", preview.stderr || ""].filter(Boolean).join("\n");
    return section("Terminal", pre);
  }
  if ((preview.kind === "image" || preview.kind === "matplotlib") && preview.preview_data_url) {
    const image = document.createElement("img");
    image.className = "stateframe-web-leaf-image";
    image.src = preview.preview_data_url;
    image.alt = preview.name || "stateframe leaf preview";
    return section(preview.name || "Image", image);
  }
  if (preview.kind === "plotly") {
    if (full && preview.plotly_json) {
      return section(preview.name || "Interactive Plot", renderPlotlyFigure(preview, {
        title: preview.name || "Interactive Plot",
      }));
    }
    if (full && preview.html) {
      const frame = document.createElement("iframe");
      frame.className = "stateframe-web-leaf-iframe";
      frame.sandbox = "allow-scripts";
      frame.srcdoc = preview.html;
      return section(preview.name || "Interactive Plot", frame);
    }
    if (preview.preview_data_url) {
      const image = document.createElement("img");
      image.className = "stateframe-web-leaf-image";
      image.src = preview.preview_data_url;
      image.alt = preview.name || "stateframe plot preview";
      return section(preview.name || "Plot Preview", image);
    }
    const placeholder = document.createElement("div");
    placeholder.className = "stateframe-web-leaf-placeholder";
    placeholder.textContent = "Interactive Plotly output saved. Open the leaf for the full render.";
    return section(preview.name || "Plotly", placeholder);
  }
  if (preview.kind === "dataframe") {
    return section(preview.name || "DataFrame", renderDataFramePreview(preview));
  }
  return section(preview.name || preview.kind || "Preview", jsonBlock(preview));
}

function renderDataFramePreview(preview) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-dataframe-preview";
  const meta = document.createElement("div");
  meta.className = "stateframe-web-code-leaf-meta";
  meta.textContent = `${formatInt(preview.row_count || 0)} rows x ${formatInt(preview.column_count || 0)} columns`;
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const tr = document.createElement("tr");
  for (const column of (preview.columns || []).slice(0, 8)) tr.appendChild(th(column));
  thead.appendChild(tr);
  const tbody = document.createElement("tbody");
  for (const row of (preview.rows || []).slice(0, 12)) {
    const bodyRow = document.createElement("tr");
    for (const column of (preview.columns || []).slice(0, 8)) bodyRow.appendChild(td(row[column]));
    tbody.appendChild(bodyRow);
  }
  table.append(thead, tbody);
  wrap.append(meta, table);
  return wrap;
}

function renderSavedFiles(files) {
  const list = document.createElement("div");
  list.className = "stateframe-web-saved-files";
  for (const file of files) {
    const item = document.createElement("div");
    item.className = "stateframe-web-saved-file";
    item.textContent = `${file.kind || "file"} / ${file.format || ""} / ${file.path || ""}`;
    list.appendChild(item);
  }
  return list;
}

function renderVisualizer(visualizer, commandStatus, setVisualizerState, sendCommand, setState, ui, setUi) {
  const shell = document.createElement("div");
  shell.className = "stateframe-web-visualizer";

  if (visualizer.status === "loading") {
    shell.appendChild(empty("Loading visualizer..."));
    return shell;
  }
  if (visualizer.status === "error") {
    const box = empty(visualizer.message || commandStatus.message || "Could not open the visualizer.");
    box.classList.add("is-error");
    shell.appendChild(box);
    return shell;
  }
  if (!visualizer.payload) {
    shell.appendChild(empty("No visualizer is loaded yet. Go back, select a state, then open the visualizer."));
    return shell;
  }

  const payload = visualizer.payload;
  const visualState = normalizeVisualizerState(visualizer.state, payload);
  const definition = visualDefinition(payload, visualState.kind);

  const top = document.createElement("div");
  top.className = "stateframe-web-visualizer-top";
  const title = document.createElement("div");
  title.className = "stateframe-web-viewer-title";
  title.textContent = payload.title || "Visual builder";
  const meta = document.createElement("div");
  meta.className = "stateframe-web-viewer-meta";
  meta.textContent = `${formatInt(payload.view?.row_count || 0)} source rows / ${formatInt((payload.columns || []).length)} columns / Plotly`;
  const render = button("Render", () => sendCommand("render_visualizer", {
    visualSpec: buildVisualSpec(payload, visualState),
    note: visualState.note || "",
  }));
  const save = button("Save Leaf", () => sendCommand("save_visualizer_leaf", {
    visualSpec: buildVisualSpec(payload, visualState),
    note: visualState.note || "",
  }));
  const libraryToggle = tinyButton(visualState.collapsedPanels.library ? "Show Library" : "Hide Library", () => {
    setVisualizerState({
      collapsedPanels: {
        ...visualState.collapsedPanels,
        library: !visualState.collapsedPanels.library,
      },
    });
  }, false, visualState.collapsedPanels.library ? "Show plot library panel" : "Hide plot library panel");
  libraryToggle.classList.add("is-layout");
  const inspectorToggle = tinyButton(visualState.collapsedPanels.inspector ? "Show Inspector" : "Hide Inspector", () => {
    setVisualizerState({
      collapsedPanels: {
        ...visualState.collapsedPanels,
        inspector: !visualState.collapsedPanels.inspector,
      },
    });
  }, false, visualState.collapsedPanels.inspector ? "Show visual inspector panel" : "Hide visual inspector panel");
  inspectorToggle.classList.add("is-layout");
  const layoutControls = document.createElement("div");
  layoutControls.className = "stateframe-web-visual-layout-controls";
  layoutControls.append(libraryToggle, inspectorToggle);
  top.append(title, meta, layoutControls, render, save);
  shell.appendChild(top);

  if (commandStatus?.status === "saved" && commandStatus.action === "save_visualizer_leaf") {
    const saved = document.createElement("div");
    saved.className = "stateframe-web-status is-saved";
    saved.textContent = `Saved visual leaf: ${commandStatus.title || commandStatus.entry_id || ""}`;
    shell.appendChild(saved);
  } else if (commandStatus?.status === "ready" && commandStatus.action === "render_visualizer") {
    const rendered = document.createElement("div");
    rendered.className = "stateframe-web-status is-saved";
    rendered.textContent = commandStatus.message || "Visual rendered";
    shell.appendChild(rendered);
  } else if (commandStatus?.status === "error") {
    const error = document.createElement("div");
    error.className = "stateframe-web-status is-error";
    error.textContent = commandStatus.message || "Visual action failed";
    shell.appendChild(error);
  }

  const body = document.createElement("div");
  body.className = "stateframe-web-visualizer-body";
  body.style.setProperty("--stateframe-visual-library-width", `${visualState.panelWidths.library}px`);
  body.style.setProperty("--stateframe-visual-inspector-width", `${visualState.panelWidths.inspector}px`);
  if (visualState.collapsedPanels.library) body.classList.add("is-library-collapsed");
  if (visualState.collapsedPanels.inspector) body.classList.add("is-inspector-collapsed");
  if (!visualState.collapsedPanels.library) {
    body.appendChild(renderVisualLibrary(payload, visualState, setVisualizerState));
    body.appendChild(horizontalPanelResizer({
      className: "stateframe-web-visual-resizer",
      label: "Resize visual library panel",
      value: visualState.panelWidths.library,
      min: 200,
      max: 440,
      onPreview: (width) => body.style.setProperty("--stateframe-visual-library-width", `${width}px`),
      onCommit: (width) => setVisualizerState({ panelWidths: { ...visualState.panelWidths, library: width } }),
    }));
  } else {
    body.appendChild(renderVisualPanelRail("Library", "Show plot library panel", () => setVisualizerState({
      collapsedPanels: { ...visualState.collapsedPanels, library: false },
    })));
  }
  body.appendChild(renderVisualCanvas(payload, visualizer.preview, visualState, setVisualizerState, sendCommand));
  if (!visualState.collapsedPanels.inspector) {
    body.appendChild(horizontalPanelResizer({
      className: "stateframe-web-visual-resizer",
      label: "Resize visual inspector panel",
      value: visualState.panelWidths.inspector,
      min: 260,
      max: 640,
      direction: -1,
      onPreview: (width) => body.style.setProperty("--stateframe-visual-inspector-width", `${width}px`),
      onCommit: (width) => setVisualizerState({ panelWidths: { ...visualState.panelWidths, inspector: width } }),
    }));
    body.appendChild(renderVisualInspector(payload, definition, visualState, setVisualizerState, ui, setUi));
  } else {
    body.appendChild(renderVisualPanelRail("Inspector", "Show visual inspector panel", () => setVisualizerState({
      collapsedPanels: { ...visualState.collapsedPanels, inspector: false },
    })));
  }
  shell.appendChild(body);
  return shell;
}

function renderVisualLibrary(payload, visualState, setVisualizerState) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-visual-library";
  panel.dataset.scrollKey = "visual-library";
  const header = document.createElement("div");
  header.className = "stateframe-web-panel-header";
  const label = document.createElement("span");
  label.textContent = "Plot Library";
  const collapse = tinyButton("Collapse", () => setVisualizerState({
    collapsedPanels: { ...visualState.collapsedPanels, library: true },
  }), false, "Collapse plot library panel");
  collapse.classList.add("is-layout");
  header.append(label, collapse);
  panel.appendChild(header);
  const groups = new Map();
  for (const definition of payload.catalog?.plot_types || []) {
    const family = definition.family || "Visuals";
    if (!groups.has(family)) groups.set(family, []);
    groups.get(family).push(definition);
  }
  for (const [family, definitions] of groups.entries()) {
    const group = document.createElement("div");
    group.className = "stateframe-web-visual-family";
    const title = document.createElement("div");
    title.className = "stateframe-web-visual-family-title";
    title.textContent = family;
    group.appendChild(title);
    for (const definition of definitions) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "stateframe-web-visual-type";
      if (definition.id === visualState.kind) item.classList.add("is-selected");
      item.addEventListener("click", () => setVisualizerState({
        kind: definition.id,
        fields: defaultFieldsForVisual(payload, definition),
        options: {},
      }));
      const name = document.createElement("div");
      name.className = "stateframe-web-visual-type-title";
      name.textContent = definition.title;
      const description = document.createElement("div");
      description.className = "stateframe-web-visual-type-description";
      description.textContent = definition.description || "";
      item.append(name, description);
      group.appendChild(item);
    }
    panel.appendChild(group);
  }
  return panel;
}

function renderVisualPanelRail(label, title, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "stateframe-web-visual-panel-rail";
  button.title = title;
  button.setAttribute("aria-label", title);
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function renderVisualCanvas(payload, preview, visualState, setVisualizerState, sendCommand) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-visual-canvas";
  panel.dataset.scrollKey = "visual-canvas";
  const controls = document.createElement("div");
  controls.className = "stateframe-web-visual-savebar";
  const title = document.createElement("input");
  title.className = "stateframe-web-input";
  title.placeholder = "Visual title";
  title.dataset.focusKey = "visual-title";
  title.value = visualState.title || "";
  title.addEventListener("input", () => setVisualizerState({ title: title.value }));
  const render = button("Render", () => sendCommand("render_visualizer", {
    visualSpec: buildVisualSpec(payload, { ...visualState, title: title.value }),
    note: visualState.note || "",
  }));
  const save = button("Save Leaf", () => sendCommand("save_visualizer_leaf", {
    visualSpec: buildVisualSpec(payload, { ...visualState, title: title.value }),
    note: visualState.note || "",
  }));
  controls.append(title, render, save);
  panel.appendChild(controls);
  panel.appendChild(renderVisualPreview(preview));
  const note = document.createElement("textarea");
  note.className = "stateframe-web-textarea stateframe-web-visual-note";
  note.placeholder = "Leaf note. Markdown is supported after save.";
  note.dataset.focusKey = "visual-note";
  note.value = visualState.note || "";
  note.addEventListener("input", () => setVisualizerState({ note: note.value }));
  panel.appendChild(section("Leaf Notes", note));
  return panel;
}

function renderVisualPreview(preview) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-preview";
  if (!preview) {
    wrap.appendChild(empty("Choose a plot type, bind columns, then render a preview."));
    return wrap;
  }
  const header = document.createElement("div");
  header.className = "stateframe-web-visual-preview-header";
  header.textContent = `${preview.title || "Visual preview"} / interactive Plotly`;
  wrap.appendChild(header);
  if (preview.plotly_json) {
    wrap.appendChild(renderPlotlyFigure(preview, {
      title: preview.title || "Interactive Plotly preview",
      className: "stateframe-web-visual-plotly",
    }));
  } else if (preview.html) {
    const frame = document.createElement("iframe");
    frame.className = "stateframe-web-visual-iframe";
    frame.sandbox = "allow-scripts allow-same-origin";
    frame.title = preview.title || "Interactive Plotly preview";
    frame.srcdoc = preview.html;
    wrap.appendChild(frame);
  }
  if (preview.preview_data_url) {
    if (preview.html || preview.plotly_json) {
      const fallback = document.createElement("details");
      fallback.className = "stateframe-web-visual-fallback";
      const summary = document.createElement("summary");
      summary.textContent = "Static thumbnail";
      fallback.appendChild(summary);
      fallback.appendChild(renderVisualFallbackImage(preview));
      wrap.appendChild(fallback);
    } else {
      wrap.appendChild(renderVisualFallbackImage(preview));
    }
  }
  if (preview.plotly_json || preview.html || preview.preview_data_url) {
    return wrap;
  }
  wrap.appendChild(jsonBlock(preview));
  return wrap;
}

function renderVisualFallbackImage(preview) {
  const image = document.createElement("img");
  image.className = "stateframe-web-visual-fallback-image";
  image.src = preview.preview_data_url;
  image.alt = preview.title || "visual preview";
  return image;
}

function renderPlotlyFigure(source, options = {}) {
  const figure = plotlyFigureFromSource(source);
  const wrap = document.createElement("div");
  wrap.className = ["stateframe-web-plotly-live", options.className].filter(Boolean).join(" ");
  if (source?.html) {
    wrap.appendChild(renderPlotlyHtmlFrame(source, options));
  } else if (figure) {
    wrap.appendChild(plotlyPlaceholder("Plotly JSON is saved for replay, and the static thumbnail is available below."));
  } else {
    wrap.appendChild(plotlyPlaceholder("Plotly visual metadata is available, but no renderable payload was saved."));
  }

  if (source?.preview_data_url) {
    const fallback = document.createElement("details");
    fallback.className = "stateframe-web-plotly-fallback";
    const summary = document.createElement("summary");
    summary.textContent = "Static thumbnail";
    fallback.appendChild(summary);
    const image = document.createElement("img");
    image.className = "stateframe-web-plotly-fallback-image";
    image.src = source.preview_data_url;
    image.alt = options.title || source.title || source.name || "stateframe plot thumbnail";
    fallback.appendChild(image);
    wrap.appendChild(fallback);
  }
  return wrap;
}

function renderPlotlyHtmlFrame(source, options = {}) {
  const frame = document.createElement("iframe");
  frame.className = ["stateframe-web-leaf-iframe", options.className].filter(Boolean).join(" ");
  frame.sandbox = "allow-scripts allow-same-origin";
  frame.title = options.title || source?.title || source?.name || "Interactive Plotly chart";
  frame.srcdoc = source.html;
  return frame;
}

function plotlyFigureFromSource(source) {
  const raw = source?.plotly_json ?? source;
  const value = parseMaybeJson(raw);
  if (!value || typeof value !== "object") return null;
  if (!Array.isArray(value.data) && !value.layout) return null;
  return value;
}

function parseMaybeJson(value) {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch (_error) {
    return null;
  }
}

function plotlyPlaceholder(message) {
  const placeholder = document.createElement("div");
  placeholder.className = "stateframe-web-leaf-placeholder";
  placeholder.textContent = message;
  return placeholder;
}

function renderVisualInspector(payload, definition, visualState, setVisualizerState, ui, setUi) {
  const panel = document.createElement("aside");
  panel.className = "stateframe-web-visual-inspector";
  panel.dataset.scrollKey = "visual-inspector";
  const header = document.createElement("div");
  header.className = "stateframe-web-panel-header";
  const label = document.createElement("span");
  label.textContent = "Inspector";
  const collapse = tinyButton("Collapse", () => setVisualizerState({
    collapsedPanels: { ...visualState.collapsedPanels, inspector: true },
  }), false, "Collapse visual inspector panel");
  collapse.classList.add("is-layout");
  header.append(label, collapse);
  panel.appendChild(header);
  panel.appendChild(section("Fields", renderVisualFields(payload, definition, visualState, setVisualizerState)));
  panel.appendChild(section("Columns", renderVisualColumns(payload, definition, visualState, setVisualizerState)));
  panel.appendChild(section("Filters", renderVisualFilters(payload, visualState, setVisualizerState)));
  panel.appendChild(section("Options", renderVisualOptions(definition, visualState, setVisualizerState, ui, setUi)));
  return panel;
}

function renderVisualFields(payload, definition, visualState, setVisualizerState) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-fields";
  for (const field of definition.fields || []) {
    const row = document.createElement("label");
    row.className = "stateframe-web-visual-field";
    const label = document.createElement("span");
    label.textContent = `${field.label}${field.required ? " *" : ""}`;
    const select = document.createElement("select");
    select.className = "stateframe-web-select";
    select.dataset.focusKey = `visual-field-${field.slot}`;
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = field.multiple ? "Comma-select below or choose first" : "None";
    select.appendChild(blank);
    for (const column of payload.columns || []) {
      const option = document.createElement("option");
      option.value = column.id;
      option.textContent = column.display_name || column.source_name || column.id;
      select.appendChild(option);
    }
    const current = visualState.fields?.[field.slot];
    select.value = Array.isArray(current) ? current[0] || "" : current || "";
    select.addEventListener("change", () => {
      const next = { ...(visualState.fields || {}) };
      if (field.multiple) next[field.slot] = select.value ? [select.value] : [];
      else if (select.value) next[field.slot] = select.value;
      else delete next[field.slot];
      setVisualizerState({ fields: next });
    });
    row.append(label, select);
    if (field.multiple) {
      const input = document.createElement("input");
      input.className = "stateframe-web-input";
      input.placeholder = "col_a, col_b, col_c";
      input.dataset.focusKey = `visual-field-${field.slot}-multi`;
      input.value = Array.isArray(current) ? current.join(", ") : current || "";
      input.addEventListener("input", () => {
        const next = { ...(visualState.fields || {}) };
        next[field.slot] = input.value.split(",").map((item) => item.trim()).filter(Boolean);
        setVisualizerState({ fields: next });
      });
      row.appendChild(input);
    }
    wrap.appendChild(row);
  }
  return wrap.children.length ? wrap : empty("This visual does not require field bindings.");
}

function renderVisualColumns(payload, definition, visualState, setVisualizerState) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-column-list";
  const assignable = (definition.fields || []).filter((field) => !field.multiple).slice(0, 4);
  for (const column of payload.columns || []) {
    const item = document.createElement("div");
    item.className = "stateframe-web-visual-column";
    const name = document.createElement("div");
    name.className = "stateframe-web-visual-column-name";
    name.textContent = column.display_name || column.source_name || column.id;
    const meta = document.createElement("div");
    meta.className = "stateframe-web-visual-column-meta";
    meta.textContent = `${column.semantic_type || "unknown"} / ${column.dtype || ""}`;
    const actions = document.createElement("div");
    actions.className = "stateframe-web-action-row";
    for (const field of assignable) {
      const assign = tinyButton(field.label, () => {
        const next = { ...(visualState.fields || {}) };
        next[field.slot] = column.id;
        setVisualizerState({ fields: next });
      }, false, `Use as ${field.label}`);
      actions.appendChild(assign);
    }
    item.append(name, meta, actions);
    wrap.appendChild(item);
  }
  return wrap;
}

function renderVisualFilters(payload, visualState, setVisualizerState) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-filters";
  const filters = visualState.filters || [];
  filters.forEach((filter, index) => {
    const row = document.createElement("div");
    row.className = "stateframe-web-visual-filter";
    const column = selectControl(payload.columns || [], filter.column || "", (value) => updateVisualFilter(index, { column: value }, visualState, setVisualizerState), `visual-filter-${index}-column`);
    const op = selectControl((payload.catalog?.filter_ops || []).map((item) => ({ id: item.id, display_name: item.label })), filter.op || "contains", (value) => updateVisualFilter(index, { op: value }, visualState, setVisualizerState), `visual-filter-${index}-op`);
    const value = document.createElement("input");
    value.className = "stateframe-web-input";
    value.placeholder = "Value";
    value.dataset.focusKey = `visual-filter-${index}-value`;
    value.value = filter.value || "";
    value.addEventListener("input", () => updateVisualFilter(index, { value: value.value }, visualState, setVisualizerState));
    const value2 = document.createElement("input");
    value2.className = "stateframe-web-input";
    value2.placeholder = "Value 2";
    value2.dataset.focusKey = `visual-filter-${index}-value2`;
    value2.value = filter.value2 || "";
    value2.addEventListener("input", () => updateVisualFilter(index, { value2: value2.value }, visualState, setVisualizerState));
    const remove = tinyButton("x", () => {
      const next = filters.filter((_item, itemIndex) => itemIndex !== index);
      setVisualizerState({ filters: next });
    }, false, "Remove filter");
    row.append(column, op, value, value2, remove);
    wrap.appendChild(row);
  });
  wrap.appendChild(button("Add Filter", () => {
    const first = payload.columns?.[0]?.id || "";
    setVisualizerState({ filters: [...filters, { column: first, op: "contains", value: "" }] });
  }));
  return wrap;
}

function renderVisualOptions(definition, visualState, setVisualizerState, ui, setUi) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-options";
  for (const group of definition.option_groups || []) {
    const details = document.createElement("details");
    details.className = "stateframe-web-visual-option-group";
    const key = `${definition.id}:${group.id}`;
    details.open = ui.visualOptionOpen[key] !== false;
    details.addEventListener("toggle", () => {
      ui.visualOptionOpen[key] = details.open;
    });
    const summary = document.createElement("summary");
    summary.textContent = group.title;
    details.appendChild(summary);
    const body = document.createElement("div");
    body.className = "stateframe-web-visual-option-body";
    for (const control of group.controls || []) {
      body.appendChild(renderVisualOptionControl(control, visualState, setVisualizerState));
    }
    details.appendChild(body);
    wrap.appendChild(details);
  }
  return wrap;
}

function renderVisualOptionControl(control, visualState, setVisualizerState) {
  const label = document.createElement("label");
  label.className = "stateframe-web-visual-option";
  const title = document.createElement("span");
  title.textContent = control.label;
  const current = Object.prototype.hasOwnProperty.call(visualState.options || {}, control.id)
    ? visualState.options[control.id]
    : control.default ?? "";
  let input;
  if (control.kind === "select") {
    input = document.createElement("select");
    input.className = "stateframe-web-select";
    for (const choice of control.choices || []) {
      const option = document.createElement("option");
      option.value = choice.value;
      option.textContent = choice.label;
      input.appendChild(option);
    }
    input.value = String(current);
    input.addEventListener("change", () => setVisualizerState({ options: { ...(visualState.options || {}), [control.id]: input.value } }));
  } else if (control.kind === "checkbox") {
    input = document.createElement("input");
    input.type = "checkbox";
    input.checked = Boolean(current);
    input.addEventListener("change", () => setVisualizerState({ options: { ...(visualState.options || {}), [control.id]: input.checked } }));
  } else if (control.kind === "textarea") {
    input = document.createElement("textarea");
    input.className = "stateframe-web-textarea";
    input.value = current || "";
    input.addEventListener("input", () => setVisualizerState({ options: { ...(visualState.options || {}), [control.id]: input.value } }));
  } else {
    input = document.createElement("input");
    input.className = "stateframe-web-input";
    input.type = control.kind === "number" ? "number" : "text";
    input.value = current ?? "";
    input.addEventListener("input", () => setVisualizerState({ options: { ...(visualState.options || {}), [control.id]: input.value } }));
  }
  input.dataset.focusKey = `visual-option-${control.id}`;
  label.append(title, input);
  if (control.help) label.appendChild(textSpan(control.help, "stateframe-web-visual-help"));
  return label;
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
  payload.draft = draftSummary(payload, viewerState);
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
  const columnsToggle = button(viewerState.collapsedPanels.columns ? "Show Columns" : "Hide Columns", () => {
    setViewerState({ collapsedPanels: { ...viewerState.collapsedPanels, columns: !viewerState.collapsedPanels.columns } });
  });
  const inspectorToggle = button(viewerState.collapsedPanels.inspector ? "Show Inspector" : "Hide Inspector", () => {
    setViewerState({ collapsedPanels: { ...viewerState.collapsedPanels, inspector: !viewerState.collapsedPanels.inspector } });
  });
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
  const visualizerButton = button("Visualizer", () => {
    setState({ viewMode: "visualizer" });
    sendCommand("open_visualizer", {
      height: payload.view?.height || 640,
      maxRows: 500,
      viewerState,
    });
  });
  loadFull.disabled = !payload.view?.truncated;
  loadFull.title = payload.view?.truncated
    ? "Send all rows for this selected state to the browser preview."
    : "All rows are already loaded in the browser preview.";
  top.append(title, meta, search, matchCount, previousMatch, nextMatch, columnsToggle, inspectorToggle, clear, loadFull, visualizerButton, save);
  shell.appendChild(renderViewerLineageBar(payload, viewerState, ui, setUi));
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
  body.style.setProperty("--stateframe-viewer-columns-width", `${viewerState.panelWidths.columns}px`);
  body.style.setProperty("--stateframe-viewer-inspector-width", `${viewerState.panelWidths.inspector}px`);
  if (viewerState.collapsedPanels.columns) body.classList.add("is-columns-collapsed");
  if (viewerState.collapsedPanels.inspector) body.classList.add("is-inspector-collapsed");
  if (!viewerState.collapsedPanels.columns) {
    body.appendChild(renderViewerColumns(payload, viewerState, setViewerState));
    body.appendChild(horizontalPanelResizer({
      className: "stateframe-web-viewer-resizer",
      label: "Resize columns panel",
      value: viewerState.panelWidths.columns,
      min: 180,
      max: 440,
      onPreview: (width) => body.style.setProperty("--stateframe-viewer-columns-width", `${width}px`),
      onCommit: (width) => setViewerState({ panelWidths: { ...viewerState.panelWidths, columns: width } }),
    }));
  }
  body.appendChild(renderViewerGrid(payload, viewerState, computed, visibleColumns, setViewerState, ui));
  if (!viewerState.collapsedPanels.inspector) {
    body.appendChild(horizontalPanelResizer({
      className: "stateframe-web-viewer-resizer",
      label: "Resize inspector panel",
      value: viewerState.panelWidths.inspector,
      min: 240,
      max: 600,
      direction: -1,
      onPreview: (width) => body.style.setProperty("--stateframe-viewer-inspector-width", `${width}px`),
      onCommit: (width) => setViewerState({ panelWidths: { ...viewerState.panelWidths, inspector: width } }),
    }));
    body.appendChild(renderViewerInspector(payload, viewerState, selectedColumn, setViewerState, sendCommand));
  }
  shell.appendChild(body);

  if (ui.saveBranchOpen) {
    shell.appendChild(renderSaveBranchDialog(viewerState, sendCommand, ui, setUi));
  }
  return shell;
}

function renderViewerLineageBar(payload, viewerState, ui, setUi) {
  const bar = document.createElement("div");
  bar.className = "stateframe-web-lineage";
  const lineage = payload.lineage?.entries || [];
  const trail = document.createElement("div");
  trail.className = "stateframe-web-lineage-trail";
  if (!lineage.length) {
    trail.appendChild(pill("current state"));
  } else {
    for (const [index, entry] of lineage.entries()) {
      if (index > 0) {
        const sep = document.createElement("span");
        sep.className = "stateframe-web-lineage-separator";
        sep.textContent = ">";
        trail.appendChild(sep);
      }
      const chip = document.createElement("span");
      chip.className = "stateframe-web-lineage-chip";
      chip.textContent = entry.title || entry.operation || entry.id;
      chip.title = `${entry.kind || "entry"} / ${entry.operation || ""}`;
      trail.appendChild(chip);
    }
  }

  const draft = draftSummary(payload, viewerState);
  const current = document.createElement("div");
  current.className = "stateframe-web-draft";
  const divider = document.createElement("span");
  divider.className = "stateframe-web-lineage-current";
  divider.textContent = "Current";
  current.appendChild(divider);
  if (!draft.pills.length) {
    current.appendChild(pill("no unsaved changes"));
  } else {
    for (const item of draft.pills) {
      const chip = document.createElement("span");
      chip.className = "stateframe-web-draft-pill";
      chip.textContent = item.label;
      chip.title = JSON.stringify(item.details);
      current.appendChild(chip);
    }
  }

  const details = button(ui.lineageOpen ? "Hide Details" : "Lineage Details", () => setUi({ lineageOpen: !ui.lineageOpen }));
  details.classList.add("is-tiny");
  bar.append(trail, current, details);

  if (ui.lineageOpen) {
    const expanded = document.createElement("div");
    expanded.className = "stateframe-web-lineage-details";
    for (const entry of lineage) {
      const row = document.createElement("div");
      row.className = "stateframe-web-lineage-detail-row";
      row.append(
        kindBadge(entry.kind),
        textSpan(entry.title || entry.operation || entry.id, "stateframe-web-lineage-detail-title"),
        codePill(entry.operation || ""),
      );
      if (entry.summary && Object.keys(entry.summary).length) {
        row.appendChild(textSpan(compactJson(entry.summary), "stateframe-web-lineage-detail-summary"));
      }
      expanded.appendChild(row);
    }
    if (draft.pills.length) {
      const draftRow = document.createElement("div");
      draftRow.className = "stateframe-web-lineage-detail-row";
      draftRow.append(
        kindBadge("draft"),
        textSpan("Unsaved viewer changes", "stateframe-web-lineage-detail-title"),
        textSpan(draft.pills.map((item) => item.label).join(", "), "stateframe-web-lineage-detail-summary"),
      );
      expanded.appendChild(draftRow);
    }
    bar.appendChild(expanded);
  }
  return bar;
}

function renderViewerColumns(payload, state, setViewerState) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-viewer-columns";
  panel.dataset.scrollKey = "viewer-columns";
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
      tinyButton("\u2191", () => setViewerState({ columnOrder: moveId(state.columnOrder, column.id, -1) }), index === 0, "Move column up", true),
      tinyButton("\u2193", () => setViewerState({ columnOrder: moveId(state.columnOrder, column.id, 1) }), index === ordered.length - 1, "Move column down", true),
      tinyButton(hidden.has(column.id) ? "\u21e4" : "\u21e5", () => {
        const next = hidden.has(column.id)
          ? state.hiddenColumnIds.filter((id) => id !== column.id)
          : [...state.hiddenColumnIds, column.id];
        setViewerState({ hiddenColumnIds: next });
      }, false, hidden.has(column.id) ? "Load column back into view" : "Offload column from view", true),
    );
    list.appendChild(row);
  });
  panel.appendChild(list);
  return panel;
}

function renderViewerGrid(payload, state, computed, visibleColumns, setViewerState, ui) {
  const wrap = document.createElement("section");
  wrap.className = "stateframe-web-viewer-grid";
  wrap.dataset.scrollKey = "viewer-grid";
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
        cell.dataset.viewerActiveMatch = "true";
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

function renderViewerInspector(payload, state, column, setViewerState, sendCommand) {
  const inspector = document.createElement("aside");
  inspector.className = "stateframe-web-viewer-inspector";
  inspector.dataset.scrollKey = "viewer-inspector";
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
  inspector.appendChild(section("Visualize", renderViewerPlotControls(column, state, sendCommand)));
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

function renderViewerPlotControls(column, state, sendCommand) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-plot-controls";
  if (!column) return empty("Select a column to build a plot leaf.");
  const kind = plotKindForColumn(column);
  const save = button("Save Plot Leaf", () => sendCommand("save_plot_leaf", {
    plotKind: kind,
    columnName: column.source_name,
    title: `${column.display_name || column.source_name} plot`,
    viewerState: state,
  }));
  const auto = button("Auto Plot", () => sendCommand("save_plot_leaf", {
    plotKind: "column",
    columnName: column.source_name,
    title: `${column.display_name || column.source_name} auto plot`,
    viewerState: state,
  }));
  wrap.append(
    textSpan(`${kind} from current draft`, "stateframe-web-plot-caption"),
    save,
    auto,
  );
  return wrap;
}

function plotKindForColumn(column) {
  const semantic = column.semantic_type || "";
  if (semantic.includes("numeric") || ["amount", "percentage", "proportion"].includes(semantic)) return "distribution.numeric";
  if (semantic.includes("datetime")) return "time.cadence";
  if (column.binary_profile) return "binary.flags";
  if (["category", "string", "postal_code", "geographic"].includes(semantic)) return "categorical.value_counts";
  return "column";
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

function buildVisualSpec(payload, state) {
  return {
    version: 1,
    renderer: "plotly",
    kind: state.kind || visualDefinition(payload, state.kind)?.id || "histogram",
    title: state.title || "",
    note: state.note || "",
    fields: cleanObject(state.fields || {}),
    filters: (state.filters || []).filter((filter) => filter?.column && filter?.op),
    options: cleanObject(state.options || {}),
  };
}

function visualDefinition(payload, kind) {
  const plotTypes = payload?.catalog?.plot_types || [];
  return plotTypes.find((item) => item.id === kind) || plotTypes[0] || { id: "histogram", fields: [], option_groups: [] };
}

function defaultFieldsForVisual(payload, definition) {
  const fields = {};
  for (const field of definition.fields || []) {
    const column = defaultVisualColumn(payload, definition, field);
    if (column) {
      fields[field.slot] = field.multiple ? [column] : column;
      if (field.required) break;
    }
  }
  return fields;
}

function defaultVisualColumn(payload, definition, field = null) {
  const columns = payload?.columns || [];
  if (!columns.length) return null;
  const wanted = new Set(field?.semantic || []);
  const numeric = columns.find((column) => ["numeric", "amount", "percentage", "proportion"].includes(String(column.semantic_type || "").toLowerCase()));
  const datetime = columns.find((column) => String(column.semantic_type || "").toLowerCase().includes("datetime"));
  const categorical = columns.find((column) => ["category", "string", "postal_code", "geographic"].includes(String(column.semantic_type || "").toLowerCase()));
  if (wanted.size) {
    const match = columns.find((column) => wanted.has(String(column.semantic_type || "").toLowerCase()));
    if (match) return match.id;
  }
  if (["histogram", "box", "violin", "ecdf", "scatter", "line", "area"].includes(definition?.id) && numeric) return numeric.id;
  if (definition?.id === "line" && datetime) return datetime.id;
  if (["bar", "pie", "treemap"].includes(definition?.id) && categorical) return categorical.id;
  return columns[0].id || null;
}

function updateVisualFilter(index, patch, state, setVisualizerState) {
  const filters = [...(state.filters || [])];
  filters[index] = { ...(filters[index] || {}), ...patch };
  setVisualizerState({ filters });
}

function selectControl(items, value, onChange, focusKey) {
  const select = document.createElement("select");
  select.className = "stateframe-web-select";
  select.dataset.focusKey = focusKey;
  for (const item of items) {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.display_name || item.source_name || item.label || item.id;
    select.appendChild(option);
  }
  select.value = value || items[0]?.id || "";
  select.addEventListener("change", () => onChange(select.value));
  return select;
}

function cleanObject(value) {
  const result = {};
  for (const [key, item] of Object.entries(value || {})) {
    if (item === null || item === undefined || item === "") continue;
    if (Array.isArray(item) && !item.length) continue;
    result[key] = item;
  }
  return result;
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
  ui.activeMatchIndex = nextIndex;
  ui.pendingViewerMatch = match;
  setViewerState({ selectedColumnId: match.columnId });
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

function draftSummary(payload, state) {
  const columns = payload.columns || [];
  const byId = new Map(columns.map((column) => [column.id, column]));
  const defaultOrder = columns.map((column) => column.id);
  const order = state.columnOrder || defaultOrder;
  const pills = [];
  const filters = Object.entries(state.filters || {})
    .filter(([id, spec]) => byId.has(id) && spec && Object.keys(spec).length)
    .map(([id, spec]) => ({ column: byId.get(id).source_name, spec }));
  if (filters.length) pills.push({ kind: "filters", label: `${filters.length} filter${filters.length === 1 ? "" : "s"}`, details: filters });
  if (state.globalSearch) pills.push({ kind: "search", label: `search: ${state.globalSearch}`, details: state.globalSearch });
  if ((state.sorts || []).length) {
    const sorts = (state.sorts || []).map((sort) => ({
      column: byId.get(sort.id)?.source_name || sort.id,
      direction: sort.direction,
    }));
    pills.push({ kind: "sorts", label: `${sorts.length} sort${sorts.length === 1 ? "" : "s"}`, details: sorts });
  }
  if ((state.hiddenColumnIds || []).length) {
    const hidden = state.hiddenColumnIds.map((id) => byId.get(id)?.source_name || id);
    pills.push({ kind: "hidden_columns", label: `${hidden.length} offloaded`, details: hidden });
  }
  if (JSON.stringify(order) !== JSON.stringify(defaultOrder)) {
    pills.push({ kind: "column_order", label: "reordered columns", details: order.map((id) => byId.get(id)?.source_name || id) });
  }
  return { has_changes: Boolean(pills.length), pills };
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

function horizontalPanelResizer({ className, label, value, min, max, direction = 1, onPreview, onCommit }) {
  const handle = document.createElement("div");
  handle.className = className;
  handle.setAttribute("role", "separator");
  handle.setAttribute("aria-orientation", "vertical");
  handle.setAttribute("aria-label", label);
  handle.tabIndex = 0;

  handle.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    const startX = event.clientX;
    const startValue = Number(value || min);
    handle.classList.add("is-dragging");
    const move = (moveEvent) => {
      const next = clampNumber(startValue + (moveEvent.clientX - startX) * direction, startValue, min, max);
      onPreview(next);
    };
    const stop = (upEvent) => {
      const next = clampNumber(startValue + (upEvent.clientX - startX) * direction, startValue, min, max);
      handle.classList.remove("is-dragging");
      handle.ownerDocument.removeEventListener("pointermove", move);
      handle.ownerDocument.removeEventListener("pointerup", stop);
      onCommit(next);
    };
    handle.ownerDocument.addEventListener("pointermove", move);
    handle.ownerDocument.addEventListener("pointerup", stop, { once: true });
  });

  handle.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const delta = event.key === "ArrowRight" ? 24 : -24;
    const next = clampNumber(Number(value || min) + delta * direction, Number(value || min), min, max);
    onPreview(next);
    onCommit(next);
  });

  return handle;
}

// Any text input that writes to synced widget state can redraw the DOM on each
// update. Give it a stable data-focus-key so focus and caret position survive.
function captureFocus(root, ui) {
  captureScroll(root, ui);
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

function captureScroll(root, ui) {
  const scroll = { ...(ui.scroll || {}) };
  for (const element of root.querySelectorAll("[data-scroll-key]")) {
    const key = element.dataset.scrollKey;
    if (!key) continue;
    scroll[key] = {
      top: element.scrollTop,
      left: element.scrollLeft,
    };
  }
  ui.scroll = scroll;
}

function focusedKey(root) {
  const active = root.ownerDocument.activeElement;
  return active && root.contains(active) ? active.dataset?.focusKey || null : null;
}

function queueRestoreUiState(root, ui) {
  restoreScroll(root, ui);
  restoreFocus(root, ui);
  requestAnimationFrame(() => restoreUiState(root, ui));
}

function restoreUiState(root, ui) {
  restoreScroll(root, ui);
  restoreFocus(root, ui);
  scrollPendingViewerMatch(root, ui);
}

function restoreScroll(root, ui) {
  for (const element of root.querySelectorAll("[data-scroll-key]")) {
    const key = element.dataset.scrollKey;
    const position = key ? ui.scroll?.[key] : null;
    if (!position) continue;
    element.scrollTop = Number(position.top || 0);
    element.scrollLeft = Number(position.left || 0);
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

function scrollPendingViewerMatch(root, ui) {
  if (!ui.pendingViewerMatch) return;
  const target = root.querySelector("[data-viewer-active-match='true']");
  const scroller = target?.closest("[data-scroll-key='viewer-grid']");
  if (target && scroller) {
    centerElementInScroller(target, scroller);
    ui.scroll = {
      ...(ui.scroll || {}),
      "viewer-grid": {
        top: scroller.scrollTop,
        left: scroller.scrollLeft,
      },
    };
  }
  ui.pendingViewerMatch = null;
}

function centerElementInScroller(element, scroller) {
  const elementRect = element.getBoundingClientRect();
  const scrollerRect = scroller.getBoundingClientRect();
  const topDelta = elementRect.top - scrollerRect.top - (scroller.clientHeight / 2) + (elementRect.height / 2);
  const leftDelta = elementRect.left - scrollerRect.left - (scroller.clientWidth / 2) + (elementRect.width / 2);
  scroller.scrollTop += topDelta;
  scroller.scrollLeft += leftDelta;
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

function compactJson(value) {
  const text = JSON.stringify(value);
  return text.length > 160 ? `${text.slice(0, 157)}...` : text;
}

function hydrationCallout(tree, entry) {
  const box = document.createElement("div");
  box.className = "stateframe-web-callout";
  const title = document.createElement("div");
  title.className = "stateframe-web-callout-title";
  const body = document.createElement("div");
  body.className = "stateframe-web-callout-body";
  if (isOutputEntry(entry)) {
    title.textContent = "Output leaf";
    body.textContent = "Open Leaf renders captured output artifacts. Open Viewer is for dataframe branch states that can be pulled or replayed.";
  } else if (entry.has_snapshot) {
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

function renderMarkdown(value) {
  const fragment = document.createDocumentFragment();
  const lines = String(value ?? "").replace(/\r\n/g, "\n").split("\n");
  let paragraph = [];
  let list = null;
  let code = null;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const p = document.createElement("p");
    appendInlineMarkdown(p, paragraph.join(" "));
    fragment.appendChild(p);
    paragraph = [];
  };
  const flushList = () => {
    if (!list) return;
    fragment.appendChild(list.element);
    list = null;
  };

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/, "");
    if (code) {
      if (line.trim().startsWith("```")) {
        const pre = document.createElement("pre");
        const codeEl = document.createElement("code");
        codeEl.textContent = code.lines.join("\n");
        pre.appendChild(codeEl);
        fragment.appendChild(pre);
        code = null;
      } else {
        code.lines.push(rawLine);
      }
      continue;
    }
    if (line.trim().startsWith("```")) {
      flushParagraph();
      flushList();
      code = { lines: [] };
      continue;
    }
    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) {
      flushParagraph();
      flushList();
      const level = Math.min(4, heading[1].length + 2);
      const h = document.createElement(`h${level}`);
      appendInlineMarkdown(h, heading[2]);
      fragment.appendChild(h);
      continue;
    }
    if (/^---+$/.test(line.trim())) {
      flushParagraph();
      flushList();
      fragment.appendChild(document.createElement("hr"));
      continue;
    }
    const bullet = /^\s*[-*]\s+(.+)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.+)$/.exec(line);
    if (bullet || numbered) {
      flushParagraph();
      const ordered = Boolean(numbered);
      if (!list || list.ordered !== ordered) {
        flushList();
        list = { ordered, element: document.createElement(ordered ? "ol" : "ul") };
      }
      const li = document.createElement("li");
      appendInlineMarkdown(li, (bullet || numbered)[1]);
      list.element.appendChild(li);
      continue;
    }
    const quote = /^\s*>\s?(.+)$/.exec(line);
    if (quote) {
      flushParagraph();
      flushList();
      const block = document.createElement("blockquote");
      appendInlineMarkdown(block, quote[1]);
      fragment.appendChild(block);
      continue;
    }
    paragraph.push(line.trim());
  }
  if (code) {
    const pre = document.createElement("pre");
    const codeEl = document.createElement("code");
    codeEl.textContent = code.lines.join("\n");
    pre.appendChild(codeEl);
    fragment.appendChild(pre);
  }
  flushParagraph();
  flushList();
  return fragment;
}

function appendInlineMarkdown(parent, value) {
  const text = String(value ?? "");
  const token = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
  let index = 0;
  for (const match of text.matchAll(token)) {
    if (match.index > index) parent.appendChild(document.createTextNode(text.slice(index, match.index)));
    const raw = match[0];
    if (raw.startsWith("`")) {
      const code = document.createElement("code");
      code.textContent = raw.slice(1, -1);
      parent.appendChild(code);
    } else if (raw.startsWith("**")) {
      const strong = document.createElement("strong");
      strong.textContent = raw.slice(2, -2);
      parent.appendChild(strong);
    } else if (raw.startsWith("*")) {
      const em = document.createElement("em");
      em.textContent = raw.slice(1, -1);
      parent.appendChild(em);
    } else {
      const parsed = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(raw);
      if (parsed) {
        const link = document.createElement("a");
        link.textContent = parsed[1];
        link.href = safeMarkdownHref(parsed[2]);
        link.target = "_blank";
        link.rel = "noreferrer";
        parent.appendChild(link);
      } else {
        parent.appendChild(document.createTextNode(raw));
      }
    }
    index = match.index + raw.length;
  }
  if (index < text.length) parent.appendChild(document.createTextNode(text.slice(index)));
}

function safeMarkdownHref(value) {
  const href = String(value || "").trim();
  if (/^(https?:|mailto:|#|\/)/i.test(href)) return href;
  return "#";
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

function codeBlock(value) {
  const pre = document.createElement("pre");
  pre.className = "stateframe-web-json";
  pre.textContent = String(value ?? "");
  return pre;
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

function buildEntryHierarchy(entries) {
  const byId = new Map(entries.map((entry) => [entry.id, entry]));
  const byParent = new Map();
  const addChild = (parentId, entry) => {
    if (!byParent.has(parentId)) byParent.set(parentId, []);
    byParent.get(parentId).push(entry);
  };
  for (const entry of entries) {
    const parentId = entry.parent_id && entry.parent_id !== entry.id && byId.has(entry.parent_id)
      ? entry.parent_id
      : null;
    addChild(parentId, entry);
  }
  return { roots: byParent.get(null) || [], byParent };
}

function descendantCount(entryId, byParent) {
  const stack = [...(byParent.get(entryId) || [])];
  const seen = new Set();
  let count = 0;
  while (stack.length) {
    const entry = stack.pop();
    if (!entry?.id || seen.has(entry.id)) continue;
    seen.add(entry.id);
    count += 1;
    stack.push(...(byParent.get(entry.id) || []));
  }
  return count;
}

function markDescendantsVisited(entryId, byParent, visited) {
  const stack = [...(byParent.get(entryId) || [])];
  const seen = new Set();
  while (stack.length) {
    const entry = stack.pop();
    if (!entry?.id || seen.has(entry.id)) continue;
    seen.add(entry.id);
    visited.add(entry.id);
    stack.push(...(byParent.get(entry.id) || []));
  }
}

function toggleArrayValue(values, value) {
  const set = new Set(values || []);
  if (set.has(value)) set.delete(value);
  else set.add(value);
  return Array.from(set);
}

function deleteSelectionCount(state) {
  return (state.deleteTreeIds || []).length + (state.deleteEntryIds || []).length;
}

function deleteSelectionLabel(state) {
  const treeCount = (state.deleteTreeIds || []).length;
  const entryCount = (state.deleteEntryIds || []).length;
  const parts = [];
  if (treeCount) parts.push(`${formatInt(treeCount)} tree${treeCount === 1 ? "" : "s"}`);
  if (entryCount) parts.push(`${formatInt(entryCount)} branch/leaf item${entryCount === 1 ? "" : "s"}`);
  return parts.join(" and ") || "selected items";
}

function toggleEntryCollapse(entryId, state, setState) {
  const collapsed = new Set(state.collapsedEntryIds || []);
  if (collapsed.has(entryId)) collapsed.delete(entryId);
  else collapsed.add(entryId);
  setState({ collapsedEntryIds: Array.from(collapsed) });
}

function entryKindClasses(entry, prefix) {
  const kind = String(entry?.kind || "entry").toLowerCase();
  const classes = [`${prefix}-entry-kind-${safeClassName(kind)}`];
  if (kind === "plot") classes.push("is-plot-output");
  else if (isOutputEntry(entry)) classes.push("is-artifact-output");
  if (entry?.has_state) classes.push("is-stateful-output");
  return classes;
}

function isOutputEntry(entry) {
  const kind = String(entry?.kind || "").toLowerCase();
  return kind === "plot" || kind === "artifact" || kind === "report" || hasOutputArtifact(entry);
}

function hasOutputArtifact(entry) {
  return (entry?.artifacts || []).some((artifact) => artifact?.kind && artifact.kind !== "data_snapshot");
}

function entryOutputArtifacts(entry) {
  return (entry?.artifacts || []).filter((artifact) => artifact?.kind && artifact.kind !== "data_snapshot");
}

function safeClassName(value) {
  return String(value || "entry").toLowerCase().replace(/[^a-z0-9_-]+/g, "-");
}

function isImageDataUrl(value) {
  return typeof value === "string" && value.startsWith("data:image/");
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
  el.classList.add(`stateframe-web-kind-${safeClassName(kind)}`);
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

function renderPullReference(entry, { compact = false } = {}) {
  const code = pullCode(entry);
  const wrap = document.createElement("div");
  wrap.className = compact ? "stateframe-web-pull-ref is-compact" : "stateframe-web-pull-ref";
  const text = document.createElement("code");
  text.textContent = code;
  const copy = tinyButton("Copy", () => copyTextToClipboard(code, copy), false, `Copy ${code}`);
  wrap.append(text, copy);
  return wrap;
}

function pullCode(entry) {
  return `sf.pull(${JSON.stringify(entry?.id || "")})`;
}

function copyTextToClipboard(text, trigger) {
  const done = () => {
    if (!trigger) return;
    const previous = trigger.textContent;
    trigger.textContent = "Copied";
    trigger.disabled = true;
    setTimeout(() => {
      trigger.textContent = previous;
      trigger.disabled = false;
    }, 1100);
  };
  const fail = () => {
    if (!trigger) return;
    const previous = trigger.textContent;
    trigger.textContent = "Select code";
    setTimeout(() => { trigger.textContent = previous; }, 1400);
  };
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => {
      if (fallbackCopyText(text)) done();
      else fail();
    });
    return;
  }
  if (fallbackCopyText(text)) done();
  else fail();
}

function fallbackCopyText(text) {
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand("copy");
    area.remove();
    return copied;
  } catch (_) {
    return false;
  }
}

function labeledControl(label, control) {
  const wrap = document.createElement("label");
  wrap.className = "stateframe-web-field";
  const text = document.createElement("span");
  text.className = "stateframe-web-field-label";
  text.textContent = label;
  wrap.append(text, control);
  return wrap;
}

function inputControl(placeholder, value, focusKey, onInput) {
  const input = document.createElement("input");
  input.className = "stateframe-web-input";
  input.placeholder = placeholder;
  input.value = value || "";
  input.dataset.focusKey = focusKey;
  input.addEventListener("input", () => onInput(input.value));
  return input;
}

function checkbox(label, checked, onChange) {
  const wrap = document.createElement("label");
  wrap.className = "stateframe-web-checkbox";
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = Boolean(checked);
  input.addEventListener("change", () => onChange(input.checked));
  const text = document.createElement("span");
  text.textContent = label;
  wrap.append(input, text);
  return wrap;
}

function inlineControls(...items) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-inline-controls";
  wrap.append(...items.filter(Boolean));
  return wrap;
}

function parseParamsJson(value) {
  const text = String(value || "").trim();
  if (!text) return { value: {} };
  try {
    const parsed = JSON.parse(text);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      return { error: "Params JSON must be an object, such as {\"start\": \"2025-01-01\"}." };
    }
    return { value: parsed };
  } catch (error) {
    return { error: `Params JSON is invalid: ${error.message}` };
  }
}

function blankConnectionDraft() {
  return {
    id: "",
    display_name: "",
    description: "",
    import_path: "",
    enabled: true,
    store_query: true,
    store_params: true,
  };
}

function connectionDraftFrom(connection) {
  if (!connection) return blankConnectionDraft();
  return {
    id: connection.id || "",
    display_name: connection.display_name || "",
    description: connection.description || "",
    import_path: connection.import_path || "",
    enabled: connection.enabled !== false,
    store_query: connection.store_query !== false,
    store_params: connection.store_params !== false,
  };
}

function button(label, onClick) {
  const el = document.createElement("button");
  el.type = "button";
  el.className = "stateframe-web-button";
  el.textContent = label;
  el.addEventListener("click", onClick);
  return el;
}

function tinyButton(label, onClick, disabled = false, title = "", icon = false) {
  const el = button(label, onClick);
  el.classList.add("is-tiny");
  if (icon) el.classList.add("is-icon");
  if (title) {
    el.title = title;
    el.setAttribute("aria-label", title);
  }
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

function clampNumber(value, fallback, min, max) {
  const number = Number(value);
  const resolved = Number.isFinite(number) ? number : fallback;
  return Math.min(max, Math.max(min, resolved));
}

export default { render };
