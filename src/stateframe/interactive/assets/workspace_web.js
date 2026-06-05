const VIEWER_PAYLOAD_CACHE = new WeakMap();
const VIEWER_GRID_CELL_BUDGET = 12000;
const VIEWER_MATCH_LIMIT = 1000;
const VIEWER_MATCH_ROW_SCAN_LIMIT = 2500;
const VALUE_OVERVIEW_PROFILE_LIMIT = 6;
const VALUE_OVERVIEW_ROW_LIMIT = 2500;

function render({ model, el, signal }) {
  let payload = model.get("payload") || {};
  let state = normalizeState(model.get("state"), payload);
  let viewer = normalizeViewer(model.get("viewer"));
  let visualizer = normalizeVisualizer(model.get("visualizer"));
  let cleaning = normalizeCleaning(model.get("cleaning"));
  let modeling = normalizeModeling(model.get("modeling"));
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
  let drawFrame = null;
  let modelSaveFrame = null;

  el.classList.add("stateframe-web-host");
  el.style.setProperty("--stateframe-web-height", `${payload.view?.height || 640}px`);

  const root = document.createElement("div");
  root.className = "stateframe-web";
  el.replaceChildren(root);

  function sendWidgetMessage(content) {
    try {
      if (typeof model.send === "function") model.send(content);
    } catch (error) {
      console.warn("stateframe widget message failed", error);
    }
  }

  function scheduleDraw() {
    if (drawFrame !== null) return;
    drawFrame = requestAnimationFrame(() => {
      drawFrame = null;
      draw();
    });
  }

  function scheduleModelSaveChanges() {
    if (modelSaveFrame !== null) return;
    modelSaveFrame = requestAnimationFrame(() => {
      modelSaveFrame = null;
      model.save_changes();
    });
  }

  function flushModelSaveChanges() {
    if (modelSaveFrame !== null) {
      cancelAnimationFrame(modelSaveFrame);
      modelSaveFrame = null;
    }
    model.save_changes();
  }

  function setState(patch) {
    captureFocus(root, ui);
    state = normalizeState({ ...state, ...patch }, payload);
    model.set("state", state);
    scheduleModelSaveChanges();
    sendWidgetMessage({ type: "stateframe_state", state });
    scheduleDraw();
  }

  function setViewerState(patch) {
    captureFocus(root, ui);
    const viewerPayload = viewer.payload || {};
    viewer = normalizeViewer({
      ...viewer,
      state: normalizeViewerState({ ...(viewer.state || {}), ...patch }, viewerPayload),
    });
    model.set("viewer_state", viewer.state);
    scheduleModelSaveChanges();
    scheduleDraw();
  }

  function setVisualizerState(patch) {
    captureFocus(root, ui);
    const visualPayload = visualizer.payload || {};
    visualizer = normalizeVisualizer({
      ...visualizer,
      state: normalizeVisualizerState({ ...(visualizer.state || {}), ...patch }, visualPayload),
    });
    model.set("visualizer_state", visualizer.state);
    scheduleModelSaveChanges();
    scheduleDraw();
  }

  function setCleaningState(patch) {
    captureFocus(root, ui);
    const cleaningPayload = cleaning.payload || {};
    cleaning = normalizeCleaning({
      ...cleaning,
      state: normalizeCleaningState({ ...(cleaning.state || {}), ...patch }, cleaningPayload),
    });
    model.set("cleaning_state", cleaning.state);
    scheduleModelSaveChanges();
    scheduleDraw();
  }

  function setModelingState(patch) {
    captureFocus(root, ui);
    const modelingPayload = modeling.payload || {};
    modeling = normalizeModeling({
      ...modeling,
      state: normalizeModelingState({ ...(modeling.state || {}), ...patch }, modelingPayload),
    });
    model.set("modeling_state", modeling.state);
    scheduleModelSaveChanges();
    scheduleDraw();
  }

  function setUi(patch) {
    captureFocus(root, ui);
    Object.assign(ui, patch);
    scheduleDraw();
  }

  function sendCommand(action, extra = {}) {
    captureFocus(root, ui);
    primeCommandSurface(action, extra);
    const command = commandPayload(action, extra);
    commandStatus = pendingCommandStatus(action);
    model.set("command", command);
    flushModelSaveChanges();
    sendWidgetMessage({ type: "stateframe_command", command, state });
    scheduleDraw();
  }

  function commandPayload(action, extra = {}) {
    return {
      nonce: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      action,
      selectedTreeId: state.selectedTreeId,
      selectedEntryId: state.selectedEntryId,
      saveMode: Boolean(state.saveMode),
      ...extra,
    };
  }

  function primeCommandSurface(action, extra = {}) {
    if (action === "open_viewer") {
      viewer = { status: "loading", payload: null, state: {}, message: "Loading selected state" };
      model.set("viewer", viewer);
      model.set("viewer_state", {});
      state = normalizeState({ ...state, viewMode: "viewer" }, payload);
      model.set("state", state);
    } else if (action === "open_visualizer") {
      visualizer = { status: "loading", payload: null, state: {}, preview: null, message: "Loading visualizer" };
      model.set("visualizer", visualizer);
      model.set("visualizer_state", {});
      state = normalizeState({ ...state, viewMode: "visualizer" }, payload);
      model.set("state", state);
    } else if (action === "open_cleaning") {
      cleaning = { status: "loading", payload: null, state: {}, preview: null, message: "Loading cleaning workbench" };
      model.set("cleaning", cleaning);
      model.set("cleaning_state", {});
      state = normalizeState({ ...state, viewMode: "cleaning" }, payload);
      model.set("state", state);
    } else if (action === "open_modeling") {
      modeling = { status: "loading", payload: null, state: {}, preview: null, message: "Loading modeling workbench" };
      model.set("modeling", modeling);
      model.set("modeling_state", {});
      state = normalizeState({ ...state, viewMode: "modeling" }, payload);
      model.set("state", state);
    } else if (action === "browse_files" && ["files", "get_data"].includes(extra.viewMode)) {
      state = normalizeState({
        ...state,
        viewMode: extra.viewMode,
        getDataTab: extra.getDataTab || state.getDataTab || "files",
        selectedFilePath: null,
      }, payload);
      model.set("state", state);
    } else if (action === "render_visualizer") {
      visualizer = normalizeVisualizer({
        ...visualizer,
        status: "rendering",
        preview: null,
        message: "Rendering visual",
      });
    } else if (action === "save_visualizer_leaf") {
      visualizer = normalizeVisualizer({
        ...visualizer,
        status: "saving",
        message: "Saving visual leaf",
      });
    }
  }

  function pendingCommandStatus(action) {
    const messages = {
      open_viewer: "Loading selected state",
      save_viewer_branch: "Saving branch",
      save_plot_leaf: "Saving plot leaf",
      save_value_overview_leaf: "Saving overview leaf",
      save_entry_note: "Saving notes",
      save_source_connection: "Saving source connection",
      delete_source_connection: "Deleting source connection",
      delete_selected: "Deleting selected items",
      refresh_sources: "Refreshing source connections",
      open_visualizer: "Loading visualizer",
      render_visualizer: "Rendering visual",
      save_visualizer_leaf: "Saving visual leaf",
      open_cleaning: "Loading cleaning workbench",
      apply_cleaning: "Applying cleaning branch",
      open_modeling: "Loading modeling workbench",
      apply_modeling: "Applying modeling branch",
      run_modeling_experiment: "Running modeling experiment",
      run_modeling_comparison: "Running model comparison",
      save_modeling_experiment: "Saving modeling experiment",
      refresh: "Refreshing workspace web",
      browse_files: "Loading workspace files",
      scan_file: "Scanning selected file",
      query_data: "Running source query",
    };
    return { status: "loading", action, message: messages[action] || "Working" };
  }

  function openSelectedViewer(extra = {}) {
    sendCommand("open_viewer", {
      height: payload.view?.height || 640,
      maxRows: 500,
      ...extra,
    });
  }

  function openSelectedVisualizer(extra = {}) {
    sendCommand("open_visualizer", {
      height: payload.view?.height || 640,
      maxRows: 500,
      ...extra,
    });
  }

  function openSelectedCleaning(extra = {}) {
    sendCommand("open_cleaning", {
      height: payload.view?.height || 640,
      maxRows: 500,
      ...extra,
    });
  }

  function openSelectedModeling(extra = {}) {
    sendCommand("open_modeling", {
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
    scheduleDraw();
  }

  function onStateChange() {
    captureFocus(root, ui);
    state = normalizeState(model.get("state"), payload);
    if (focusedKey(root) !== "web-search") ui.webSearchDraft = state.search || "";
    scheduleDraw();
  }

  function onViewerChange() {
    captureFocus(root, ui);
    viewer = normalizeViewer(model.get("viewer"));
    scheduleDraw();
  }

  function onViewerStateChange() {
    captureFocus(root, ui);
    if (viewer.payload) {
      viewer = normalizeViewer({ ...viewer, state: model.get("viewer_state") || viewer.state || {} });
    }
    scheduleDraw();
  }

  function onVisualizerChange() {
    captureFocus(root, ui);
    visualizer = normalizeVisualizer(model.get("visualizer"));
    scheduleDraw();
  }

  function onVisualizerStateChange() {
    captureFocus(root, ui);
    if (visualizer.payload) {
      visualizer = normalizeVisualizer({ ...visualizer, state: model.get("visualizer_state") || visualizer.state || {} });
    }
    scheduleDraw();
  }

  function onCleaningChange() {
    captureFocus(root, ui);
    cleaning = normalizeCleaning(model.get("cleaning"));
    scheduleDraw();
  }

  function onCleaningStateChange() {
    captureFocus(root, ui);
    if (cleaning.payload) {
      cleaning = normalizeCleaning({ ...cleaning, state: model.get("cleaning_state") || cleaning.state || {} });
    }
    scheduleDraw();
  }

  function onModelingChange() {
    captureFocus(root, ui);
    modeling = normalizeModeling(model.get("modeling"));
    scheduleDraw();
  }

  function onModelingStateChange() {
    captureFocus(root, ui);
    if (modeling.payload) {
      modeling = normalizeModeling({ ...modeling, state: model.get("modeling_state") || modeling.state || {} });
    }
    scheduleDraw();
  }

  function onFilesChange() {
    captureFocus(root, ui);
    files = normalizeFiles(model.get("files"));
    scheduleDraw();
  }

  function onCommandStatusChange() {
    captureFocus(root, ui);
    commandStatus = model.get("command_status") || {};
    scheduleDraw();
  }

  model.on("change:payload", onPayloadChange);
  model.on("change:state", onStateChange);
  model.on("change:viewer", onViewerChange);
  model.on("change:viewer_state", onViewerStateChange);
  model.on("change:visualizer", onVisualizerChange);
  model.on("change:visualizer_state", onVisualizerStateChange);
  model.on("change:cleaning", onCleaningChange);
  model.on("change:cleaning_state", onCleaningStateChange);
  model.on("change:modeling", onModelingChange);
  model.on("change:modeling_state", onModelingStateChange);
  model.on("change:files", onFilesChange);
  model.on("change:command_status", onCommandStatusChange);
  signal.addEventListener("abort", () => {
    model.off("change:payload", onPayloadChange);
    model.off("change:state", onStateChange);
    model.off("change:viewer", onViewerChange);
    model.off("change:viewer_state", onViewerStateChange);
    model.off("change:visualizer", onVisualizerChange);
    model.off("change:visualizer_state", onVisualizerStateChange);
    model.off("change:cleaning", onCleaningChange);
    model.off("change:cleaning_state", onCleaningStateChange);
    model.off("change:modeling", onModelingChange);
    model.off("change:modeling_state", onModelingStateChange);
    model.off("change:files", onFilesChange);
    model.off("change:command_status", onCommandStatusChange);
    if (ui.webSearchTimer) clearTimeout(ui.webSearchTimer);
    if (drawFrame !== null) cancelAnimationFrame(drawFrame);
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

    if (state.viewMode === "cleaning") {
      root.appendChild(renderCleaning(
        cleaning,
        commandStatus,
        setCleaningState,
        sendCommand,
        setState,
      ));
      queueRestoreUiState(root, ui);
      return;
    }

    if (state.viewMode === "modeling") {
      root.appendChild(renderModeling(
        modeling,
        commandStatus,
        setModelingState,
        sendCommand,
        setState,
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
    body.appendChild(renderDetail(payload, selected, selectedEntry, state, setState, sendCommand, commandStatus, openSelectedViewer, openSelectedVisualizer, openSelectedCleaning, openSelectedModeling));
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
  const modes = new Set(["web", "viewer", "visualizer", "cleaning", "modeling", "get_data", "files", "leaf"]);
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

function normalizeCleaning(raw) {
  const payload = raw?.payload || null;
  return {
    status: raw?.status || (payload ? "ready" : "empty"),
    payload,
    state: payload ? normalizeCleaningState(raw?.state, payload) : {},
    preview: raw?.preview || null,
    message: raw?.message || "",
  };
}

function normalizeModeling(raw) {
  const payload = raw?.payload || null;
  return {
    status: raw?.status || (payload ? "ready" : "empty"),
    payload,
    state: payload ? normalizeModelingState(raw?.state, payload) : {},
    preview: raw?.preview || null,
    message: raw?.message || "",
  };
}

function normalizeCleaningState(raw, payload) {
  const actions = payload?.cleaning?.actions || [];
  const presets = payload?.cleaning?.presets || [];
  const ids = new Set(actions.map((action) => action.id).filter(Boolean));
  const presetIds = new Set(presets.map((preset) => preset.id).filter(Boolean));
  const defaultIds = actions
    .filter((action) => action.applies_by_default !== false && action.id)
    .map((action) => action.id);
  const selected = Array.isArray(raw?.selectedActionIds)
    ? raw.selectedActionIds.filter((id) => ids.has(id))
    : defaultIds;
  const selectedActionId = ids.has(raw?.selectedActionId)
    ? raw.selectedActionId
    : (selected[0] || actions[0]?.id || null);
  const nullPolicies = new Set(["preserve", "treat_as_false", "treat_as_true", "false_to_null", "true_to_null"]);
  const outputs = new Set(["int", "bool_nullable", "bool", "yes_no", "yn"]);
  const outlierPolicies = new Set(["skip", "flag", "null", "clip", "drop"]);
  const outlierMethods = new Set(["iqr", "zscore", "modified_zscore", "percentile"]);
  const fallbackPreset = presets.find((preset) => preset.id === "safe_defaults")?.id || presets[0]?.id || "";
  const activePreset = raw?.activePreset === "custom" || presetIds.has(raw?.activePreset)
    ? raw.activePreset
    : fallbackPreset;
  return {
    selectedActionIds: selected,
    selectedActionId,
    actionControlValues: normalizeActionControlValues(raw?.actionControlValues, ids),
    binaryNullPolicy: nullPolicies.has(raw?.binaryNullPolicy) ? raw.binaryNullPolicy : "preserve",
    binaryOutput: outputs.has(raw?.binaryOutput) ? raw.binaryOutput : "int",
    applyAmbiguousBinary: Boolean(raw?.applyAmbiguousBinary),
    outlierPolicy: outlierPolicies.has(raw?.outlierPolicy) ? raw.outlierPolicy : "skip",
    outlierMethod: outlierMethods.has(raw?.outlierMethod) ? raw.outlierMethod : "iqr",
    activePreset,
    search: raw?.search || "",
  };
}

function normalizeModelingState(raw, payload) {
  const actions = payload?.modeling?.actions || [];
  const ids = new Set(actions.map((action) => action.id).filter(Boolean));
  const defaultIds = actions
    .filter((action) => action.applies_by_default !== false && action.id)
    .map((action) => action.id);
  const selected = Array.isArray(raw?.selectedActionIds)
    ? raw.selectedActionIds.filter((id) => ids.has(id))
    : defaultIds;
  const selectedActionId = ids.has(raw?.selectedActionId)
    ? raw.selectedActionId
    : (selected[0] || actions[0]?.id || null);
  const scaleMethods = new Set(["none", "standard", "minmax", "robust", "maxabs"]);
  const experiment = normalizeModelingExperiment(raw?.experiment, payload?.default_experiment, payload?.experiment_catalog, payload);
  const comparisonCandidates = modelingComparisonCandidates(payload?.experiment_catalog || {}, experiment.task || "regression");
  const comparisonIds = new Set(comparisonCandidates.map((item) => item.id).filter(Boolean));
  const defaultComparisonIds = comparisonCandidates
    .filter((item) => item.enabled_by_default !== false)
    .map((item) => item.id)
    .filter(Boolean);
  const selectedComparisonIds = Array.isArray(raw?.comparisonCandidateIds)
    ? raw.comparisonCandidateIds.filter((id) => comparisonIds.has(id))
    : defaultComparisonIds;
  return {
    selectedActionIds: selected,
    selectedActionId,
    actionControlValues: normalizeActionControlValues(raw?.actionControlValues, ids),
    includeTarget: raw?.includeTarget !== false,
    dropIdentifiers: raw?.dropIdentifiers !== false,
    impute: raw?.impute !== false,
    addIndicators: raw?.addIndicators !== false,
    encode: raw?.encode !== false,
    dateFeatures: raw?.dateFeatures !== false,
    scaleMethod: scaleMethods.has(raw?.scaleMethod) ? raw.scaleMethod : "none",
    experiment,
    comparisonCandidateIds: selectedComparisonIds,
    search: raw?.search || "",
    runHistory: Array.isArray(raw?.runHistory) ? raw.runHistory.filter((item) => item && typeof item === "object").slice(0, 8) : [],
  };
}

function normalizeModelingExperiment(raw, defaults = {}, catalog = {}, payload = {}) {
  const base = defaults || {};
  const tasks = new Set((catalog?.tasks || []).map((item) => item.id));
  const estimators = new Set((catalog?.estimators || []).map((item) => item.id));
  const split = { ...(base.split || {}), ...(raw?.split || {}) };
  const validation = { ...(base.validation || {}), ...(raw?.validation || {}) };
  const preprocessing = { ...(base.preprocessing || {}), ...(raw?.preprocessing || {}) };
  const search = { ...(base.search || {}), ...(raw?.search || {}) };
  const explanation = { ...(base.explanation || {}), ...(raw?.explanation || {}) };
  const sample = { ...(base.sample || {}), ...(raw?.sample || {}) };
  const clustering = { ...(base.clustering || {}), ...(raw?.clustering || {}) };
  const rowCount = Number(payload?.view?.row_count || 0);
  if (!raw?.sample && rowCount > 10000) {
    sample.enabled = true;
    sample.max_rows = Math.min(rowCount, 10000);
  }
  let features = raw?.features ?? base.features ?? null;
  if (typeof features === "string") {
    features = features
      .replaceAll(",", "\n")
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (Array.isArray(features)) {
    features = features.map((item) => String(item)).filter(Boolean);
  } else {
    features = null;
  }
  return {
    ...base,
    ...raw,
    features,
    task: tasks.has(raw?.task) ? raw.task : (base.task || "auto"),
    estimator: estimators.has(raw?.estimator) ? raw.estimator : (base.estimator || "random_forest"),
    split,
    validation,
    preprocessing,
    search,
    explanation,
    sample,
    clustering,
  };
}

function modelingColumnValue(column) {
  return String(column?.source_name || column?.name || column?.display_name || column?.id || "");
}

function modelingColumnLabel(column) {
  return String(column?.display_name || column?.source_name || column?.name || column?.id || "");
}

function modelingColumnMeta(column) {
  const parts = [column?.semantic_type || "unknown", column?.dtype || ""].filter(Boolean);
  const distinct = Number(column?.distinct_count);
  if (Number.isFinite(distinct)) parts.push(`${formatInt(distinct)} distinct`);
  return parts.join(" / ");
}

function modelingColumnForValue(payload, value) {
  if (value === undefined || value === null || value === "") return null;
  const wanted = String(value);
  return (payload?.columns || []).find((column) => {
    const candidates = [column?.id, column?.source_name, column?.name, column?.display_name, column?.label]
      .filter((item) => item !== undefined && item !== null)
      .map((item) => String(item));
    return candidates.includes(wanted);
  }) || null;
}

function inferModelingTaskForColumn(column) {
  if (!column) return "clustering";
  const semantic = String(column.semantic_type || "").toLowerCase();
  const distinct = Number(column.distinct_count);
  if (["numeric", "numeric-like", "amount", "percentage", "proportion", "numeric_discrete"].includes(semantic) && (!Number.isFinite(distinct) || distinct > 10)) {
    return "regression";
  }
  if (Number.isFinite(distinct) && distinct <= 2) return "binary_classification";
  return "multiclass_classification";
}

function defaultEstimatorForTask(task, current) {
  if (task === "clustering") return "kmeans";
  if (!current || ["kmeans", "agglomerative", "dbscan"].includes(current)) return "random_forest";
  return current;
}

function modelingEstimatorChoices(catalog, task) {
  const choices = (catalog?.estimators || [])
    .filter((item) => !Array.isArray(item.tasks) || item.tasks.includes(task))
    .map((item) => [item.id, item.label || item.id]);
  return choices.length ? choices : [["random_forest", "Random forest"]];
}

function compatibleModelingEstimator(catalog, task, estimator) {
  const choices = modelingEstimatorChoices(catalog, task);
  if (choices.some(([value]) => value === estimator)) return estimator;
  const fallback = defaultEstimatorForTask(task, estimator);
  if (choices.some(([value]) => value === fallback)) return fallback;
  return choices[0][0];
}

function modelingComparisonCandidates(catalog, task) {
  const groups = catalog?.comparison_candidates || {};
  const candidates = groups[task] || groups.regression || [];
  return candidates.filter((item) => item && item.id);
}

function modelingFeatureCandidates(payload, targetValue, options = {}) {
  const target = String(targetValue || "");
  const dropIdentifiers = options.dropIdentifiers !== false;
  return (payload?.columns || []).filter((column) => {
    const value = modelingColumnValue(column);
    if (!value || value === target) return false;
    const semantic = String(column?.semantic_type || "").toLowerCase();
    if (["constant", "mostly_missing", "text", "json-like"].includes(semantic)) return false;
    if (dropIdentifiers && semantic === "identifier") return false;
    return true;
  });
}

function suggestedModelingFeatures(payload, targetValue) {
  const target = String(targetValue || "").toLowerCase();
  const targetCompact = target.replace(/[^a-z0-9]+/g, "");
  const targetTerms = target.split(/[^a-z0-9]+/).filter((part) => part.length >= 4 && part !== "price" && part !== "value");
  return modelingFeatureCandidates(payload, targetValue)
    .filter((column) => {
      const semantic = String(column?.semantic_type || "").toLowerCase();
      const name = modelingColumnValue(column).toLowerCase();
      const compact = name.replace(/[^a-z0-9]+/g, "");
      const distinct = Number(column?.distinct_count);
      if (semantic === "identifier") return false;
      if (["string", "category"].includes(semantic) && Number.isFinite(distinct) && distinct > 80) return false;
      if (targetCompact && compact.includes(targetCompact)) return false;
      if (targetTerms.some((term) => name.includes(term))) return false;
      if (target.includes("price") && name.includes("price_per")) return false;
      return true;
    })
    .slice(0, 28)
    .map((column) => modelingColumnValue(column));
}

function visualColumnLookup(payload) {
  const lookup = new Map();
  for (const column of payload?.columns || []) {
    const id = column?.id;
    if (!id) continue;
    for (const value of [column.id, column.source_name, column.name, column.display_name, column.label]) {
      if (value === undefined || value === null || value === "") continue;
      const key = String(value);
      lookup.set(key, id);
      lookup.set(key.toLowerCase(), id);
    }
  }
  return lookup;
}

function resolveVisualColumnId(value, lookup) {
  if (value === undefined || value === null || value === "") return null;
  const key = String(value);
  return lookup.get(key) || lookup.get(key.toLowerCase()) || null;
}

function normalizeVisualizerState(raw, payload) {
  const catalog = payload?.catalog || {};
  const plotTypes = Array.isArray(catalog.plot_types) ? catalog.plot_types : [];
  const ids = new Set(plotTypes.map((item) => item.id));
  const kind = ids.has(raw?.kind) ? raw.kind : plotTypes[0]?.id || "histogram";
  const definition = plotTypes.find((item) => item.id === kind) || plotTypes[0] || {};
  const lookup = visualColumnLookup(payload);
  const fields = {};
  for (const field of definition.fields || []) {
    const value = raw?.fields?.[field.slot];
    if (field.multiple) {
      const values = Array.isArray(value)
        ? value.map((column) => resolveVisualColumnId(column, lookup)).filter(Boolean)
        : String(value || "")
          .split(",")
          .map((item) => resolveVisualColumnId(item.trim(), lookup))
          .filter(Boolean);
      if (values.length) fields[field.slot] = values;
    } else {
      const resolved = resolveVisualColumnId(value, lookup);
      if (resolved) fields[field.slot] = resolved;
    }
  }
  if (!Object.keys(fields).length) {
    const rawFields = raw?.fields && typeof raw.fields === "object" ? raw.fields : {};
    if (!Object.keys(rawFields).length) {
      Object.assign(fields, defaultFieldsForVisual(payload, definition));
    }
  }
  const filters = Array.isArray(raw?.filters)
    ? raw.filters
      .map((filter) => ({
        ...filter,
        column: resolveVisualColumnId(filter?.column, lookup) || "",
      }))
      .filter((filter) => filter.column)
    : [];
  const fieldOptions = normalizeVisualFieldOptions(payload, definition, fields, raw?.fieldOptions || raw?.field_options || {}, raw?.options || {});
  const targetColumns = [];
  const seenTargets = new Set();
  const rawTargets = Array.isArray(raw?.targetColumns)
    ? raw.targetColumns
    : raw?.targetColumn
      ? [raw.targetColumn]
      : [];
  for (const target of rawTargets) {
    const resolved = resolveVisualColumnId(target, lookup);
    if (!resolved || seenTargets.has(resolved)) continue;
    seenTargets.add(resolved);
    targetColumns.push(resolved);
  }
  return {
    kind,
    fields,
    fieldOptions,
    filters,
    targetColumns,
    options: raw?.options || {},
    controlMode: ["basic", "advanced", "expert"].includes(raw?.controlMode) ? raw.controlMode : "basic",
    controlQuery: raw?.controlQuery || "",
    columnQuery: raw?.columnQuery || "",
    columnTypeFilter: ["all", "numeric", "categorical", "date", "targets", "target_ready", "assigned", "available"].includes(raw?.columnTypeFilter) ? raw.columnTypeFilter : "all",
    columnSort: ["original", "name", "type", "unique_desc", "missing_desc", "assigned_first", "target_relevance"].includes(raw?.columnSort) ? raw.columnSort : "original",
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
  const allIdSet = new Set(allIds);
  const displayedRowCount = Number(payload.view?.displayed_row_count || (payload.rows || []).length || 0);
  const rawOrder = Array.isArray(raw?.columnOrder) ? raw.columnOrder : [];
  const rawOrderSet = new Set(rawOrder);
  const columnOrder = [
    ...rawOrder.filter((id) => allIdSet.has(id)),
    ...allIds.filter((id) => !rawOrderSet.has(id)),
  ];
  const columnRenames = {};
  if (raw?.columnRenames && typeof raw.columnRenames === "object" && !Array.isArray(raw.columnRenames)) {
    for (const [id, value] of Object.entries(raw.columnRenames)) {
      const name = String(value || "").trim();
      if (allIdSet.has(id) && name) columnRenames[id] = name;
    }
  }
  const hiddenColumnIds = Array.isArray(raw?.hiddenColumnIds)
    ? raw.hiddenColumnIds.filter((id) => allIdSet.has(id))
    : [];
  const hiddenSet = new Set(hiddenColumnIds);
  const pinnedColumnIds = Array.isArray(raw?.pinnedColumnIds)
    ? raw.pinnedColumnIds.filter((id) => allIdSet.has(id) && !hiddenSet.has(id))
    : [];
  const pinnedRowIndices = Array.isArray(raw?.pinnedRowIndices)
    ? raw.pinnedRowIndices
      .map((value) => Number(value))
      .filter((value) => Number.isInteger(value) && value >= 0 && value < displayedRowCount)
    : [];
  const sorts = Array.isArray(raw?.sorts)
    ? raw.sorts.filter((sort) => allIdSet.has(sort.id) && ["asc", "desc"].includes(sort.direction))
    : [];
  const columnSort = [
    "original",
    "name_asc",
    "name_desc",
    "type_asc",
    "type_desc",
    "missing_desc",
    "unique_desc",
    "issues_desc",
  ].includes(raw?.columnSort) ? raw.columnSort : "original";
  const selectedCell = raw?.selectedCell && allIdSet.has(raw.selectedCell.columnId)
    && Number.isInteger(Number(raw.selectedCell.rowIndex))
    && Number(raw.selectedCell.rowIndex) >= 0
    && Number(raw.selectedCell.rowIndex) < displayedRowCount
    ? {
      rowIndex: Number(raw.selectedCell.rowIndex),
      columnId: raw.selectedCell.columnId,
    }
    : null;
  return {
    columnOrder,
    columnRenames,
    hiddenColumnIds,
    pinnedColumnIds,
    pinnedRowIndices,
    sorts,
    filters: raw?.filters || {},
    globalSearch: raw?.globalSearch || "",
    columnSearch: raw?.columnSearch || "",
    columnSort,
    selectedColumnId: allIdSet.has(raw?.selectedColumnId) ? raw.selectedColumnId : allIds[0] || null,
    selectedCell,
    showIndex: raw?.showIndex !== false,
    showFilterBar: raw?.showFilterBar !== false,
    widths: raw?.widths || {},
    collapsedPanels: {
      columns: Boolean(raw?.collapsedPanels?.columns),
      inspector: Boolean(raw?.collapsedPanels?.inspector),
    },
    panelWidths: {
      columns: clampNumber(raw?.panelWidths?.columns, 300, 220, 520),
      inspector: clampNumber(raw?.panelWidths?.inspector, 320, 240, 600),
    },
  };
}

function normalizeActionControlValues(raw, ids) {
  if (!raw || typeof raw !== "object") return {};
  const result = {};
  for (const [actionId, values] of Object.entries(raw)) {
    if (!ids.has(actionId) || !values || typeof values !== "object" || Array.isArray(values)) continue;
    result[actionId] = { ...values };
  }
  return result;
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
      : state.viewMode === "cleaning"
        ? "stateframe cleaning"
        : state.viewMode === "modeling"
          ? "stateframe modeling"
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
      : state.viewMode === "cleaning"
        ? statusText(commandStatus) || "Preview, select, and apply cleaning operations as a branch"
        : state.viewMode === "modeling"
          ? statusText(commandStatus) || "Preview feature prep, encoding, imputation, and scaling as a branch"
          : state.viewMode === "get_data" || state.viewMode === "files"
            ? statusText(commandStatus) || `${workspaceName} / ${files.current_path || "."}`
            : statusText(commandStatus) || `${workspaceName} / ${payload.settings?.root || ""}`;
  titleGroup.append(title, subtitle);

  const controls = document.createElement("div");
  controls.className = "stateframe-web-controls";
  const backToWeb = () => setState(backToWebState(commandStatus));

  if (state.viewMode === "viewer") {
    controls.classList.add("is-viewer");
    controls.append(
      button("Back", backToWeb),
      button(state.saveMode ? "Save Mode On" : "Save Mode Off", () => setState({ saveMode: !state.saveMode })),
      button("Save Branch", () => setUi({ saveBranchOpen: true })),
      button("Refresh", () => sendCommand("refresh")),
    );
  } else if (state.viewMode === "visualizer") {
    controls.classList.add("is-viewer");
    controls.append(
      button("Back", backToWeb),
      button(state.saveMode ? "Save Mode On" : "Save Mode Off", () => setState({ saveMode: !state.saveMode })),
      button("Refresh", () => sendCommand("refresh")),
    );
  } else if (state.viewMode === "cleaning") {
    controls.classList.add("is-viewer");
    controls.append(
      button("Back", backToWeb),
      button(state.saveMode ? "Save Mode On" : "Save Mode Off", () => setState({ saveMode: !state.saveMode })),
      button("Refresh", () => sendCommand("refresh")),
    );
  } else if (state.viewMode === "modeling") {
    controls.classList.add("is-viewer");
    controls.append(
      button("Back", backToWeb),
      button(state.saveMode ? "Save Mode On" : "Save Mode Off", () => setState({ saveMode: !state.saveMode })),
      button("Refresh", () => sendCommand("refresh")),
    );
  } else if (state.viewMode === "leaf") {
    controls.classList.add("is-viewer");
    controls.append(
      button("Back", backToWeb),
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
        button("Clean", () => sendCommand("open_cleaning", { height: payload.view?.height || 640, maxRows: 500 })),
        button("Model", () => sendCommand("open_modeling", { height: payload.view?.height || 640, maxRows: 500 })),
        button("Visualizer", () => sendCommand("open_visualizer", { height: payload.view?.height || 640, maxRows: 500 })),
        button("Get Data", () => sendCommand("browse_files", { path: files.current_path || ".", viewMode: "get_data" })),
      );
      if (canDelete) controls.append(button("Delete Mode", () => setState({ deleteMode: true, deleteTreeIds: [], deleteEntryIds: [] })));
      controls.append(button("Refresh", () => sendCommand("refresh")));
    }
  }

  toolbar.append(titleGroup, controls);
  return toolbar;
}

function backToWebState(commandStatus) {
  const patch = { viewMode: "web" };
  if (commandStatus?.status === "saved" && commandStatus.entry_id) {
    patch.selectedEntryId = commandStatus.entry_id;
  }
  return patch;
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

function renderDetail(payload, tree, selectedEntry, state, setState, sendCommand, commandStatus, openSelectedViewer, openSelectedVisualizer, openSelectedCleaning, openSelectedModeling) {
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
    panel.appendChild(section("Selected State", renderEntryDetail(payload, tree, selectedEntry, state, sendCommand, commandStatus, openSelectedViewer, openSelectedVisualizer, openSelectedCleaning, openSelectedModeling, setState)));
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
    if (entry.has_snapshot || entry.has_ancestor_snapshot) footer.append(pill("pull ready"));
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

function renderEntryDetail(payload, tree, entry, state, sendCommand, commandStatus, openSelectedViewer, openSelectedVisualizer, openSelectedCleaning, openSelectedModeling, setState) {
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
  const canOpen = !isLeafOutput && entry.has_state && (entry.has_snapshot || entry.has_ancestor_snapshot || canReplayFromSource(tree, entry) || entry.state?.has_data);
  if (!isLeafOutput) {
    const open = button("Open Viewer", openSelectedViewer);
    open.disabled = !canOpen;
    actions.append(open);
    const visualize = button("Visualizer", () => openSelectedVisualizer());
    visualize.disabled = !canOpen;
    actions.append(visualize);
    const clean = button("Clean", () => openSelectedCleaning());
    clean.disabled = !canOpen;
    actions.append(clean);
    const model = button("Model", () => openSelectedModeling());
    model.disabled = !canOpen;
    actions.append(model);
  }
  if (outputArtifacts.length) {
    actions.append(button("Open Leaf", () => setState({ viewMode: "leaf" })));
  }
  actions.append(renderFlowControls(payload, entry, state, sendCommand, commandStatus));
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
  if (entry.params && Object.keys(entry.params).length) wrap.appendChild(section("Params", renderEntryParams(entry.params)));
  if (entry.artifacts?.length) wrap.appendChild(section("Artifacts", renderArtifacts(entry.artifacts)));
  return wrap;
}

function renderFlowControls(payload, entry, state, sendCommand, commandStatus) {
  const wrap = document.createElement("span");
  wrap.className = "stateframe-web-flow-controls";
  const save = button("Save Flow", () => {
    const suggested = `${entry.title || entry.operation || "Selected path"} flow`;
    const name = window.prompt("Flow name", suggested);
    if (!name || !name.trim()) return;
    sendCommand("save_flow", {
      name: name.trim(),
      entryId: entry.id,
    });
  });
  save.disabled = commandStatus?.status === "loading";
  wrap.appendChild(save);

  const flows = payload.flows || [];
  if (flows.length) {
    const select = document.createElement("select");
    select.className = "stateframe-web-input";
    select.title = "Saved flow";
    for (const flow of flows) {
      const option = document.createElement("option");
      option.value = flow.id;
      option.textContent = flow.name || flow.id;
      select.appendChild(option);
    }
    const run = button("Run Flow", () => {
      const chosen = flows.find((flow) => flow.id === select.value) || flows[0];
      sendCommand("run_flow", {
        flow: select.value,
        name: `${chosen?.name || "flow"} on ${entry.title || entry.id}`,
        saveMode: Boolean(state.saveMode),
      });
    });
    run.disabled = commandStatus?.status === "loading";
    wrap.append(select, run);
  }
  return wrap;
}

function renderArtifacts(artifacts, { full = false } = {}) {
  const list = document.createElement("div");
  list.className = "stateframe-web-artifacts";
  for (const artifact of artifacts) {
    if (artifact?.kind === "code_leaf") {
      list.appendChild(renderCodeLeafArtifact(artifact, { full: false }));
    } else if (artifact?.kind === "model") {
      list.appendChild(renderModelArtifact(artifact, { full }));
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
      if (!full) item.appendChild(disclosureBlock("Plot spec", jsonBlock({ spec: artifact.spec, source_lens: artifact.source_lens })));
      list.appendChild(item);
    } else if (artifact?.kind === "value_overview") {
      list.appendChild(renderValueOverviewArtifact(artifact, { full }));
    } else if (artifact?.kind === "data_snapshot") {
      list.appendChild(renderDataSnapshotArtifact(artifact));
    } else {
      list.appendChild(disclosureBlock(artifact?.kind || "Artifact", jsonBlock(artifact), { open: full }));
    }
  }
  return list;
}

function renderValueOverviewArtifact(artifact, { full = false } = {}) {
  const overview = artifact.overview || {};
  const item = document.createElement("div");
  item.className = "stateframe-web-artifact-card stateframe-web-value-overview-artifact";
  const title = document.createElement("div");
  title.className = "stateframe-web-plot-artifact-title";
  title.textContent = artifact.title || "Selected value overview";
  item.appendChild(title);
  item.appendChild(keyValueList({
    Column: overview.label || overview.column || "",
    Value: overview.formatted_value || formatCell(overview.value),
    "Current view": `${formatInt(overview.current_match_count)} of ${formatInt(overview.current_row_count)}`,
    "Loaded preview": `${formatInt(overview.loaded_match_count)} of ${formatInt(overview.loaded_row_count)}`,
    Row: overview.selected_row_label || (overview.row_index ?? ""),
  }));
  const profile = Array.isArray(overview.profile) ? overview.profile.slice(0, full ? 16 : 6) : [];
  if (profile.length) {
    const profileList = document.createElement("div");
    profileList.className = "stateframe-web-value-profile";
    for (const row of profile) {
      const profileRow = document.createElement("div");
      profileRow.className = "stateframe-web-value-profile-row";
      profileRow.title = row.title || "";
      profileRow.append(
        textSpan(row.label || "", "stateframe-web-value-profile-label"),
        textSpan(row.value || "", "stateframe-web-value-profile-value"),
        textSpan(row.signal || "", `stateframe-web-value-profile-signal is-${row.tone || "neutral"}`),
        textSpan(row.detail || "", "stateframe-web-value-profile-detail"),
      );
      profileList.appendChild(profileRow);
    }
    item.appendChild(section("Profile", profileList));
  }
  if (full) item.appendChild(disclosureBlock("Raw overview", jsonBlock(artifact), { open: false }));
  return item;
}

function renderDataSnapshotArtifact(artifact) {
  const item = document.createElement("div");
  item.className = "stateframe-web-artifact-card";
  const title = document.createElement("div");
  title.className = "stateframe-web-plot-artifact-title";
  title.textContent = "Data snapshot";
  item.appendChild(title);
  item.appendChild(keyValueList({
    Format: artifact.format || "",
    Rows: artifact.row_count !== undefined ? formatInt(artifact.row_count) : "",
    Columns: artifact.column_count !== undefined ? formatInt(artifact.column_count) : "",
    Saved: formatDate(artifact.saved_at),
    Path: displayPath(artifact.path || artifact.metadata_path || ""),
  }));
  item.appendChild(disclosureBlock("Raw artifact", jsonBlock(artifact)));
  return item;
}

function displayPath(value) {
  const text = String(value || "");
  if (text.length <= 72) return text;
  const normalized = text.replace(/\\/g, "/");
  const parts = normalized.split("/").filter(Boolean);
  const tail = parts.slice(-2).join("/");
  return tail ? `.../${tail}` : text.slice(0, 20) + "..." + text.slice(-40);
}

function renderModelArtifact(artifact, { full = false } = {}) {
  const item = document.createElement("div");
  item.className = "stateframe-web-plot-artifact";
  const title = document.createElement("div");
  title.className = "stateframe-web-plot-artifact-title";
  title.textContent = artifact.title || "Modeling experiment";
  item.appendChild(title);
  item.appendChild(keyValueList({
    Target: artifact.target || "None",
    Task: artifact.task || "",
    Estimator: artifact.estimator || "",
    Saved: artifact.saved ? "yes" : "metadata only",
    "Model file": artifact.model_path || "",
    "Result file": artifact.result_path || "",
  }));
  if (artifact.metrics) item.appendChild(section("Metrics", renderModelingMetricTiles(artifact.metrics)));
  if (artifact.assessment) item.appendChild(section("Model Review", renderModelingAssessment(artifact.assessment)));
  const sourceRows = artifact.result?.explanation?.source_features || [];
  if (Array.isArray(sourceRows) && sourceRows.length) {
    item.appendChild(section("Source Importance", renderModelingSourceFeatureBars(sourceRows)));
  }
  if (full && Array.isArray(artifact.saved_files) && artifact.saved_files.length) {
    item.appendChild(section("Saved Files", renderSavedFiles(artifact.saved_files)));
  }
  if (full && artifact.result) {
    item.appendChild(section("Result", jsonBlock({ spec: artifact.spec, warnings: artifact.warnings || [] })));
  }
  return item;
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
  if (entry.summary && Object.keys(entry.summary).length) wrap.appendChild(section("Summary", renderLeafSummary(entry.summary)));
  if (entry.params && Object.keys(entry.params).length) wrap.appendChild(section("Params", renderEntryParams(entry.params)));
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

function renderCleaning(cleaning, commandStatus, setCleaningState, sendCommand, setState) {
  const shell = document.createElement("div");
  shell.className = "stateframe-web-cleaning";

  if (cleaning.status === "loading") {
    shell.appendChild(empty("Loading cleaning workbench..."));
    return shell;
  }
  if (cleaning.status === "error") {
    const box = empty(cleaning.message || commandStatus.message || "Could not open the cleaning workbench.");
    box.classList.add("is-error");
    shell.appendChild(box);
    return shell;
  }
  if (!cleaning.payload) {
    shell.appendChild(empty("No cleaning workbench is loaded yet. Go back, select a state, then open Clean."));
    return shell;
  }

  const payload = cleaning.payload;
  const cleaningState = normalizeCleaningState(cleaning.state, payload);
  const actions = payload.cleaning?.actions || [];
  const selected = new Set(cleaningState.selectedActionIds || []);
  const selectedAction = actions.find((action) => action.id === cleaningState.selectedActionId) || actions.find((action) => selected.has(action.id)) || actions[0] || null;

  const top = document.createElement("div");
  top.className = "stateframe-web-cleaning-top";
  const title = document.createElement("div");
  title.className = "stateframe-web-viewer-title";
  title.textContent = payload.title || "Cleaning workbench";
  const meta = document.createElement("div");
  meta.className = "stateframe-web-viewer-meta";
  meta.textContent = `${formatInt(actions.length)} action${actions.length === 1 ? "" : "s"} / ${formatInt(selected.size)} selected / ${formatInt(payload.view?.row_count || 0)} rows`;
  const apply = button("Apply Branch", () => sendCommand("apply_cleaning", { cleaningState }));
  apply.disabled = selected.size === 0 || (commandStatus?.status === "loading" && commandStatus.action === "apply_cleaning");
  const safePreset = (payload.cleaning?.presets || []).find((preset) => preset.id === "safe_defaults");
  const defaults = button("Select Defaults", () => setCleaningState({
    ...(safePreset
      ? cleaningPresetPatch(safePreset, actions)
      : {
          selectedActionIds: actions.filter((action) => action.applies_by_default !== false).map((action) => action.id).filter(Boolean),
          activePreset: "custom",
        }),
  }));
  const all = button("All", () => setCleaningState({ selectedActionIds: actions.map((action) => action.id).filter(Boolean), activePreset: "custom" }));
  const none = button("None", () => setCleaningState({ selectedActionIds: [], activePreset: "custom" }));
  top.append(title, meta, defaults, all, none, apply);
  shell.appendChild(top);
  const presets = renderCleaningPresets(payload, cleaningState, setCleaningState, actions);
  if (presets) shell.appendChild(presets);

  if (commandStatus?.status === "saved" && commandStatus.action === "apply_cleaning") {
    const saved = document.createElement("div");
    saved.className = "stateframe-web-status is-saved";
    saved.appendChild(textSpan(`Saved: ${commandStatus.title || commandStatus.entry_id || "cleaning branch"}`, ""));
    if (commandStatus.entry_id) {
      const view = button("View Branch", () => setState({ viewMode: "web", selectedEntryId: commandStatus.entry_id }));
      view.classList.add("is-tiny");
      saved.appendChild(view);
    }
    shell.appendChild(saved);
  } else if (commandStatus?.status === "error") {
    const error = document.createElement("div");
    error.className = "stateframe-web-status is-error";
    error.textContent = commandStatus.message || "Action failed";
    shell.appendChild(error);
  }

  const body = document.createElement("div");
  body.className = "stateframe-web-cleaning-body";
  body.appendChild(renderCleaningActions(actions, cleaningState, setCleaningState, "cleaning"));
  body.appendChild(renderCleaningDetail(selectedAction, "cleaning", cleaningState, setCleaningState));
  body.appendChild(renderCleaningControls(payload, cleaningState, setCleaningState));
  shell.appendChild(body);
  return shell;
}

function renderModeling(modeling, commandStatus, setModelingState, sendCommand, setState) {
  const shell = document.createElement("div");
  shell.className = "stateframe-web-cleaning";

  if (modeling.status === "loading") {
    shell.appendChild(empty("Loading modeling workbench..."));
    return shell;
  }
  if (modeling.status === "error") {
    const box = empty(modeling.message || commandStatus.message || "Could not open the modeling workbench.");
    box.classList.add("is-error");
    shell.appendChild(box);
    return shell;
  }
  if (!modeling.payload) {
    shell.appendChild(empty("No modeling workbench is loaded yet. Go back, select a state, then open Model."));
    return shell;
  }

  const payload = modeling.payload;
  const modelingState = normalizeModelingState(modeling.state, payload);
  const targetValue = modelingState.experiment?.target || payload.modeling?.target || "";
  const actions = (payload.modeling?.actions || []).filter((action) => !modelingActionUsesTarget(action, targetValue));
  const visibleActionIds = new Set(actions.map((action) => action.id).filter(Boolean));
  const selected = new Set((modelingState.selectedActionIds || []).filter((id) => visibleActionIds.has(id)));
  const visibleModelingState = {
    ...modelingState,
    selectedActionIds: [...selected],
    selectedActionId: visibleActionIds.has(modelingState.selectedActionId)
      ? modelingState.selectedActionId
      : ([...selected][0] || actions[0]?.id || null),
  };
  const selectedAction = actions.find((action) => action.id === visibleModelingState.selectedActionId) || actions.find((action) => selected.has(action.id)) || actions[0] || null;

  const top = document.createElement("div");
  top.className = "stateframe-web-cleaning-top";
  const title = document.createElement("div");
  title.className = "stateframe-web-viewer-title";
  title.textContent = payload.title || "Modeling readiness";
  const meta = document.createElement("div");
  meta.className = "stateframe-web-viewer-meta";
  meta.textContent = `${formatInt(actions.length)} action${actions.length === 1 ? "" : "s"} / ${formatInt(selected.size)} selected / ${formatInt(payload.view?.row_count || 0)} rows`;
  const apply = button("Apply Branch", () => sendCommand("apply_modeling", { modelingState: visibleModelingState }));
  apply.disabled = selected.size === 0 || (commandStatus?.status === "loading" && commandStatus.action === "apply_modeling");
  const experimentTask = modelingState.experiment?.task || payload.default_experiment?.task || "";
  const runLabel = !payload.modeling?.target && experimentTask === "clustering" ? "Run Clustering" : "Run Experiment";
  const run = button(runLabel, () => sendCommand("run_modeling_experiment", { modelingState: visibleModelingState }));
  run.disabled = commandStatus?.status === "loading" && commandStatus.action === "run_modeling_experiment";
  const runComparison = button("Run Comparison", () => sendCommand("run_modeling_comparison", { modelingState: visibleModelingState }));
  runComparison.disabled = commandStatus?.status === "loading" && commandStatus.action === "run_modeling_comparison";
  const saveModel = button("Save Model Leaf", () => sendCommand("save_modeling_experiment", { modelingState: visibleModelingState }));
  saveModel.disabled = commandStatus?.status === "loading" && ["run_modeling_experiment", "run_modeling_comparison", "save_modeling_experiment"].includes(commandStatus.action);
  const defaults = button("Select Defaults", () => setModelingState({
    selectedActionIds: actions.filter((action) => action.applies_by_default !== false).map((action) => action.id).filter(Boolean),
  }));
  const all = button("All", () => setModelingState({ selectedActionIds: actions.map((action) => action.id).filter(Boolean) }));
  const none = button("None", () => setModelingState({ selectedActionIds: [] }));
  top.append(title, meta, defaults, all, none, run, runComparison, saveModel, apply);
  shell.appendChild(top);

  if (commandStatus?.status === "saved" && commandStatus.action === "apply_modeling") {
    const saved = document.createElement("div");
    saved.className = "stateframe-web-status is-saved";
    saved.appendChild(textSpan(`Saved: ${commandStatus.title || commandStatus.entry_id || "modeling branch"}`, ""));
    if (commandStatus.entry_id) {
      const view = button("View Branch", () => setState({ viewMode: "web", selectedEntryId: commandStatus.entry_id }));
      view.classList.add("is-tiny");
      saved.appendChild(view);
    }
    shell.appendChild(saved);
  } else if (commandStatus?.status === "saved" && commandStatus.action === "save_modeling_experiment") {
    const saved = document.createElement("div");
    saved.className = "stateframe-web-status is-saved";
    saved.appendChild(textSpan(`Saved model: ${commandStatus.title || commandStatus.entry_id || "model leaf"}`, ""));
    if (commandStatus.entry_id) {
      const view = button("Open Leaf", () => setState({ viewMode: "leaf", selectedEntryId: commandStatus.entry_id }));
      view.classList.add("is-tiny");
      saved.appendChild(view);
    }
    shell.appendChild(saved);
  } else if (commandStatus?.status === "error") {
    const error = document.createElement("div");
    error.className = "stateframe-web-status is-error";
    error.textContent = commandStatus.message || "Action failed";
    shell.appendChild(error);
  }
  if (modeling.preview?.kind === "modeling_experiment") {
    shell.appendChild(renderModelingExperimentResult(modeling.preview.result || {}));
  } else if (modeling.preview?.kind === "modeling_comparison") {
    shell.appendChild(renderModelingComparisonResult(modeling.preview.suite || {}));
  }

  const body = document.createElement("div");
  body.className = "stateframe-web-cleaning-body";
  body.appendChild(renderCleaningActions(actions, visibleModelingState, setModelingState, "modeling"));
  body.appendChild(renderCleaningDetail(selectedAction, "modeling", visibleModelingState, setModelingState));
  body.appendChild(renderModelingControls(payload, modelingState, setModelingState));
  shell.appendChild(body);
  return shell;
}

function modelingActionUsesTarget(action, targetValue) {
  if (!targetValue) return false;
  const target = String(targetValue).toLowerCase();
  const compactTarget = target.replace(/[^a-z0-9]+/g, "");
  const actionId = String(action?.action || "");
  if (actionId === "modeling.review_target") return false;
  const values = [
    action?.column,
    action?.preview?.output,
    action?.preview?.numerator,
    action?.preview?.denominator,
    action?.control_values?.output,
    action?.control_values?.numerator,
    action?.control_values?.denominator,
  ]
    .filter((value) => value !== undefined && value !== null)
    .map((value) => String(value).toLowerCase());
  return values.some((value) => {
    const compact = value.replace(/[^a-z0-9]+/g, "");
    return value === target
      || (compactTarget && compact.includes(compactTarget))
      || (target.includes("price") && value.includes("price_per"));
  });
}

function renderCleaningActions(actions, cleaningState, setCleaningState, kind = "cleaning") {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-cleaning-actions";
  panel.dataset.scrollKey = `${kind}-actions`;
  const search = document.createElement("input");
  search.className = "stateframe-web-input";
  search.type = "search";
  search.placeholder = "Search actions";
  search.dataset.focusKey = `${kind}-search`;
  search.value = cleaningState.search || "";
  search.addEventListener("input", () => setCleaningState({ search: search.value }));
  panel.appendChild(search);

  const selected = new Set(cleaningState.selectedActionIds || []);
  const query = String(cleaningState.search || "").trim().toLowerCase();
  const filtered = actions.filter((action) => {
    if (!query) return true;
    return [action.column, action.title, action.action, action.reason, action.risk]
      .some((value) => String(value || "").toLowerCase().includes(query));
  });
  if (!filtered.length) {
    panel.appendChild(empty(`No ${kind} actions match.`));
    return panel;
  }
  const groups = groupBy(filtered, (action) => action.family || action.action || "cleaning");
  for (const [group, groupActions] of Object.entries(groups)) {
    const label = document.createElement("div");
    label.className = "stateframe-web-cleaning-family";
    label.textContent = group;
    panel.appendChild(label);
    for (const action of groupActions) {
      const row = document.createElement("label");
      row.className = "stateframe-web-cleaning-action";
      if (action.id === cleaningState.selectedActionId) row.classList.add("is-selected");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = selected.has(action.id);
      checkbox.addEventListener("change", (event) => {
        event.stopPropagation();
        setCleaningState({ selectedActionIds: toggleArrayValue(cleaningState.selectedActionIds || [], action.id), activePreset: "custom" });
      });
      const main = document.createElement("button");
      main.type = "button";
      main.className = "stateframe-web-cleaning-action-main";
      main.addEventListener("click", (event) => {
        event.preventDefault();
        setCleaningState({ selectedActionId: action.id });
      });
      main.append(
        textSpan(action.title || action.action, "stateframe-web-cleaning-action-title"),
        textSpan(`${action.column} / ${action.risk || "risk"} / ${formatPercent(action.confidence)}`, "stateframe-web-cleaning-action-meta"),
      );
      const count = document.createElement("span");
      count.className = "stateframe-web-cleaning-count";
      count.textContent = action.affected_rows === null || action.affected_rows === undefined
        ? ""
        : formatInt(action.affected_rows);
      row.append(checkbox, main, count);
      panel.appendChild(row);
    }
  }
  return panel;
}

function renderCleaningPresets(payload, cleaningState, setCleaningState, actions) {
  const presets = payload.cleaning?.presets || [];
  if (!presets.length) return null;
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-cleaning-presets";
  for (const preset of presets) {
    const item = button(preset.label || preset.id, () => setCleaningState(cleaningPresetPatch(preset, actions)));
    item.classList.add("stateframe-web-cleaning-preset");
    if (cleaningState.activePreset === preset.id) item.classList.add("is-selected");
    item.title = preset.description || preset.label || preset.id;
    item.setAttribute("aria-label", item.title);
    const count = document.createElement("span");
    count.className = "stateframe-web-cleaning-preset-count";
    count.textContent = formatInt(preset.selectedActionCount || (preset.selectedActionIds || []).length);
    item.appendChild(count);
    wrap.appendChild(item);
  }
  if (cleaningState.activePreset === "custom") {
    const custom = document.createElement("span");
    custom.className = "stateframe-web-cleaning-preset-custom";
    custom.textContent = "Custom";
    wrap.appendChild(custom);
  }
  return wrap;
}

function cleaningPresetPatch(preset, actions) {
  const ids = new Set(actions.map((action) => action.id).filter(Boolean));
  const selectedActionIds = (preset.selectedActionIds || []).filter((id) => ids.has(id));
  const options = preset.options || {};
  return {
    selectedActionIds,
    selectedActionId: selectedActionIds[0] || actions[0]?.id || null,
    actionControlValues: normalizeActionControlValues(preset.actionControlValues || {}, ids),
    binaryNullPolicy: options.binaryNullPolicy || "preserve",
    binaryOutput: options.binaryOutput || "int",
    applyAmbiguousBinary: Boolean(options.applyAmbiguousBinary),
    outlierPolicy: options.outlierPolicy || "skip",
    outlierMethod: options.outlierMethod || "iqr",
    activePreset: preset.id,
  };
}

function renderCleaningDetail(action, kind = "cleaning", planState = {}, setPlanState = null) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-cleaning-detail";
  panel.dataset.scrollKey = `${kind}-detail`;
  if (!action) {
    panel.appendChild(empty(`No ${kind} actions were suggested for this state.`));
    return panel;
  }
  const title = document.createElement("div");
  title.className = "stateframe-web-cleaning-detail-title";
  title.textContent = action.title || action.action;
  const meta = document.createElement("div");
  meta.className = "stateframe-web-cleaning-detail-meta";
  meta.textContent = `${action.column} / ${action.before_dtype || ""}${action.after_dtype ? ` -> ${action.after_dtype}` : ""}`;
  panel.append(title, meta);
  if (action.reason) panel.appendChild(textSpan(action.reason, "stateframe-web-cleaning-reason"));
  panel.appendChild(section("Operation", keyValueList({
    Action: action.action,
    Risk: action.risk,
    Confidence: formatPercent(action.confidence),
    "Affected rows": action.affected_rows === null || action.affected_rows === undefined ? "" : formatInt(action.affected_rows),
    "Applies by default": action.applies_by_default === false ? "no" : "yes",
  })));
  panel.appendChild(section("Preview", renderPreviewObject(action.preview || {})));
  if (Array.isArray(action.examples) && action.examples.length) {
    panel.appendChild(section("Rows To Inspect", renderCleaningExamples(action.examples)));
  }
  if (Array.isArray(action.controls) && action.controls.length) {
    const values = effectiveActionControlValues(action, planState);
    panel.appendChild(section(
      "Controls",
      setPlanState
        ? renderActionControls(action, action.controls, values, planState, setPlanState, kind)
        : renderCleaningControlSummary(action.controls, values),
    ));
  }
  return panel;
}

function renderCleaningControls(payload, cleaningState, setCleaningState) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-cleaning-controls";
  panel.dataset.scrollKey = "cleaning-controls";
  const summary = payload.cleaning || {};
  const actions = summary.actions || [];
  panel.appendChild(section("Selected Impact", renderSelectedCleaningImpact(actions, cleaningState, payload.view?.row_count || 0)));
  panel.appendChild(section("Plan Summary", keyValueList({
    Actions: formatInt(summary.action_count || 0),
    Columns: formatInt(summary.affected_column_count || 0),
    Preset: cleaningPresetLabel(summary.presets || [], cleaningState.activePreset),
    "Binary nulls": cleaningState.binaryNullPolicy,
    "Outlier treatment": cleaningState.outlierPolicy,
  })));

  const binary = document.createElement("div");
  binary.className = "stateframe-web-cleaning-control-stack";
  binary.append(
    selectSetting("Binary output", cleaningState.binaryOutput, [
      ["int", "1 / 0"],
      ["bool_nullable", "True / False / null"],
      ["bool", "True / False"],
      ["yes_no", "Yes / No"],
      ["yn", "Y / N"],
    ], (value) => setCleaningState({ binaryOutput: value, activePreset: "custom" }), "cleaning-binary-output"),
    selectSetting("Null policy", cleaningState.binaryNullPolicy, [
      ["preserve", "Preserve nulls"],
      ["treat_as_false", "Nulls false"],
      ["treat_as_true", "Nulls true"],
      ["false_to_null", "False/0 to null"],
      ["true_to_null", "True/1 to null"],
    ], (value) => setCleaningState({ binaryNullPolicy: value, activePreset: "custom" }), "cleaning-binary-null"),
    checkboxSetting("Apply ambiguous binary mappings", cleaningState.applyAmbiguousBinary, (value) => setCleaningState({ applyAmbiguousBinary: value, activePreset: "custom" }), "cleaning-ambiguous"),
  );
  panel.appendChild(section("Binary Flags", binary));

  const outlier = document.createElement("div");
  outlier.className = "stateframe-web-cleaning-control-stack";
  outlier.append(
    selectSetting("Treatment", cleaningState.outlierPolicy, [
      ["skip", "Inspect only"],
      ["flag", "Add indicator"],
      ["null", "Set null"],
      ["clip", "Clip"],
      ["drop", "Drop rows"],
    ], (value) => setCleaningState({ outlierPolicy: value, activePreset: "custom" }), "cleaning-outlier-policy"),
    selectSetting("Method", cleaningState.outlierMethod, [
      ["iqr", "IQR fences"],
      ["zscore", "Z-score"],
      ["modified_zscore", "Modified z-score"],
      ["percentile", "Percentile"],
    ], (value) => setCleaningState({ outlierMethod: value, activePreset: "custom" }), "cleaning-outlier-method"),
  );
  panel.appendChild(section("Outliers", outlier));
  panel.appendChild(section("Columns", renderCleaningColumnSummary(payload.columns || [])));
  return panel;
}

function renderSelectedCleaningImpact(actions, cleaningState, rowCount = 0) {
  const selected = selectedCleaningActions(actions, cleaningState);
  const effects = selected.map((action) => cleaningActionEffect(action, cleaningState));
  const transforming = effects.filter((effect) => effect.active);
  const reviewOnly = selected.length - transforming.length;
  const affectedRows = selected.reduce((total, action) => total + Number(action.affected_rows || 0), 0);
  const columnCount = new Set(selected
    .map((action) => String(action.column || ""))
    .filter((column) => column && !column.startsWith("__")))
    .size;
  const mediumOrHigher = selected.filter((action) => ["medium", "high"].includes(String(action.risk || "").toLowerCase())).length;
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-cleaning-impact";
  const grid = document.createElement("div");
  grid.className = "stateframe-web-cleaning-impact-grid";
  grid.append(
    cleaningImpactCard("Selected", selected.length),
    cleaningImpactCard("Transforms", transforming.length),
    cleaningImpactCard("Review-only", reviewOnly),
    cleaningImpactCard("Columns", columnCount),
    cleaningImpactCard("Rows", selected.length ? (affectedRows || rowCount || 0) : 0),
    cleaningImpactCard("Risk items", mediumOrHigher),
  );
  wrap.appendChild(grid);
  if (transforming.length) {
    const labels = transforming
      .slice(0, 4)
      .map((effect) => effect.label)
      .filter(Boolean)
      .join(" / ");
    if (labels) wrap.appendChild(textSpan(labels, "stateframe-web-cleaning-impact-note"));
  } else if (selected.length) {
    wrap.appendChild(textSpan("Inspection only", "stateframe-web-cleaning-impact-note"));
  }
  return wrap;
}

function cleaningImpactCard(label, value) {
  const item = document.createElement("div");
  item.className = "stateframe-web-cleaning-impact-card";
  item.append(
    textSpan(formatInt(value), "stateframe-web-cleaning-impact-value"),
    textSpan(label, "stateframe-web-cleaning-impact-label"),
  );
  return item;
}

function cleaningPresetLabel(presets, activePreset) {
  if (activePreset === "custom") return "Custom";
  const preset = presets.find((item) => item.id === activePreset);
  return preset?.label || activePreset || "";
}

function selectedCleaningActions(actions, cleaningState) {
  const selected = new Set(cleaningState.selectedActionIds || []);
  return actions.filter((action) => selected.has(action.id));
}

function cleaningActionEffect(action, cleaningState) {
  const values = effectiveActionControlValues(action, cleaningState);
  const actionType = action.action || action.operation_id || "";
  if (actionType === "column_rename_review") {
    const active = String(values.treatment || "inspect") === "apply";
    return { active, label: active ? "Rename columns" : "Inspect renames" };
  }
  if (actionType === "duplicate_row_review") {
    const active = String(values.treatment || "inspect") === "drop";
    return { active, label: active ? "Drop duplicates" : "Inspect duplicates" };
  }
  if (actionType === "missing_value_review") {
    const treatment = String(values.treatment || "inspect");
    const active = treatment !== "inspect" || Boolean(values.add_indicator);
    return { active, label: active ? `Missing: ${treatment.replace(/_/g, " ")}` : "Inspect missing" };
  }
  if (actionType === "numeric_outlier_review") {
    let treatment = String(values.treatment || cleaningState.outlierPolicy || "skip");
    if (["inspect", "skip"].includes(treatment) && cleaningState.outlierPolicy !== "skip") treatment = cleaningState.outlierPolicy;
    const active = !["inspect", "skip"].includes(treatment);
    return { active, label: active ? `Outliers: ${treatment}` : "Inspect outliers" };
  }
  if (actionType === "geo_coordinate_review") {
    const treatment = String(values.treatment || "inspect");
    const active = !["inspect", "skip", ""].includes(treatment);
    return { active, label: active ? `Coordinates: ${treatment.replace(/_/g, " ")}` : "Inspect coordinates" };
  }
  if (actionType === "category_value_review") {
    const active = mappingHasEntries(values.mapping);
    return { active, label: active ? "Map categories" : "Inspect categories" };
  }
  if (actionType === "binary_mapping_review") {
    const active = Boolean(cleaningState.applyAmbiguousBinary);
    return { active, label: active ? "Map reviewed binaries" : "Inspect binaries" };
  }
  if (actionType === "trim_strings") {
    const active = values.strip !== false;
    return { active, label: active ? "Trim strings" : "Inspect strings" };
  }
  if (actionType === "missing_like_to_null") return { active: true, label: "Missing tokens to null" };
  if (actionType === "parse_numeric") return { active: true, label: "Parse numbers" };
  if (actionType === "parse_datetime") return { active: true, label: "Parse dates" };
  if (actionType === "binary_mapping") return { active: true, label: "Map binaries" };
  return { active: true, label: action.title || actionType };
}

function mappingHasEntries(value) {
  if (!value) return false;
  if (typeof value === "object" && !Array.isArray(value)) return Object.keys(value).length > 0;
  const text = String(value || "").trim();
  return Boolean(text);
}

function renderModelingControls(payload, modelingState, setModelingState) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-cleaning-controls";
  panel.dataset.scrollKey = "modeling-controls";
  const summary = payload.modeling || {};
  const experiment = modelingState.experiment || payload.default_experiment || {};
  const updateExperiment = (patch) => setModelingState({ experiment: mergeDeep(experiment, patch) });
  const targetColumn = modelingColumnForValue(payload, experiment.target || summary.target);
  const effectiveTask = (experiment.task && experiment.task !== "auto") ? experiment.task : inferModelingTaskForColumn(targetColumn);
  const estimatorExperiment = {
    ...experiment,
    task: effectiveTask,
    estimator: compatibleModelingEstimator(payload.experiment_catalog || {}, effectiveTask, experiment.estimator),
  };
  const sample = experiment.sample || {};
  const featureCount = Array.isArray(experiment.features) && experiment.features.length ? formatInt(experiment.features.length) : "Auto";
  panel.appendChild(section("Plan Summary", keyValueList({
    Actions: formatInt(summary.action_count || 0),
    Target: targetColumn ? modelingColumnLabel(targetColumn) : "No target selected",
    Task: experiment.task || summary.task || "auto",
    Features: Array.isArray(experiment.features) && experiment.features.length ? `${featureCount} selected` : "Auto-selected",
    "Rows modeled": sample.enabled && sample.max_rows ? `up to ${formatInt(sample.max_rows)}` : "All available",
    "Scale method": modelingState.scaleMethod,
  })));

  const toggles = document.createElement("div");
  toggles.className = "stateframe-web-cleaning-control-stack";
  const featureSettings = [
    checkboxSetting("Drop identifiers", modelingState.dropIdentifiers, (value) => setModelingState({ dropIdentifiers: value }), "modeling-drop-identifiers"),
    checkboxSetting("Impute missing values", modelingState.impute, (value) => setModelingState({ impute: value }), "modeling-impute"),
    checkboxSetting("Add imputation indicators", modelingState.addIndicators, (value) => setModelingState({ addIndicators: value }), "modeling-indicators"),
    checkboxSetting("Encode categories", modelingState.encode, (value) => setModelingState({ encode: value }), "modeling-encode"),
    checkboxSetting("Add date features", modelingState.dateFeatures, (value) => setModelingState({ dateFeatures: value }), "modeling-date-features"),
  ];
  if (summary.target) {
    featureSettings.unshift(checkboxSetting("Keep target column", modelingState.includeTarget, (value) => setModelingState({ includeTarget: value }), "modeling-include-target"));
  }
  toggles.append(...featureSettings);
  panel.appendChild(section("Feature Prep", toggles));

  const scaling = document.createElement("div");
  scaling.className = "stateframe-web-cleaning-control-stack";
  scaling.append(
    selectSetting("Numeric scaling", modelingState.scaleMethod, [
      ["none", "None"],
      ["standard", "Standard"],
      ["minmax", "Min/max"],
      ["robust", "Robust"],
      ["maxabs", "Max abs"],
    ], (value) => setModelingState({ scaleMethod: value }), "modeling-scale"),
  );
  panel.appendChild(section("Scaling", scaling));
  panel.appendChild(section("Experiment", renderModelingExperimentControls(payload, modelingState, setModelingState)));
  panel.appendChild(section("Estimator Settings", renderModelingEstimatorParamControls(estimatorExperiment, updateExperiment)));
  panel.appendChild(section("Model Candidates", renderModelingComparisonCandidateControls(payload, modelingState, setModelingState)));
  panel.appendChild(section("Feature Scope", renderModelingFeaturePicker(payload, modelingState, setModelingState)));
  if (Array.isArray(modelingState.runHistory) && modelingState.runHistory.length) {
    panel.appendChild(section("Run Comparison", renderModelingRunHistory(modelingState.runHistory)));
  }
  panel.appendChild(section("Columns", renderCleaningColumnSummary(payload.columns || [])));
  return panel;
}

function renderModelingRunHistory(rows) {
  const table = document.createElement("table");
  table.className = "stateframe-web-table";
  const thead = document.createElement("thead");
  const head = document.createElement("tr");
  ["run", "estimator", "rows", "primary metric", "warnings"].forEach((key) => head.appendChild(th(key)));
  thead.appendChild(head);
  const tbody = document.createElement("tbody");
  for (const row of rows.slice(0, 8)) {
    const metrics = row.metrics || {};
    const primaryKey = ["r2", "roc_auc", "accuracy", "f1", "mae", "rmse", "silhouette"].find((key) => metrics[key] !== undefined && metrics[key] !== null) || Object.keys(metrics)[0] || "";
    const tr = document.createElement("tr");
    tr.append(
      td(row.candidate_label || row.entry_id || row.id || ""),
      td(`${row.estimator || ""} / ${row.task || ""}`),
      td(formatInt(row.row_count || 0)),
      td(primaryKey ? `${primaryKey}: ${formatModelingMetricValue(primaryKey, metrics[primaryKey])}` : ""),
      td(formatInt(row.warning_count || 0)),
    );
    tbody.appendChild(tr);
  }
  table.append(thead, tbody);
  return table;
}

function renderModelingExperimentControls(payload, modelingState, setModelingState) {
  const catalog = payload.experiment_catalog || {};
  const experiment = modelingState.experiment || payload.default_experiment || {};
  const updateExperiment = (patch) => setModelingState({ experiment: mergeDeep(experiment, patch) });
  const stack = document.createElement("div");
  stack.className = "stateframe-web-cleaning-control-stack";
  const columns = payload.columns || [];
  const targetChoices = [["", "No target (clustering)"], ...columns.map((column) => [modelingColumnValue(column), modelingColumnLabel(column)])];
  const explanationChoices = (catalog.explanation?.methods || []).map((item) => [item.id, item.label || item.id]);
  const targetColumn = modelingColumnForValue(payload, experiment.target);
  const effectiveTask = (experiment.task && experiment.task !== "auto") ? experiment.task : inferModelingTaskForColumn(targetColumn);
  const estimatorChoices = modelingEstimatorChoices(catalog, effectiveTask);
  const estimatorValue = compatibleModelingEstimator(catalog, effectiveTask, experiment.estimator);
  const onTargetChange = (value) => {
    const targetColumn = modelingColumnForValue(payload, value);
    const task = value ? inferModelingTaskForColumn(targetColumn) : "clustering";
    const features = Array.isArray(experiment.features) ? experiment.features.filter((feature) => feature !== value) : experiment.features;
    updateExperiment({
      target: value || null,
      task,
      estimator: defaultEstimatorForTask(task, experiment.estimator),
      features,
    });
  };
  stack.append(
    selectSetting("Target", experiment.target || "", targetChoices, onTargetChange, "modeling-exp-target"),
    selectSetting("Task", experiment.task || "auto", (catalog.tasks || []).map((item) => [item.id, item.label || item.id]), (value) => {
      const nextTask = value === "auto" ? inferModelingTaskForColumn(targetColumn) : value;
      updateExperiment({ task: value, estimator: defaultEstimatorForTask(nextTask, experiment.estimator) });
    }, "modeling-exp-task"),
    selectSetting("Estimator", estimatorValue, estimatorChoices, (value) => updateExperiment({ estimator: value }), "modeling-exp-estimator"),
    checkboxSetting("Limit rows", Boolean(experiment.sample?.enabled), (value) => updateExperiment({ sample: { enabled: value } }), "modeling-exp-sample-enabled"),
    numberSetting("Max training rows", experiment.sample?.max_rows ?? "", (value) => updateExperiment({ sample: { max_rows: value === "" ? null : Number(value), enabled: value !== "" ? true : Boolean(experiment.sample?.enabled) } }), "modeling-exp-sample-rows", "100", null, "500"),
    numberSetting("Test size", experiment.split?.test_size ?? 0.25, (value) => updateExperiment({ split: { test_size: Number(value) } }), "modeling-exp-test-size", "0.05", "0.6", "0.05"),
    numberSetting("CV folds", experiment.validation?.cv_folds ?? 5, (value) => updateExperiment({ validation: { cv_folds: Number(value) } }), "modeling-exp-cv", "2", "20", "1"),
    selectSetting("Validation", experiment.validation?.strategy || "holdout", (catalog.validation?.strategies || []).map((item) => [item.id, item.label || item.id]), (value) => updateExperiment({ validation: { strategy: value } }), "modeling-exp-validation"),
    selectSetting("Encoder", experiment.preprocessing?.encoder || "onehot", (catalog.preprocessing?.encoders || []).map((item) => [item.id, item.label || item.id]), (value) => updateExperiment({ preprocessing: { encoder: value } }), "modeling-exp-encoder"),
    selectSetting("Scaler", experiment.preprocessing?.scaler || "auto", (catalog.preprocessing?.scalers || []).map((item) => [item.id, item.label || item.id]), (value) => updateExperiment({ preprocessing: { scaler: value } }), "modeling-exp-scaler"),
    selectSetting("Explanation", experiment.explanation?.method || "auto", explanationChoices.length ? explanationChoices : [["auto", "Auto"], ["permutation", "Permutation"], ["model_importance", "Model native"]], (value) => updateExperiment({ explanation: { method: value } }), "modeling-exp-explanation-method"),
    checkboxSetting("Grid search", Boolean(experiment.search?.enabled), (value) => updateExperiment({ search: { enabled: value } }), "modeling-exp-grid"),
    checkboxSetting("Explain model", experiment.explanation?.enabled !== false, (value) => updateExperiment({ explanation: { enabled: value } }), "modeling-exp-shap"),
  );
  return stack;
}

function renderModelingEstimatorParamControls(experiment, updateExperiment) {
  const stack = document.createElement("div");
  stack.className = "stateframe-web-cleaning-control-stack";
  const estimator = experiment.estimator || "random_forest";
  const task = experiment.task || "auto";
  const params = experiment.estimator_params || {};
  const clustering = experiment.clustering || {};
  const setParam = (key, value) => updateExperiment({ estimator_params: { [key]: nullableNumber(value) } });
  const setRawParam = (key, value) => updateExperiment({ estimator_params: { [key]: value } });
  const setClustering = (key, value) => updateExperiment({ clustering: { [key]: nullableNumber(value) } });

  if (estimator === "random_forest") {
    stack.append(
      numberSetting("Trees", params.n_estimators ?? 160, (value) => setParam("n_estimators", value), "modeling-param-rf-trees", "10", "1000", "10"),
      numberSetting("Max depth", params.max_depth ?? "", (value) => setParam("max_depth", value), "modeling-param-rf-depth", "1", "100", "1"),
      numberSetting("Min leaf", params.min_samples_leaf ?? 2, (value) => setParam("min_samples_leaf", value), "modeling-param-rf-leaf", "1", "100", "1"),
    );
  } else if (estimator === "knn") {
    stack.append(
      numberSetting("Neighbors", params.n_neighbors ?? 5, (value) => setParam("n_neighbors", value), "modeling-param-knn-neighbors", "1", "100", "1"),
      selectSetting("Weights", params.weights || "uniform", [["uniform", "Uniform"], ["distance", "Distance"]], (value) => setRawParam("weights", value), "modeling-param-knn-weights"),
    );
  } else if (estimator === "linear") {
    if (["binary_classification", "multiclass_classification"].includes(task)) {
      stack.appendChild(numberSetting("Regularization C", params.C ?? 1, (value) => setParam("C", value), "modeling-param-linear-c", "0.001", "1000", "0.1"));
    } else {
      stack.appendChild(numberSetting("Ridge alpha", params.alpha ?? 1, (value) => setParam("alpha", value), "modeling-param-linear-alpha", "0", "1000", "0.1"));
    }
  } else if (estimator === "xgboost") {
    stack.append(
      numberSetting("Trees", params.n_estimators ?? 80, (value) => setParam("n_estimators", value), "modeling-param-xgb-trees", "10", "1000", "10"),
      numberSetting("Max depth", params.max_depth ?? 4, (value) => setParam("max_depth", value), "modeling-param-xgb-depth", "1", "20", "1"),
      numberSetting("Learning rate", params.learning_rate ?? 0.08, (value) => setParam("learning_rate", value), "modeling-param-xgb-rate", "0.001", "1", "0.01"),
    );
  } else if (["kmeans", "agglomerative"].includes(estimator)) {
    stack.appendChild(numberSetting("Clusters", clustering.n_clusters ?? 3, (value) => setClustering("n_clusters", value), "modeling-param-clusters", "2", "30", "1"));
  } else if (estimator === "dbscan") {
    stack.append(
      numberSetting("Epsilon", clustering.eps ?? 0.5, (value) => setClustering("eps", value), "modeling-param-dbscan-eps", "0.01", "100", "0.1"),
      numberSetting("Min samples", clustering.min_samples ?? 5, (value) => setClustering("min_samples", value), "modeling-param-dbscan-min", "1", "100", "1"),
    );
  }
  return stack.children.length ? stack : empty("No additional settings for this estimator.");
}

function nullableNumber(value) {
  if (value === "" || value === null || value === undefined) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function renderModelingComparisonCandidateControls(payload, modelingState, setModelingState) {
  const experiment = modelingState.experiment || payload.default_experiment || {};
  const targetColumn = modelingColumnForValue(payload, experiment.target || payload.modeling?.target);
  const task = (experiment.task && experiment.task !== "auto") ? experiment.task : inferModelingTaskForColumn(targetColumn);
  const candidates = modelingComparisonCandidates(payload.experiment_catalog || {}, task);
  const selected = new Set(Array.isArray(modelingState.comparisonCandidateIds) ? modelingState.comparisonCandidateIds : []);
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-model-feature-scope";
  const toolbar = document.createElement("div");
  toolbar.className = "stateframe-web-model-feature-toolbar";
  toolbar.appendChild(textSpan(`${formatInt(selected.size)} candidate${selected.size === 1 ? "" : "s"} selected`, "stateframe-web-visual-control-count"));
  const defaults = button("Suggested", () => setModelingState({
    comparisonCandidateIds: candidates.filter((item) => item.enabled_by_default !== false).map((item) => item.id),
  }));
  defaults.classList.add("is-tiny");
  const all = button("All", () => setModelingState({ comparisonCandidateIds: candidates.map((item) => item.id) }));
  all.classList.add("is-tiny");
  toolbar.append(defaults, all);
  wrap.appendChild(toolbar);

  const list = document.createElement("div");
  list.className = "stateframe-web-model-feature-list";
  for (const candidate of candidates) {
    const item = document.createElement("label");
    item.className = "stateframe-web-model-feature-option";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = selected.has(candidate.id);
    input.addEventListener("change", () => {
      const next = new Set(selected);
      if (input.checked) next.add(candidate.id);
      else next.delete(candidate.id);
      setModelingState({ comparisonCandidateIds: [...next] });
    });
    const text = document.createElement("span");
    const params = candidate.estimator_params || candidate.clustering || {};
    text.append(
      textSpan(candidate.label || candidate.id, "stateframe-web-visual-column-name"),
      textSpan(`${candidate.estimator || ""}${candidate.optional ? " / optional" : ""}${Object.keys(params).length ? ` / ${compactJson(params)}` : ""}`, "stateframe-web-visual-column-meta"),
    );
    item.append(input, text);
    list.appendChild(item);
  }
  wrap.appendChild(list.children.length ? list : empty("No comparison candidates are available for this task."));
  return wrap;
}

function renderModelingFeaturePicker(payload, modelingState, setModelingState) {
  const experiment = modelingState.experiment || payload.default_experiment || {};
  const updateExperiment = (patch) => setModelingState({ experiment: mergeDeep(experiment, patch) });
  const selected = new Set(Array.isArray(experiment.features) ? experiment.features : []);
  const candidates = modelingFeatureCandidates(payload, experiment.target, {
    dropIdentifiers: experiment.preprocessing?.drop_identifiers !== false,
  });
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-model-feature-scope";

  const toolbar = document.createElement("div");
  toolbar.className = "stateframe-web-model-feature-toolbar";
  toolbar.appendChild(textSpan(selected.size ? `${formatInt(selected.size)} manual feature${selected.size === 1 ? "" : "s"}` : "Auto-select eligible features", "stateframe-web-visual-control-count"));
  const suggested = button("Suggested", () => updateExperiment({ features: suggestedModelingFeatures(payload, experiment.target) }));
  suggested.classList.add("is-tiny");
  const auto = button("Auto", () => updateExperiment({ features: [] }));
  auto.classList.add("is-tiny");
  toolbar.append(suggested, auto);
  wrap.appendChild(toolbar);

  const list = document.createElement("div");
  list.className = "stateframe-web-model-feature-list";
  for (const column of candidates.slice(0, 80)) {
    const value = modelingColumnValue(column);
    const item = document.createElement("label");
    item.className = "stateframe-web-model-feature-option";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = selected.has(value);
    input.addEventListener("change", () => {
      const next = new Set(selected);
      if (input.checked) next.add(value);
      else next.delete(value);
      updateExperiment({ features: [...next] });
    });
    const text = document.createElement("span");
    text.append(
      textSpan(modelingColumnLabel(column), "stateframe-web-visual-column-name"),
      textSpan(modelingColumnMeta(column), "stateframe-web-visual-column-meta"),
    );
    item.append(input, text);
    list.appendChild(item);
  }
  wrap.appendChild(list.children.length ? list : empty("Choose a target to inspect eligible features."));
  return wrap;
}

function renderModelingComparisonResult(suite) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-cleaning-detail";
  const comparison = suite.comparison || {};
  const title = document.createElement("div");
  title.className = "stateframe-web-cleaning-detail-title";
  title.textContent = `Model comparison: ${comparison.run_count || 0} run${comparison.run_count === 1 ? "" : "s"}`;
  panel.appendChild(title);
  panel.appendChild(section("Champion", keyValueList({
    Candidate: comparison.champion_label || "None",
    "Successful runs": formatInt(comparison.run_count || 0),
    "Failed runs": formatInt(comparison.error_count || 0),
  })));
  panel.appendChild(section("Comparison", renderModelingComparisonTable(comparison.rows || [])));
  const championRun = (suite.runs || []).find((run) => (run.search || {}).candidate_id === comparison.champion_id) || (suite.runs || [])[0];
  if (championRun) {
    panel.appendChild(section("Champion Details", renderModelingExperimentResult(championRun)));
  }
  if (Array.isArray(suite.errors) && suite.errors.length) {
    panel.appendChild(section("Failed Candidates", renderModelingComparisonErrors(suite.errors)));
  }
  return panel;
}

function renderModelingComparisonTable(rows) {
  const table = document.createElement("table");
  table.className = "stateframe-web-table";
  const thead = document.createElement("thead");
  const head = document.createElement("tr");
  ["rank", "candidate", "estimator", "primary", "r2", "mae", "rmse", "rating", "warnings"].forEach((key) => head.appendChild(th(key)));
  thead.appendChild(head);
  const tbody = document.createElement("tbody");
  for (const row of rows || []) {
    const metric = row.primary_metric || {};
    const metrics = row.metrics || {};
    const tr = document.createElement("tr");
    if (row.status === "error") tr.classList.add("is-error");
    tr.append(
      td(row.rank || ""),
      td(row.candidate_label || row.candidate_id || ""),
      td(row.estimator || ""),
      td(metric.key ? `${metric.key}: ${formatModelingMetricValue(metric.key, metric.value)}` : (row.error || "")),
      td(metrics.r2 === undefined ? "" : formatNumber(metrics.r2)),
      td(metrics.mae === undefined ? "" : formatNumber(metrics.mae)),
      td(metrics.rmse === undefined ? "" : formatNumber(metrics.rmse)),
      td(row.rating || row.status || ""),
      td(formatInt(row.warning_count || 0)),
    );
    tbody.appendChild(tr);
  }
  table.append(thead, tbody);
  return tbody.children.length ? table : empty("No model comparison rows available.");
}

function renderModelingComparisonErrors(errors) {
  const table = document.createElement("table");
  table.className = "stateframe-web-table";
  const thead = document.createElement("thead");
  const head = document.createElement("tr");
  ["candidate", "estimator", "error"].forEach((key) => head.appendChild(th(key)));
  thead.appendChild(head);
  const tbody = document.createElement("tbody");
  for (const error of errors || []) {
    const tr = document.createElement("tr");
    tr.append(td(error.candidate_label || error.candidate_id || ""), td(error.estimator || ""), td(error.error || ""));
    tbody.appendChild(tr);
  }
  table.append(thead, tbody);
  return table;
}

function renderModelingExperimentResult(result) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-cleaning-detail";
  const title = document.createElement("div");
  title.className = "stateframe-web-cleaning-detail-title";
  title.textContent = `Experiment: ${result.estimator || "model"} / ${result.task || ""}`;
  panel.appendChild(title);
  panel.appendChild(section("Training Setup", renderModelingTrainingSetup(result)));
  if (result.assessment && Object.keys(result.assessment).length) {
    panel.appendChild(section("Model Review", renderModelingAssessment(result.assessment)));
  }
  panel.appendChild(section("Metrics", renderModelingMetricTiles(result.metrics || {})));
  if (result.cross_validation?.enabled) {
    panel.appendChild(section("Cross-validation", renderModelingCrossValidation(result.cross_validation)));
  }
  if (result.task === "regression" && (Array.isArray(result.predictions) && result.predictions.length || result.holdout?.residual_summary)) {
    panel.appendChild(section("Prediction Check", renderModelingRegressionDiagnostics(result)));
  }
  if (result.holdout?.confusion_matrix) {
    panel.appendChild(section("Confusion Matrix", renderModelingConfusionMatrix(result.holdout.confusion_matrix, result.holdout.class_labels || [])));
  }
  if (result.holdout?.classification_report) {
    panel.appendChild(section("Precision / Recall Report", renderModelingClassificationReport(result.holdout.classification_report)));
  }
  if (result.holdout?.curves?.precision_recall?.length || result.holdout?.curves?.roc?.length) {
    panel.appendChild(section("Curves", renderModelingCurvePanel(result.holdout.curves || {})));
  }
  if (Array.isArray(result.holdout?.prediction_audit) && result.holdout.prediction_audit.length) {
    panel.appendChild(section("Prediction Records", renderModelingPredictionAudit(result.holdout.prediction_audit)));
  }
  const search = result.search || {};
  if (search.enabled) {
    panel.appendChild(section("Best Parameters", keyValueList(search.best_params || {})));
  }
  const explanation = result.explanation || {};
  panel.appendChild(section("Observability", keyValueList({
    Method: explanation.method || "",
    "Rows explained": explanation.sample_rows || "",
    Warnings: (result.warnings || []).join("; "),
  })));
  const features = explanation.top_features || result.feature_importance || [];
  if (features.length) {
    panel.appendChild(section("Top Features", renderModelingFeatureBars(features)));
  }
  if (Array.isArray(explanation.source_features) && explanation.source_features.length) {
    panel.appendChild(section("Top Source Columns", renderModelingSourceFeatureBars(explanation.source_features)));
  }
  if (Array.isArray(result.preprocessing?.feature_lineage) && result.preprocessing.feature_lineage.length) {
    panel.appendChild(section("Feature Lineage", renderModelingFeatureLineage(result.preprocessing.feature_lineage)));
  }
  if (Array.isArray(explanation.beeswarm) && explanation.beeswarm.length) {
    panel.appendChild(section("SHAP Beeswarm", renderModelingBeeswarmPlot(explanation.beeswarm)));
  }
  if (Array.isArray(explanation.records) && explanation.records.length) {
    panel.appendChild(section("Individual SHAP Records", renderModelingShapRecords(explanation.records)));
  }
  return panel;
}

function renderModelingTrainingSetup(result) {
  const preprocessing = result.preprocessing || {};
  const spec = result.spec || {};
  const sample = spec.sample || {};
  const split = spec.split || {};
  const manualFeatures = Array.isArray(spec.features) ? spec.features.length : 0;
  const values = {
    Target: result.target || "None",
    Task: result.task || "",
    Estimator: result.estimator || "",
    "Rows trained": formatInt(result.row_count || 0),
    "Transformed features": formatInt(result.feature_count || 0),
    "Numeric inputs": formatInt((preprocessing.numeric_columns || []).length),
    "Categorical inputs": formatInt((preprocessing.categorical_columns || []).length),
    "Date inputs": formatInt((preprocessing.datetime_columns || []).length),
    "Feature scope": manualFeatures ? `${formatInt(manualFeatures)} manual fields` : "Auto-selected eligible fields",
    "Row limit": sample.enabled && sample.max_rows ? `Sampled up to ${formatInt(sample.max_rows)}` : "All rows",
    "Test size": split.test_size ?? "",
  };
  return keyValueList(values);
}

function renderModelingAssessment(assessment) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-cleaning-control-stack";
  const metric = assessment.primary_metric || {};
  wrap.appendChild(keyValueList({
    Rating: assessment.rating || "",
    "Primary metric": metric.key ? `${metric.key}: ${formatModelingMetricValue(metric.key, metric.value)}` : "",
    Direction: metric.direction ? metric.direction.replaceAll("_", " ") : "",
    Summary: assessment.summary || "",
    Warnings: formatInt(assessment.warning_count || 0),
  }));
  if (Array.isArray(assessment.suggestions) && assessment.suggestions.length) {
    const list = document.createElement("div");
    list.className = "stateframe-web-cleaning-column-list";
    for (const item of assessment.suggestions.slice(0, 6)) {
      const row = document.createElement("div");
      row.className = "stateframe-web-cleaning-column";
      row.appendChild(textSpan(item, "stateframe-web-visual-column-name"));
      list.appendChild(row);
    }
    wrap.appendChild(list);
  }
  return wrap;
}

function renderModelingCrossValidation(crossValidation) {
  const scores = crossValidation.scores || {};
  const table = document.createElement("table");
  table.className = "stateframe-web-table";
  const thead = document.createElement("thead");
  const head = document.createElement("tr");
  ["metric", "mean", "std", "folds"].forEach((key) => head.appendChild(th(key)));
  thead.appendChild(head);
  const tbody = document.createElement("tbody");
  for (const [metric, row] of Object.entries(scores)) {
    const tr = document.createElement("tr");
    tr.append(
      td(metric),
      td(formatNumber(row?.mean)),
      td(formatNumber(row?.std)),
      td(Array.isArray(row?.folds) ? row.folds.map((value) => formatNumber(value)).join(", ") : ""),
    );
    tbody.appendChild(tr);
  }
  table.append(thead, tbody);
  return tbody.children.length ? table : empty("No cross-validation scores available.");
}

function renderModelingMetricTiles(metrics) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-model-report-grid";
  const keys = Object.keys(metrics || {}).filter((key) => typeof metrics[key] !== "object").slice(0, 12);
  if (!keys.length) return keyValueList(metrics || {});
  for (const key of keys) {
    const tile = document.createElement("div");
    tile.className = "stateframe-web-model-metric";
    tile.append(
      textSpan(formatModelingMetricValue(key, metrics[key]), "stateframe-web-model-metric-value"),
      textSpan(key.replaceAll("_", " "), "stateframe-web-model-metric-label"),
    );
    wrap.appendChild(tile);
  }
  return wrap;
}

function formatModelingMetricValue(key, value) {
  const label = String(key || "").toLowerCase();
  if (label.includes("rate") || label.includes("within") || label.includes("percentage")) {
    return formatPercent(value);
  }
  return formatNumber(value);
}

function renderModelingConfusionMatrix(matrix, labels) {
  const rows = Array.isArray(matrix) ? matrix : [];
  const maxValue = Math.max(1, ...rows.flat().map((value) => Number(value) || 0));
  const table = document.createElement("table");
  table.className = "stateframe-web-model-matrix";
  const thead = document.createElement("thead");
  const head = document.createElement("tr");
  head.appendChild(th("actual \\ predicted"));
  rows.forEach((_row, index) => head.appendChild(th(labels[index] ?? index)));
  thead.appendChild(head);
  const tbody = document.createElement("tbody");
  rows.forEach((row, rowIndex) => {
    const tr = document.createElement("tr");
    tr.appendChild(th(labels[rowIndex] ?? rowIndex));
    row.forEach((value) => {
      const cell = td(value);
      const intensity = Math.max(0.08, Math.min(1, Number(value || 0) / maxValue));
      cell.style.background = `rgba(37, 99, 235, ${0.08 + intensity * 0.48})`;
      cell.style.color = intensity > 0.55 ? "#ffffff" : "#0f172a";
      tr.appendChild(cell);
    });
    tbody.appendChild(tr);
  });
  table.append(thead, tbody);
  return table;
}

function renderModelingCurvePanel(curves) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-model-curves";
  if (curves.precision_recall?.length) {
    wrap.appendChild(renderModelingCurveChart(curves.precision_recall, {
      title: "Precision / Recall",
      xKey: "recall",
      yKey: "precision",
      xLabel: "recall",
      yLabel: "precision",
    }));
  }
  if (curves.roc?.length) {
    wrap.appendChild(renderModelingCurveChart(curves.roc, {
      title: "ROC",
      xKey: "fpr",
      yKey: "tpr",
      xLabel: "false positive rate",
      yLabel: "true positive rate",
      diagonal: true,
    }));
  }
  return wrap.children.length ? wrap : empty("No curve data available.");
}

function renderModelingRegressionDiagnostics(result) {
  const rows = result.predictions || [];
  const holdout = result.holdout || {};
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-model-diagnostics";
  const pairs = (rows || [])
    .map((row) => ({
      actual: Number(row.actual),
      prediction: Number(row.prediction),
      residual: Number(row.residual ?? (Number(row.prediction) - Number(row.actual))),
      index: row.index,
    }))
    .filter((row) => Number.isFinite(row.actual) && Number.isFinite(row.prediction));
  if (holdout.residual_summary && Object.keys(holdout.residual_summary).length) {
    wrap.appendChild(renderModelingResidualSummary(holdout.residual_summary));
  }
  if (Array.isArray(holdout.residual_bins) && holdout.residual_bins.length) {
    wrap.appendChild(renderModelingResidualHistogram(holdout.residual_bins));
  }
  if (pairs.length) {
    wrap.appendChild(renderModelingActualPredictionChart(pairs));
  }
  const table = document.createElement("table");
  table.className = "stateframe-web-table";
  const thead = document.createElement("thead");
  const head = document.createElement("tr");
  ["row", "actual", "prediction", "residual", "absolute error", "absolute % error"].forEach((key) => head.appendChild(th(key)));
  thead.appendChild(head);
  const tbody = document.createElement("tbody");
  const tableRows = Array.isArray(holdout.worst_predictions) && holdout.worst_predictions.length ? holdout.worst_predictions : pairs;
  tableRows.slice(0, 12).forEach((row) => {
    const tr = document.createElement("tr");
    tr.append(
      td(row.index),
      td(formatNumber(row.actual)),
      td(formatNumber(row.prediction)),
      td(formatNumber(row.residual)),
      td(formatNumber(row.absolute_error ?? Math.abs(Number(row.residual)))),
      td(row.absolute_percentage_error === undefined || row.absolute_percentage_error === null ? "" : formatPercent(row.absolute_percentage_error)),
    );
    tbody.appendChild(tr);
  });
  table.append(thead, tbody);
  if (tableRows.length) wrap.appendChild(table);
  return wrap.children.length ? wrap : empty("No numeric prediction diagnostics available.");
}

function renderModelingResidualSummary(summary) {
  return renderModelingMetricTiles({
    "median absolute error": summary.median_absolute_error,
    "p90 absolute error": summary.p90_absolute_error,
    "mean bias": summary.mean_residual,
    "over prediction rate": summary.over_prediction_rate,
    "within 10%": summary.within_10pct_rate,
    "within 20%": summary.within_20pct_rate,
  });
}

function renderModelingResidualHistogram(rows) {
  const card = document.createElement("div");
  card.className = "stateframe-web-model-curve";
  card.appendChild(textSpan("Residual distribution", "stateframe-web-model-chart-title"));
  const width = 320;
  const height = 180;
  const margin = { left: 34, right: 12, top: 14, bottom: 32 };
  const counts = rows.map((row) => Number(row.count || 0));
  const maxCount = Math.max(1, ...counts);
  const barGap = 3;
  const innerWidth = width - margin.left - margin.right;
  const barWidth = innerWidth / Math.max(1, rows.length);
  const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" });
  svg.appendChild(svgNode("line", { x1: margin.left, y1: height - margin.bottom, x2: width - margin.right, y2: height - margin.bottom, class: "stateframe-web-model-axis" }));
  rows.forEach((row, index) => {
    const count = Number(row.count || 0);
    const barHeight = (count / maxCount) * (height - margin.top - margin.bottom);
    const x = margin.left + index * barWidth + barGap / 2;
    const y = height - margin.bottom - barHeight;
    const rect = svgNode("rect", {
      x,
      y,
      width: Math.max(1, barWidth - barGap),
      height: Math.max(1, barHeight),
      class: "stateframe-web-model-hist-bar",
    });
    rect.appendChild(svgNode("title", {}, `${formatNumber(row.start)} to ${formatNumber(row.end)}: ${formatInt(count)}`));
    svg.appendChild(rect);
  });
  svg.appendChild(svgNode("text", { x: width / 2, y: height - 8, class: "stateframe-web-model-axis-label" }, "prediction - actual"));
  card.appendChild(svg);
  return card;
}

function renderModelingActualPredictionChart(rows) {
  const card = document.createElement("div");
  card.className = "stateframe-web-model-curve";
  card.appendChild(textSpan("Actual vs prediction", "stateframe-web-model-chart-title"));
  const width = 320;
  const height = 220;
  const margin = { left: 48, right: 14, top: 14, bottom: 38 };
  const values = rows.flatMap((row) => [row.actual, row.prediction]).filter(Number.isFinite);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const pad = Math.max(1, (maxValue - minValue) * 0.06);
  const domainMin = minValue - pad;
  const domainMax = maxValue + pad;
  const xScale = (value) => margin.left + ((value - domainMin) / Math.max(0.000001, domainMax - domainMin)) * (width - margin.left - margin.right);
  const yScale = (value) => height - margin.bottom - ((value - domainMin) / Math.max(0.000001, domainMax - domainMin)) * (height - margin.top - margin.bottom);
  const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" });
  svg.appendChild(svgNode("line", { x1: margin.left, y1: height - margin.bottom, x2: width - margin.right, y2: height - margin.bottom, class: "stateframe-web-model-axis" }));
  svg.appendChild(svgNode("line", { x1: margin.left, y1: margin.top, x2: margin.left, y2: height - margin.bottom, class: "stateframe-web-model-axis" }));
  svg.appendChild(svgNode("line", { x1: xScale(domainMin), y1: yScale(domainMin), x2: xScale(domainMax), y2: yScale(domainMax), class: "stateframe-web-model-diagonal" }));
  rows.slice(0, 60).forEach((row) => {
    const dot = svgNode("circle", {
      cx: xScale(row.actual),
      cy: yScale(row.prediction),
      r: 3.5,
      class: row.residual >= 0 ? "stateframe-web-model-scatter-dot is-positive" : "stateframe-web-model-scatter-dot is-negative",
    });
    dot.appendChild(svgNode("title", {}, `actual ${formatNumber(row.actual)} / prediction ${formatNumber(row.prediction)}`));
    svg.appendChild(dot);
  });
  svg.appendChild(svgNode("text", { x: width / 2, y: height - 8, class: "stateframe-web-model-axis-label" }, "actual"));
  svg.appendChild(svgNode("text", { x: 10, y: margin.top + 8, class: "stateframe-web-model-axis-label" }, "prediction"));
  card.appendChild(svg);
  return card;
}

function renderModelingCurveChart(rows, config) {
  const card = document.createElement("div");
  card.className = "stateframe-web-model-curve";
  card.appendChild(textSpan(config.title, "stateframe-web-model-chart-title"));
  const width = 320;
  const height = 190;
  const margin = { left: 42, right: 12, top: 12, bottom: 34 };
  const xValues = rows.map((row) => Number(row[config.xKey])).filter(Number.isFinite);
  const yValues = rows.map((row) => Number(row[config.yKey])).filter(Number.isFinite);
  const xMin = Math.min(0, ...xValues);
  const xMax = Math.max(1, ...xValues);
  const yMin = Math.min(0, ...yValues);
  const yMax = Math.max(1, ...yValues);
  const xScale = (value) => margin.left + ((value - xMin) / Math.max(0.000001, xMax - xMin)) * (width - margin.left - margin.right);
  const yScale = (value) => height - margin.bottom - ((value - yMin) / Math.max(0.000001, yMax - yMin)) * (height - margin.top - margin.bottom);
  const svg = svgNode("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" });
  svg.appendChild(svgNode("line", { x1: margin.left, y1: height - margin.bottom, x2: width - margin.right, y2: height - margin.bottom, class: "stateframe-web-model-axis" }));
  svg.appendChild(svgNode("line", { x1: margin.left, y1: margin.top, x2: margin.left, y2: height - margin.bottom, class: "stateframe-web-model-axis" }));
  if (config.diagonal) {
    svg.appendChild(svgNode("line", { x1: xScale(0), y1: yScale(0), x2: xScale(1), y2: yScale(1), class: "stateframe-web-model-diagonal" }));
  }
  const points = rows
    .map((row) => [Number(row[config.xKey]), Number(row[config.yKey])])
    .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y))
    .map(([x, y]) => `${xScale(x)},${yScale(y)}`)
    .join(" ");
  svg.appendChild(svgNode("polyline", { points, class: "stateframe-web-model-curve-line" }));
  svg.appendChild(svgNode("text", { x: width / 2, y: height - 8, class: "stateframe-web-model-axis-label" }, config.xLabel));
  svg.appendChild(svgNode("text", { x: 10, y: margin.top + 8, class: "stateframe-web-model-axis-label" }, config.yLabel));
  card.appendChild(svg);
  return card;
}

function renderModelingClassificationReport(report) {
  const table = document.createElement("table");
  table.className = "stateframe-web-table";
  const thead = document.createElement("thead");
  const head = document.createElement("tr");
  ["class", "precision", "recall", "f1-score", "support"].forEach((key) => head.appendChild(th(key)));
  thead.appendChild(head);
  const tbody = document.createElement("tbody");
  for (const [label, row] of Object.entries(report || {})) {
    if (!row || typeof row !== "object") continue;
    const tr = document.createElement("tr");
    tr.append(td(label), td(formatNumber(row.precision)), td(formatNumber(row.recall)), td(formatNumber(row["f1-score"])), td(formatNumber(row.support)));
    tbody.appendChild(tr);
  }
  table.append(thead, tbody);
  return table;
}

function renderModelingPredictionAudit(rows) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-model-records";
  for (const row of (rows || []).slice(0, 10)) {
    const details = document.createElement("details");
    details.className = "stateframe-web-model-record";
    const summary = document.createElement("summary");
    const status = row.correct === false ? "miss" : row.correct === true ? "match" : "check";
    summary.textContent = `Row ${row.index}: ${status} / actual ${cleaningPreviewText(row.actual)} / predicted ${cleaningPreviewText(row.prediction)}`;
    details.appendChild(summary);
    details.appendChild(keyValueList({
      Actual: cleaningPreviewText(row.actual),
      Prediction: cleaningPreviewText(row.prediction),
      Residual: row.residual === undefined ? "" : formatNumber(row.residual),
      "Absolute error": row.absolute_error === undefined ? "" : formatNumber(row.absolute_error),
    }));
    const record = row.record || {};
    if (Object.keys(record).length) {
      details.appendChild(keyValueList(Object.fromEntries(Object.entries(record).slice(0, 24))));
    }
    wrap.appendChild(details);
  }
  return wrap.children.length ? wrap : empty("No prediction audit records available.");
}

function renderModelingFeatureLineage(rows) {
  const grouped = {};
  for (const row of rows || []) {
    const source = row.source_column || row.feature || "";
    if (!source) continue;
    if (!grouped[source]) grouped[source] = { source, role: row.role || "", transforms: new Set(), count: 0 };
    grouped[source].transforms.add(row.transform || row.role || "feature");
    grouped[source].count += 1;
  }
  const table = document.createElement("table");
  table.className = "stateframe-web-table";
  const thead = document.createElement("thead");
  const head = document.createElement("tr");
  ["source column", "role", "transforms", "features"].forEach((key) => head.appendChild(th(key)));
  thead.appendChild(head);
  const tbody = document.createElement("tbody");
  Object.values(grouped).slice(0, 24).forEach((row) => {
    const tr = document.createElement("tr");
    tr.append(
      td(row.source),
      td(row.role),
      td([...row.transforms].join(", ")),
      td(formatInt(row.count)),
    );
    tbody.appendChild(tr);
  });
  table.append(thead, tbody);
  return tbody.children.length ? table : empty("No feature lineage available.");
}

function renderModelingBeeswarmSummary(rows) {
  const grouped = {};
  for (const row of rows) {
    if (!grouped[row.feature]) grouped[row.feature] = [];
    grouped[row.feature].push(Math.abs(Number(row.shap_value || 0)));
  }
  const summary = Object.entries(grouped)
    .map(([feature, values]) => ({ feature, value: values.reduce((a, b) => a + b, 0) / Math.max(1, values.length), count: values.length }))
    .sort((a, b) => b.value - a.value);
  return renderModelingFeatureRows(summary.map((row) => ({ feature: row.feature, mean_abs_shap: row.value, count: row.count })));
}

function renderModelingFeatureBars(rows) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-model-bars";
  const prepared = (rows || []).slice(0, 15).map((row) => ({
    feature: row.feature || "",
    value: Number(row.mean_abs_shap ?? row.permutation_importance ?? row.importance ?? row.cluster_separation ?? 0),
  }));
  const maxValue = Math.max(0.000001, ...prepared.map((row) => Math.abs(row.value)));
  for (const row of prepared) {
    const item = document.createElement("div");
    item.className = "stateframe-web-model-bar-row";
    const label = textSpan(row.feature, "stateframe-web-model-bar-label");
    const track = document.createElement("div");
    track.className = "stateframe-web-model-bar-track";
    const fill = document.createElement("div");
    fill.className = "stateframe-web-model-bar-fill";
    fill.style.width = `${Math.max(2, Math.abs(row.value) / maxValue * 100)}%`;
    track.appendChild(fill);
    const value = textSpan(formatNumber(row.value), "stateframe-web-model-bar-value");
    item.append(label, track, value);
    wrap.appendChild(item);
  }
  return wrap.children.length ? wrap : empty("No feature importance available.");
}

function renderModelingSourceFeatureBars(rows) {
  const normalized = (rows || []).map((row) => ({
    feature: row.source_column || row.feature || "",
    importance: row.importance ?? row.mean_abs_shap ?? row.permutation_importance ?? row.cluster_separation ?? 0,
  }));
  return renderModelingFeatureBars(normalized);
}

function renderModelingBeeswarmPlot(rows) {
  const grouped = {};
  for (const row of rows || []) {
    if (!grouped[row.feature]) grouped[row.feature] = [];
    grouped[row.feature].push(row);
  }
  const features = Object.entries(grouped)
    .map(([feature, values]) => ({
      feature,
      values,
      score: values.reduce((total, row) => total + Math.abs(Number(row.shap_value || 0)), 0) / Math.max(1, values.length),
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 12);
  const allValues = features.flatMap((item) => item.values.map((row) => Number(row.shap_value || 0))).filter(Number.isFinite);
  const minValue = Math.min(-0.000001, ...allValues);
  const maxValue = Math.max(0.000001, ...allValues);
  const zero = ((0 - minValue) / Math.max(0.000001, maxValue - minValue)) * 100;
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-model-beeswarm";
  for (const item of features) {
    const row = document.createElement("div");
    row.className = "stateframe-web-model-beeswarm-row";
    const label = textSpan(item.feature, "stateframe-web-model-beeswarm-label");
    const lane = document.createElement("div");
    lane.className = "stateframe-web-model-beeswarm-lane";
    const zeroLine = document.createElement("span");
    zeroLine.className = "stateframe-web-model-beeswarm-zero";
    zeroLine.style.left = `${zero}%`;
    lane.appendChild(zeroLine);
    item.values.slice(0, 80).forEach((point, index) => {
      const value = Number(point.shap_value || 0);
      const dot = document.createElement("span");
      dot.className = value >= 0 ? "stateframe-web-model-beeswarm-dot is-positive" : "stateframe-web-model-beeswarm-dot is-negative";
      dot.style.left = `${((value - minValue) / Math.max(0.000001, maxValue - minValue)) * 100}%`;
      dot.style.top = `${10 + (index % 5) * 5}px`;
      dot.title = `${item.feature}: ${formatNumber(value)} / value ${formatNumber(point.feature_value)}`;
      lane.appendChild(dot);
    });
    row.append(label, lane);
    wrap.appendChild(row);
  }
  return wrap.children.length ? wrap : empty("No SHAP beeswarm rows available.");
}

function renderModelingShapRecords(records) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-model-records";
  for (const record of records.slice(0, 20)) {
    const details = document.createElement("details");
    details.className = "stateframe-web-model-record";
    const summary = document.createElement("summary");
    summary.textContent = `Row ${record.index} / base ${formatNumber(record.base_value)} / sum ${formatNumber(record.shap_sum)}`;
    details.appendChild(summary);
    details.appendChild(renderModelingContributionBars(record.top_contributions || []));
    wrap.appendChild(details);
  }
  return wrap;
}

function renderModelingContributionBars(rows) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-model-contribs";
  const maxValue = Math.max(0.000001, ...rows.map((row) => Math.abs(Number(row.shap_value || 0))));
  for (const row of rows.slice(0, 12)) {
    const item = document.createElement("div");
    item.className = "stateframe-web-model-contrib-row";
    const label = textSpan(row.feature || "", "stateframe-web-model-bar-label");
    const track = document.createElement("div");
    track.className = "stateframe-web-model-contrib-track";
    const fill = document.createElement("div");
    fill.className = Number(row.shap_value || 0) >= 0 ? "stateframe-web-model-contrib-fill is-positive" : "stateframe-web-model-contrib-fill is-negative";
    fill.style.width = `${Math.max(2, Math.abs(Number(row.shap_value || 0)) / maxValue * 100)}%`;
    track.appendChild(fill);
    const value = textSpan(`${formatNumber(row.shap_value)} (${formatNumber(row.feature_value)})`, "stateframe-web-model-bar-value");
    item.append(label, track, value);
    wrap.appendChild(item);
  }
  return wrap.children.length ? wrap : empty("No row contributions available.");
}

function svgNode(name, attrs = {}, text = null) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) {
    node.setAttribute(key, String(value));
  }
  if (text !== null) node.textContent = text;
  return node;
}

function renderModelingFeatureRows(rows) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-cleaning-column-list";
  for (const row of rows.slice(0, 15)) {
    const item = document.createElement("div");
    item.className = "stateframe-web-cleaning-column";
    const value = row.mean_abs_shap ?? row.permutation_importance ?? row.importance ?? row.cluster_separation ?? "";
    item.append(
      textSpan(row.feature || "", "stateframe-web-visual-column-name"),
      textSpan(formatNumber(value), "stateframe-web-visual-column-meta"),
    );
    wrap.appendChild(item);
  }
  return wrap;
}

function renderPreviewObject(value) {
  if (!value || !Object.keys(value).length) return empty("No preview details.");
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-cleaning-preview";
  for (const [key, item] of Object.entries(value)) {
    const row = document.createElement("div");
    row.className = "stateframe-web-cleaning-preview-row";
    row.append(textSpan(key, "stateframe-web-cleaning-preview-key"), renderPreviewValue(item));
    wrap.appendChild(row);
  }
  return wrap;
}

function renderPreviewValue(value) {
  if (isPlainObjectArray(value)) return renderPreviewObjectTable(value);
  if (isPlainObject(value)) return renderPreviewKeyValues(value);
  return textSpan(cleaningPreviewText(value), "stateframe-web-cleaning-preview-value");
}

function renderPreviewKeyValues(value) {
  const list = document.createElement("div");
  list.className = "stateframe-web-cleaning-preview-value stateframe-web-cleaning-preview-mini";
  for (const [key, item] of Object.entries(value).slice(0, 8)) {
    const row = document.createElement("div");
    row.className = "stateframe-web-cleaning-preview-mini-row";
    row.append(
      textSpan(key, "stateframe-web-cleaning-preview-mini-key"),
      textSpan(cleaningPreviewText(item), "stateframe-web-cleaning-preview-mini-value"),
    );
    list.appendChild(row);
  }
  if (Object.keys(value).length > 8) {
    list.appendChild(textSpan(`${formatInt(Object.keys(value).length - 8)} more`, "stateframe-web-cleaning-preview-more"));
  }
  return list;
}

function renderPreviewObjectTable(rows) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-cleaning-preview-value";
  const table = document.createElement("table");
  table.className = "stateframe-web-preview-table";
  const columns = previewTableColumns(rows);
  const thead = document.createElement("thead");
  const head = document.createElement("tr");
  for (const column of columns) head.appendChild(th(column));
  thead.appendChild(head);
  const tbody = document.createElement("tbody");
  for (const row of rows.slice(0, 8)) {
    const tr = document.createElement("tr");
    for (const column of columns) tr.appendChild(td(row?.[column]));
    tbody.appendChild(tr);
  }
  table.append(thead, tbody);
  wrap.appendChild(table);
  if (rows.length > 8) {
    wrap.appendChild(textSpan(`${formatInt(rows.length - 8)} more`, "stateframe-web-cleaning-preview-more"));
  }
  return wrap;
}

function previewTableColumns(rows) {
  const preferred = ["value", "count", "ratio", "missing_ratio", "distinct_count", "min", "max"];
  const keys = Array.from(new Set((rows || []).flatMap((row) => Object.keys(row || {}))));
  const ordered = [
    ...preferred.filter((key) => keys.includes(key)),
    ...keys.filter((key) => !preferred.includes(key)),
  ];
  return ordered.slice(0, 4);
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isPlainObjectArray(value) {
  return Array.isArray(value) && value.length > 0 && value.every(isPlainObject);
}

function renderCleaningExamples(examples) {
  const table = document.createElement("table");
  table.className = "stateframe-web-table";
  const keys = Array.from(new Set(examples.flatMap((row) => Object.keys(row || {})))).slice(0, 5);
  const thead = document.createElement("thead");
  const head = document.createElement("tr");
  for (const key of keys) head.appendChild(th(key));
  thead.appendChild(head);
  const tbody = document.createElement("tbody");
  for (const row of examples.slice(0, 8)) {
    const tr = document.createElement("tr");
    for (const key of keys) tr.appendChild(td(row[key]));
    tbody.appendChild(tr);
  }
  table.append(thead, tbody);
  return table;
}

function renderCleaningControlSummary(controls, values) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-cleaning-control-summary";
  for (const control of controls) {
    const row = document.createElement("div");
    row.className = "stateframe-web-cleaning-preview-row";
    const value = Object.prototype.hasOwnProperty.call(values, control.id) ? values[control.id] : control.default;
    row.append(textSpan(control.label || control.id, "stateframe-web-cleaning-preview-key"), textSpan(cleaningPreviewText(value), "stateframe-web-cleaning-preview-value"));
    wrap.appendChild(row);
  }
  return wrap;
}

function renderActionControls(action, controls, values, planState, setPlanState, kind) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-cleaning-control-stack";
  for (const control of controls) {
    wrap.appendChild(renderActionControl(action, control, values, planState, setPlanState, kind));
  }
  return wrap;
}

function renderActionControl(action, control, values, planState, setPlanState, kind) {
  const label = document.createElement("label");
  label.className = "stateframe-web-visual-option";
  const title = document.createElement("span");
  title.textContent = control.label || control.id;
  const current = Object.prototype.hasOwnProperty.call(values, control.id) ? values[control.id] : control.default ?? "";
  const focusKey = `${kind}-action-${action.id}-${control.id}`;
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
    input.value = String(current ?? "");
    input.addEventListener("change", () => updateActionControl(action.id, control.id, input.value, planState, setPlanState));
  } else if (control.kind === "checkbox") {
    input = document.createElement("input");
    input.type = "checkbox";
    input.checked = Boolean(current);
    input.addEventListener("change", () => updateActionControl(action.id, control.id, input.checked, planState, setPlanState));
  } else if (control.kind === "textarea" || control.kind === "mapping") {
    input = document.createElement("textarea");
    input.className = "stateframe-web-textarea";
    input.value = control.kind === "mapping" && current && typeof current === "object"
      ? JSON.stringify(current, null, 2)
      : String(current ?? "");
    input.addEventListener("input", () => updateActionControl(action.id, control.id, input.value, planState, setPlanState));
  } else {
    input = document.createElement("input");
    input.className = "stateframe-web-input";
    input.type = control.kind === "number" ? "number" : "text";
    input.value = current ?? "";
    input.addEventListener("input", () => {
      const value = control.kind === "number" ? input.value : input.value;
      updateActionControl(action.id, control.id, value, planState, setPlanState);
    });
  }
  input.dataset.focusKey = focusKey;
  label.append(title, input);
  if (control.help) label.appendChild(textSpan(control.help, "stateframe-web-visual-help"));
  return label;
}

function effectiveActionControlValues(action, planState) {
  return {
    ...(action?.control_values || {}),
    ...((planState?.actionControlValues || {})[action?.id] || {}),
  };
}

function updateActionControl(actionId, controlId, value, planState, setPlanState) {
  const actionControlValues = { ...(planState.actionControlValues || {}) };
  actionControlValues[actionId] = {
    ...(actionControlValues[actionId] || {}),
    [controlId]: value,
  };
  const patch = { actionControlValues };
  if (Object.prototype.hasOwnProperty.call(planState || {}, "activePreset")) patch.activePreset = "custom";
  setPlanState(patch);
}

function renderCleaningColumnSummary(columns) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-cleaning-column-list";
  for (const column of columns.slice(0, 24)) {
    const item = document.createElement("div");
    item.className = "stateframe-web-cleaning-column";
    item.append(
      textSpan(column.display_name || column.source_name || column.name || "", "stateframe-web-visual-column-name"),
      textSpan(`${column.semantic_type || "unknown"} / ${column.dtype || ""}`, "stateframe-web-visual-column-meta"),
    );
    wrap.appendChild(item);
  }
  return wrap;
}

function selectSetting(label, value, choices, onChange, focusKey) {
  const wrap = document.createElement("label");
  wrap.className = "stateframe-web-visual-option";
  const title = document.createElement("span");
  title.textContent = label;
  const select = document.createElement("select");
  select.className = "stateframe-web-select";
  select.dataset.focusKey = focusKey;
  for (const [choiceValue, choiceLabel] of choices) {
    const option = document.createElement("option");
    option.value = choiceValue;
    option.textContent = choiceLabel;
    select.appendChild(option);
  }
  select.value = value;
  select.addEventListener("change", () => onChange(select.value));
  wrap.append(title, select);
  return wrap;
}

function numberSetting(label, value, onChange, focusKey, min = null, max = null, step = "1") {
  const wrap = document.createElement("label");
  wrap.className = "stateframe-web-visual-option";
  const title = document.createElement("span");
  title.textContent = label;
  const input = document.createElement("input");
  input.type = "number";
  input.className = "stateframe-web-input";
  input.dataset.focusKey = focusKey;
  input.value = value ?? "";
  if (min !== null) input.min = min;
  if (max !== null) input.max = max;
  input.step = step;
  input.addEventListener("input", () => onChange(input.value));
  wrap.append(title, input);
  return wrap;
}

function checkboxSetting(label, checked, onChange, focusKey) {
  const wrap = document.createElement("label");
  wrap.className = "stateframe-web-visual-option";
  const title = document.createElement("span");
  title.textContent = label;
  const input = document.createElement("input");
  input.type = "checkbox";
  input.dataset.focusKey = focusKey;
  input.checked = Boolean(checked);
  input.addEventListener("change", () => onChange(input.checked));
  wrap.append(title, input);
  return wrap;
}

function mergeDeep(base, patch) {
  const result = { ...(base || {}) };
  for (const [key, value] of Object.entries(patch || {})) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      result[key] = mergeDeep(result[key] || {}, value);
    } else {
      result[key] = value;
    }
  }
  return result;
}

function cleaningPreviewText(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.map((item) => typeof item === "object" ? compactJson(item) : String(item)).join("; ");
  if (typeof value === "object") return compactJson(value);
  if (typeof value === "number") return formatNumber(value);
  return String(value);
}

function groupBy(items, fn) {
  const groups = {};
  for (const item of items) {
    const key = String(fn(item));
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
  }
  return groups;
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
    visualState,
    note: visualState.note || "",
  }));
  const save = button("Save Leaf", () => sendCommand("save_visualizer_leaf", {
    visualSpec: buildVisualSpec(payload, visualState),
    visualState,
    note: visualState.note || "",
  }));
  render.disabled = commandIsLoading(commandStatus, "render_visualizer", "save_visualizer_leaf");
  save.disabled = commandIsLoading(commandStatus, "render_visualizer", "save_visualizer_leaf");
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
  body.appendChild(renderVisualCanvas(payload, visualizer.preview, visualState, setVisualizerState, sendCommand, commandStatus));
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
  panel.appendChild(renderVisualSuggestions(payload, visualState, setVisualizerState));
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
      item.addEventListener("click", () => {
        const fields = defaultFieldsForVisual(payload, definition);
        setVisualizerState({
          kind: definition.id,
          fields,
          fieldOptions: defaultFieldOptionsForVisual(payload, definition, fields),
          options: {},
          title: "",
        });
      });
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

function renderVisualSuggestions(payload, visualState, setVisualizerState) {
  const suggestions = Array.isArray(payload?.suggestions) ? payload.suggestions : [];
  const targetSuggestions = visualTargetSuggestions(payload, visualState);
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-suggestions";
  const title = document.createElement("div");
  title.className = "stateframe-web-visual-family-title";
  title.textContent = "Suggested";
  wrap.appendChild(title);
  if (!suggestions.length && !targetSuggestions.length) {
    const hint = document.createElement("div");
    hint.className = "stateframe-web-visual-type-description";
    hint.textContent = "No automatic suggestions for this state yet.";
    wrap.appendChild(hint);
    return wrap;
  }
  if (targetSuggestions.length) {
    const targetTitle = document.createElement("div");
    targetTitle.className = "stateframe-web-visual-family-title";
    targetTitle.textContent = "Against targets";
    wrap.appendChild(targetTitle);
    for (const suggestion of targetSuggestions.slice(0, 6)) {
      wrap.appendChild(renderVisualSuggestionItem(payload, visualState, setVisualizerState, suggestion, "is-target-aware"));
    }
    if (suggestions.length) {
      const autoTitle = document.createElement("div");
      autoTitle.className = "stateframe-web-visual-family-title";
      autoTitle.textContent = "Automatic";
      wrap.appendChild(autoTitle);
    }
  }
  for (const suggestion of suggestions.slice(0, 8)) {
    wrap.appendChild(renderVisualSuggestionItem(payload, visualState, setVisualizerState, suggestion));
  }
  return wrap;
}

function renderVisualSuggestionItem(payload, visualState, setVisualizerState, suggestion, extraClass = "") {
  const spec = suggestion.spec || {};
  const item = document.createElement("button");
  item.type = "button";
  item.className = "stateframe-web-visual-suggestion";
  if (extraClass) item.classList.add(extraClass);
  if (spec.kind === visualState.kind && (spec.title || suggestion.title || "") === visualState.title) item.classList.add("is-selected");
  item.addEventListener("click", () => applyVisualSuggestion(payload, visualState, setVisualizerState, suggestion));
  const itemTitle = document.createElement("div");
  itemTitle.className = "stateframe-web-visual-type-title";
  itemTitle.textContent = suggestion.title || spec.title || spec.kind || "Suggested visual";
  const meta = document.createElement("div");
  meta.className = "stateframe-web-visual-type-description";
  meta.textContent = [spec.kind, suggestion.reason].filter(Boolean).join(" / ");
  item.append(itemTitle, meta);
  return item;
}

function applyVisualSuggestion(payload, visualState, setVisualizerState, suggestion) {
  const spec = suggestion.spec || {};
  const kind = spec.kind || visualState.kind;
  const definition = visualDefinition(payload, kind);
  const fields = spec.fields || {};
  setVisualizerState({
    kind,
    fields,
    fieldOptions: spec.field_options || spec.fieldOptions || defaultFieldOptionsForVisual(payload, definition, fields),
    filters: Array.isArray(spec.filters) ? spec.filters : [],
    options: spec.options || {},
    title: spec.title || suggestion.title || "",
  });
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

function renderVisualCanvas(payload, preview, visualState, setVisualizerState, sendCommand, commandStatus) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-visual-canvas";
  panel.dataset.scrollKey = "visual-canvas";
  const definition = visualDefinition(payload, visualState.kind);
  const healthChecks = visualHealthChecks(payload, definition, visualState, setVisualizerState);
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
    visualState: { ...visualState, title: title.value },
    note: visualState.note || "",
  }));
  const save = button("Save Leaf", () => sendCommand("save_visualizer_leaf", {
    visualSpec: buildVisualSpec(payload, { ...visualState, title: title.value }),
    visualState: { ...visualState, title: title.value },
    note: visualState.note || "",
  }));
  const hasBlockingHealthIssue = healthChecks.some((item) => item.severity === "blocker");
  render.disabled = hasBlockingHealthIssue || commandIsLoading(commandStatus, "render_visualizer", "save_visualizer_leaf");
  save.disabled = hasBlockingHealthIssue || commandIsLoading(commandStatus, "render_visualizer", "save_visualizer_leaf");
  controls.append(title, render, save);
  panel.appendChild(controls);
  panel.appendChild(section("Plot Recipe", renderVisualRecipe(payload, visualState)));
  if (healthChecks.length) panel.appendChild(section("Visual Health", renderVisualHealthPanel(healthChecks)));
  panel.appendChild(renderVisualPreview(preview, commandStatus));
  const note = document.createElement("textarea");
  note.className = "stateframe-web-textarea stateframe-web-visual-note";
  note.placeholder = "Leaf note. Markdown is supported after save.";
  note.dataset.focusKey = "visual-note";
  note.value = visualState.note || "";
  note.addEventListener("input", () => setVisualizerState({ note: note.value }));
  panel.appendChild(section("Leaf Notes", note));
  return panel;
}

function visualHealthChecks(payload, definition, visualState, setVisualizerState) {
  const checks = [];
  const fields = visualState.fields || {};
  const options = visualState.options || {};
  const columns = payload.columns || [];
  const rowCount = Number(payload.view?.row_count || 0);
  const sampleRows = Number(options.sample_rows || 0);
  for (const field of definition.fields || []) {
    if (!field.required) continue;
    const value = fields[field.slot];
    const missing = field.multiple ? !Array.isArray(value) || !value.length : !value;
    if (!missing) continue;
    checks.push({
      severity: "blocker",
      title: `Missing ${field.label}`,
      detail: `${field.label} is required for ${definition.title || definition.id}.`,
    });
  }
  if (rowCount > 50000 && !sampleRows) {
    checks.push({
      severity: "warning",
      title: "Large render",
      detail: `${formatInt(rowCount)} source rows may render slowly.`,
      actions: [
        visualOptionsAction("Sample 10k", visualState, setVisualizerState, {
          sample_rows: 10000,
          sample_method: "random",
          sample_seed: 42,
        }),
        visualOptionsAction("Sample 25k", visualState, setVisualizerState, {
          sample_rows: 25000,
          sample_method: "random",
          sample_seed: 42,
        }),
      ],
    });
  } else if (sampleRows > 0) {
    checks.push({
      severity: "info",
      title: "Sampling active",
      detail: `${formatInt(sampleRows)} ${options.sample_method || "random"} rows.`,
      actions: [visualClearOptionsAction("Full rows", visualState, setVisualizerState, ["sample_rows", "sample_method", "sample_seed"])],
    });
  }
  checks.push(...visualChannelHealthChecks(payload, "color", "Color", fields.color, options, visualState, setVisualizerState));
  checks.push(...visualChannelHealthChecks(payload, "facet", "Facet", fields.facet || fields.facet_row, options, visualState, setVisualizerState));
  const xColumn = columns.find((column) => column.id === fields.x);
  const xDistinct = visualColumnDistinctCount(xColumn);
  if (fields.x && visualColumnLooksCategorical(xColumn) && Number.isFinite(xDistinct) && xDistinct > 60 && Number(options.top_n || 0) <= 0) {
    checks.push({
      severity: "warning",
      title: "Long X axis",
      detail: `${formatInt(xDistinct)} X values can crowd labels.`,
      actions: [
        visualOptionsAction("Top 20 + Other", visualState, setVisualizerState, {
          top_n: 20,
          top_n_mode: "other",
          top_n_direction: "top",
          other_label: "Other",
        }),
        visualOptionsAction("Sort by value", visualState, setVisualizerState, { sort_by: "y_descending" }),
      ],
    });
  }
  if (["scatter", "strip"].includes(definition.id) && rowCount > 20000 && !sampleRows) {
    checks.push({
      severity: "warning",
      title: "Dense marks",
      detail: `${definition.title || definition.id} draws one mark per row.`,
      actions: [
        visualOptionsAction("Sample 10k", visualState, setVisualizerState, {
          sample_rows: 10000,
          sample_method: "random",
          sample_seed: 42,
        }),
        visualOptionsAction("Lower opacity", visualState, setVisualizerState, { opacity: 0.45, marker_opacity: 0.45 }),
      ],
    });
  }
  return checks;
}

function visualChannelHealthChecks(payload, prefix, label, columnId, options, visualState, setVisualizerState) {
  if (!columnId) return [];
  const column = (payload.columns || []).find((item) => item.id === columnId);
  const distinct = visualColumnDistinctCount(column);
  if (!Number.isFinite(distinct)) return [];
  const currentTop = Number(options[`${prefix}_top_n`] || 0);
  if (currentTop > 0) {
    return [{
      severity: "info",
      title: `${label} rollup active`,
      detail: `${label} is limited to ${formatInt(currentTop)} values.`,
      actions: [visualClearOptionsAction(`Clear ${label}`, visualState, setVisualizerState, [
        `${prefix}_top_n`,
        `${prefix}_top_n_mode`,
        `${prefix}_top_n_direction`,
        `${prefix}_other_label`,
      ])],
    }];
  }
  if (distinct <= (prefix === "facet" ? 12 : 24)) return [];
  return [{
    severity: "warning",
    title: `High-cardinality ${label}`,
    detail: `${formatInt(distinct)} distinct values can clutter the visual.`,
    actions: [
      visualOptionsAction("Top 12 + Other", visualState, setVisualizerState, {
        [`${prefix}_top_n`]: 12,
        [`${prefix}_top_n_mode`]: "other",
        [`${prefix}_top_n_direction`]: "top",
        [`${prefix}_other_label`]: "Other",
      }),
      visualOptionsAction("Top 24", visualState, setVisualizerState, {
        [`${prefix}_top_n`]: 24,
        [`${prefix}_top_n_mode`]: "filter",
        [`${prefix}_top_n_direction`]: "top",
      }),
      ...(prefix === "color" ? [visualOptionsAction("Hide Legend", visualState, setVisualizerState, { show_legend: false })] : []),
    ],
  }];
}

function visualOptionsAction(label, visualState, setVisualizerState, patch) {
  return {
    label,
    onClick: () => setVisualizerState({ options: { ...(visualState.options || {}), ...patch } }),
  };
}

function visualClearOptionsAction(label, visualState, setVisualizerState, keys) {
  return {
    label,
    onClick: () => {
      const options = { ...(visualState.options || {}) };
      for (const key of keys) delete options[key];
      setVisualizerState({ options });
    },
  };
}

function renderVisualHealthPanel(checks) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-health";
  for (const check of checks) {
    const item = document.createElement("div");
    item.className = `stateframe-web-visual-health-item is-${check.severity || "info"}`;
    const main = document.createElement("div");
    main.className = "stateframe-web-visual-health-main";
    main.append(
      textSpan(check.title, "stateframe-web-visual-health-title"),
      textSpan(check.detail || "", "stateframe-web-visual-health-detail"),
    );
    item.appendChild(main);
    if (check.actions?.length) {
      const actions = document.createElement("div");
      actions.className = "stateframe-web-action-row";
      for (const action of check.actions) {
        actions.appendChild(tinyButton(action.label, action.onClick));
      }
      item.appendChild(actions);
    }
    wrap.appendChild(item);
  }
  return wrap;
}

function renderVisualRecipe(payload, visualState) {
  const definition = visualDefinition(payload, visualState.kind);
  const fields = visualState.fields || {};
  const fieldOptions = visualState.fieldOptions || {};
  const rows = {};
  rows.Type = definition.title || visualState.kind || "";
  if (Array.isArray(fields.dimensions) && fields.dimensions.length) {
    rows.Columns = visualFieldLabel(payload, fields.dimensions);
  }
  const groupParts = [];
  for (const slot of ["x", "names", "locations", "path", "color", "facet", "facet_row", "theta"]) {
    const value = fields[slot];
    if (!value) continue;
    groupParts.push(`${slot}: ${visualFieldLabel(payload, value)}`);
  }
  rows.Grouping = groupParts.join(" / ") || "None";
  const measureSlots = ["y", "y2", "values", "r", "z", "size"].filter((slot) => fields[slot]);
  if (measureSlots.length) {
    rows.Measure = measureSlots.map((slot) => {
      const stat = fieldOptions[slot]?.stat || defaultFieldOptionForSlot(payload, definition, slot, fields[slot]).stat || "raw";
      const prefix = slot === "y2" ? "Y2: " : "";
      return `${prefix}${visualStatLabel(stat)} ${visualFieldLabel(payload, fields[slot])}`;
    }).join(" / ");
  } else if (Array.isArray(fields.dimensions) && fields.dimensions.length) {
    rows.Measure = "Not used";
  } else {
    rows.Measure = "Record count";
  }
  const bucketSlot = ["x", "date"].find((slot) => fieldOptions[slot]?.bucket && fieldOptions[slot].bucket !== "none");
  rows.Bucket = bucketSlot ? `${bucketSlot}: ${fieldOptions[bucketSlot].bucket}` : "";
  if (Number(visualState.options?.sample_rows || 0) > 0) {
    rows.Sample = `${formatInt(visualState.options.sample_rows)} ${visualState.options.sample_method || "random"}`;
  }
  rows.Rows = formatInt(payload.view?.row_count || 0);
  return keyValueList(rows);
}

function visualFieldLabel(payload, value) {
  if (Array.isArray(value)) return value.map((item) => visualFieldLabel(payload, item)).join(", ");
  const column = (payload.columns || []).find((item) => item.id === value || item.source_name === value || item.display_name === value);
  return column?.display_name || column?.source_name || value || "";
}

function visualStatLabel(value) {
  return {
    none: "Raw",
    raw: "Raw",
    count: "Count of",
    sum: "Sum of",
    mean: "Mean of",
    median: "Median of",
    min: "Min of",
    max: "Max of",
    nunique: "Distinct count of",
    p25: "P25 of",
    p75: "P75 of",
    p90: "P90 of",
    p95: "P95 of",
  }[value] || String(value || "").replace(/_/g, " ");
}

function renderVisualPreview(preview, commandStatus = {}) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-preview";
  if (commandIsLoading(commandStatus, "render_visualizer")) {
    wrap.classList.add("is-loading");
    wrap.appendChild(empty(commandStatus.message || "Rendering visual..."));
    return wrap;
  }
  if (commandIsLoading(commandStatus, "save_visualizer_leaf")) {
    wrap.classList.add("is-loading");
    if (preview) {
      const badge = document.createElement("div");
      badge.className = "stateframe-web-visual-preview-header";
      badge.textContent = commandStatus.message || "Saving visual leaf...";
      wrap.appendChild(badge);
    } else {
      wrap.appendChild(empty(commandStatus.message || "Saving visual leaf..."));
      return wrap;
    }
  }
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
  panel.appendChild(section("Options", renderVisualOptions(payload, definition, visualState, setVisualizerState, ui, setUi)));
  return panel;
}

function renderVisualFields(payload, definition, visualState, setVisualizerState) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-fields";
  for (const field of definition.fields || []) {
    const current = visualState.fields?.[field.slot];
    const hasCurrent = field.multiple ? Array.isArray(current) && current.length : Boolean(current);
    const row = document.createElement(field.multiple ? "div" : "label");
    row.className = "stateframe-web-visual-field";
    if (hasCurrent) row.classList.add("is-filled");
    if (field.required) row.classList.add("is-required");
    wireVisualFieldDropZone(row, payload, definition, field, visualState, setVisualizerState);
    const label = document.createElement("span");
    label.textContent = `${field.label}${field.required ? " *" : ""}`;
    if (field.multiple) {
      row.append(label, renderVisualMultiField(payload, definition, field, visualState, setVisualizerState));
      wrap.appendChild(row);
      continue;
    }
    const select = document.createElement("select");
    select.className = "stateframe-web-select";
    select.dataset.focusKey = `visual-field-${field.slot}`;
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = field.multiple ? "Comma-select below or choose first" : "None";
    select.appendChild(blank);
    const singleCandidates = visualCandidateColumnsForField(payload, definition, field, visualState);
    for (const column of singleCandidates) {
      const option = document.createElement("option");
      option.value = column.id;
      option.textContent = column.display_name || column.source_name || column.id;
      select.appendChild(option);
    }
    select.value = current || "";
    select.addEventListener("change", () => {
      if (select.value) {
        assignVisualColumnToField(payload, definition, field, select.value, visualState, setVisualizerState);
        return;
      }
      const next = { ...(visualState.fields || {}) };
      const nextFieldOptions = { ...(visualState.fieldOptions || {}) };
      delete next[field.slot];
      delete nextFieldOptions[field.slot];
      setVisualizerState({ fields: next, fieldOptions: nextFieldOptions });
    });
    row.append(label, select);
    if (!field.multiple && current) {
      const behavior = renderVisualFieldBehavior(payload, definition, field, visualState, setVisualizerState);
      if (behavior) row.appendChild(behavior);
    }
    wrap.appendChild(row);
  }
  return wrap.children.length ? wrap : empty("This visual does not require field bindings.");
}

function visualCandidateColumnsForField(payload, definition, field, visualState) {
  const targetId = definition.id === "target_association" && field.slot === "features" ? visualState.fields?.target : null;
  return visualCandidateColumns(payload, definition, field).filter((column) => {
    if (targetId && column.id === targetId) return false;
    if (definition.id === "target_profile" && field.slot === "feature") return column.id !== visualState.fields?.target;
    if (definition.id === "target_profile" && field.slot === "color") return column.id !== visualState.fields?.target && column.id !== visualState.fields?.feature;
    return true;
  });
}

function visualFieldAcceptsColumn(payload, definition, field, columnId, visualState) {
  if (!columnId) return false;
  return visualCandidateColumnsForField(payload, definition, field, visualState).some((column) => column.id === columnId);
}

function assignVisualColumnToField(payload, definition, field, columnId, visualState, setVisualizerState) {
  const value = String(columnId || "");
  if (!visualFieldAcceptsColumn(payload, definition, field, value, visualState)) return false;
  const next = { ...(visualState.fields || {}) };
  if (field.multiple) {
    const current = Array.isArray(next[field.slot]) ? next[field.slot] : [];
    if (!current.includes(value)) next[field.slot] = [...current, value];
    else next[field.slot] = current;
    setVisualizerState({ fields: next });
    return true;
  }
  const nextFieldOptions = { ...(visualState.fieldOptions || {}) };
  next[field.slot] = value;
  if (definition.id === "target_association" && field.slot === "target" && Array.isArray(next.features)) {
    next.features = next.features.filter((item) => item !== value);
  }
  if (definition.id === "target_profile" && field.slot === "target") {
    if (next.feature === value) delete next.feature;
    if (next.color === value) delete next.color;
  }
  if (definition.id === "target_profile" && field.slot === "feature" && next.color === value) {
    delete next.color;
  }
  const defaults = defaultFieldOptionForSlot(payload, definition, field.slot, value);
  if (Object.keys(defaults).length) nextFieldOptions[field.slot] = { ...defaults, ...(nextFieldOptions[field.slot] || {}) };
  else delete nextFieldOptions[field.slot];
  setVisualizerState({ fields: next, fieldOptions: nextFieldOptions });
  return true;
}

function wireVisualFieldDropZone(row, payload, definition, field, visualState, setVisualizerState) {
  row.classList.add("stateframe-web-visual-field-dropzone");
  row.dataset.visualSlot = field.slot;
  row.title = `Drop a column onto ${field.label}`;
  row.addEventListener("dragenter", (event) => {
    event.preventDefault();
    row.classList.add("is-drop-target");
  });
  row.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
    row.classList.add("is-drop-target");
  });
  row.addEventListener("dragleave", (event) => {
    if (!event.relatedTarget || !row.contains(event.relatedTarget)) row.classList.remove("is-drop-target");
  });
  row.addEventListener("drop", (event) => {
    event.preventDefault();
    row.classList.remove("is-drop-target");
    const columnId = event.dataTransfer?.getData("application/x-stateframe-column-id") || event.dataTransfer?.getData("text/plain") || "";
    if (!assignVisualColumnToField(payload, definition, field, columnId, visualState, setVisualizerState)) {
      row.classList.add("is-drop-rejected");
      window.setTimeout(() => row.classList.remove("is-drop-rejected"), 450);
      return;
    }
    row.classList.add("is-drop-applied");
    window.setTimeout(() => row.classList.remove("is-drop-applied"), 450);
  });
}

let activeVisualPointerDropZone = null;

function visualDropZoneFromPoint(x, y) {
  const element = document.elementFromPoint(x, y);
  return element?.closest?.(".stateframe-web-visual-field-dropzone") || null;
}

function setActiveVisualPointerDropZone(zone) {
  if (activeVisualPointerDropZone === zone) return;
  if (activeVisualPointerDropZone) activeVisualPointerDropZone.classList.remove("is-drop-target");
  activeVisualPointerDropZone = zone;
  if (activeVisualPointerDropZone) activeVisualPointerDropZone.classList.add("is-drop-target");
}

function pulseVisualDropZone(zone, className) {
  if (!zone) return;
  zone.classList.add(className);
  window.setTimeout(() => zone.classList.remove(className), 450);
}

function applyVisualColumnDrop(payload, definition, columnId, zone, visualState, setVisualizerState) {
  const slot = zone?.dataset?.visualSlot;
  const field = (definition.fields || []).find((item) => item.slot === slot);
  if (!field || !assignVisualColumnToField(payload, definition, field, columnId, visualState, setVisualizerState)) {
    pulseVisualDropZone(zone, "is-drop-rejected");
    return false;
  }
  pulseVisualDropZone(zone, "is-drop-applied");
  return true;
}

function wireVisualColumnPointerDrag(item, column, payload, definition, visualState, setVisualizerState) {
  item.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    if (event.target?.closest?.("button,input,select,textarea,a")) return;
    let start = { x: event.clientX, y: event.clientY, dragging: false };
    const handleMove = (moveEvent) => {
      if (!start) return;
      const distance = Math.hypot(moveEvent.clientX - start.x, moveEvent.clientY - start.y);
      if (!start.dragging && distance < 6) return;
      if (!start.dragging) {
        start.dragging = true;
        item.classList.add("is-dragging");
      }
      moveEvent.preventDefault();
      setActiveVisualPointerDropZone(visualDropZoneFromPoint(moveEvent.clientX, moveEvent.clientY));
    };
    const finish = (upEvent) => {
      document.removeEventListener("pointermove", handleMove);
      document.removeEventListener("pointercancel", cancel);
      const zone = start?.dragging ? visualDropZoneFromPoint(upEvent.clientX, upEvent.clientY) || activeVisualPointerDropZone : null;
      if (start?.dragging) {
        upEvent.preventDefault();
        applyVisualColumnDrop(payload, definition, column.id, zone, visualState, setVisualizerState);
      }
      item.classList.remove("is-dragging");
      setActiveVisualPointerDropZone(null);
      start = null;
      if (item.releasePointerCapture && upEvent.pointerId !== undefined) {
        try {
          item.releasePointerCapture(upEvent.pointerId);
        } catch (_error) {
          // Pointer capture can already be released when native drag starts.
        }
      }
    };
    const cancel = () => {
      document.removeEventListener("pointermove", handleMove);
      document.removeEventListener("pointerup", finish);
      item.classList.remove("is-dragging");
      setActiveVisualPointerDropZone(null);
      start = null;
    };
    document.addEventListener("pointermove", handleMove);
    document.addEventListener("pointerup", finish, { once: true });
    document.addEventListener("pointercancel", cancel, { once: true });
    if (item.setPointerCapture && event.pointerId !== undefined) {
      try {
        item.setPointerCapture(event.pointerId);
      } catch (_error) {
        // Some embedded notebook surfaces do not allow capture from output DOM.
      }
    }
  });
}

function renderVisualMultiField(payload, definition, field, visualState, setVisualizerState) {
  const targetId = definition.id === "target_association" && field.slot === "features" ? visualState.fields?.target : null;
  const current = (Array.isArray(visualState.fields?.[field.slot]) ? visualState.fields[field.slot] : []).filter((value) => value !== targetId);
  const currentSet = new Set(current);
  const candidates = visualCandidateColumnsForField(payload, definition, field, visualState);
  const panel = document.createElement("div");
  panel.className = "stateframe-web-visual-multi";
  const toolbar = document.createElement("div");
  toolbar.className = "stateframe-web-visual-multi-toolbar";
  const suggested = tinyButton("Suggested", () => {
    const values = defaultMultipleColumnsForVisual(payload, definition, field).filter((value) => value !== targetId);
    setVisualizerState({ fields: { ...(visualState.fields || {}), [field.slot]: values } });
  }, false, `Use suggested ${field.label.toLowerCase()}`);
  const clear = tinyButton("Clear", () => {
    setVisualizerState({ fields: { ...(visualState.fields || {}), [field.slot]: [] } });
  }, false, `Clear ${field.label.toLowerCase()}`);
  toolbar.append(suggested, clear, textSpan(`${formatInt(current.length)} selected`, "stateframe-web-visual-multi-count"));
  panel.appendChild(toolbar);
  const chips = document.createElement("div");
  chips.className = "stateframe-web-visual-multi-chips";
  if (current.length) {
    for (const value of current) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "stateframe-web-visual-multi-chip";
      chip.textContent = visualFieldLabel(payload, value);
      chip.title = "Remove";
      chip.addEventListener("click", () => {
        const nextValues = current.filter((item) => item !== value);
        setVisualizerState({ fields: { ...(visualState.fields || {}), [field.slot]: nextValues } });
      });
      chips.appendChild(chip);
    }
  } else {
    chips.appendChild(textSpan("None selected", "stateframe-web-visual-help"));
  }
  panel.appendChild(chips);
  const list = document.createElement("div");
  list.className = "stateframe-web-visual-multi-list";
  for (const column of candidates) {
    const option = document.createElement("label");
    option.className = "stateframe-web-visual-multi-option";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = currentSet.has(column.id);
    checkbox.addEventListener("change", () => {
      const nextSet = new Set(current);
      if (checkbox.checked) nextSet.add(column.id);
      else nextSet.delete(column.id);
      setVisualizerState({ fields: { ...(visualState.fields || {}), [field.slot]: Array.from(nextSet) } });
    });
    const main = document.createElement("span");
    main.className = "stateframe-web-visual-multi-option-main";
    main.append(
      textSpan(column.display_name || column.source_name || column.id, "stateframe-web-visual-multi-option-title"),
      textSpan(`${column.semantic_type || "unknown"} / ${column.dtype || ""}`, "stateframe-web-visual-multi-option-meta"),
    );
    option.append(checkbox, main);
    list.appendChild(option);
  }
  panel.appendChild(list.children.length ? list : empty("No matching columns."));
  return panel;
}

function renderVisualFieldBehavior(payload, definition, field, visualState, setVisualizerState) {
  const columnId = visualState.fields?.[field.slot];
  if (!columnId) return null;
  const current = {
    ...defaultFieldOptionForSlot(payload, definition, field.slot, columnId),
    ...((visualState.fieldOptions || {})[field.slot] || {}),
  };
  const controls = [];
  controls.push(renderVisualFieldQuickActions(field, visualState, setVisualizerState));
  if (visualSlotSupportsStat(definition.id, field.slot)) {
    controls.push(visualFieldSelect("Summary", current.stat || "mean", visualStatChoices(definition.id, field.slot), (value) => {
      updateVisualFieldOption(field.slot, { stat: value }, visualState, setVisualizerState);
    }, `visual-field-${field.slot}-stat`));
  }
  const column = (payload.columns || []).find((item) => item.id === columnId);
  if (["x", "date"].includes(field.slot) && visualColumnLooksDate(column) && ["line", "area", "bar"].includes(definition.id)) {
    controls.push(visualFieldSelect("Bucket", current.bucket || "none", [
      ["none", "None"],
      ["day", "Day"],
      ["week", "Week"],
      ["month", "Month"],
      ["quarter", "Quarter"],
      ["year", "Year"],
    ], (value) => updateVisualFieldOption(field.slot, { bucket: value }, visualState, setVisualizerState), `visual-field-${field.slot}-bucket`));
  }
  const guardrail = renderVisualChannelGuardrail(payload, field, column, visualState, setVisualizerState);
  if (guardrail) controls.push(guardrail);
  if (!controls.length) return null;
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-field-behavior";
  wrap.append(...controls);
  return wrap;
}

function renderVisualFieldQuickActions(field, visualState, setVisualizerState) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-field-actions";
  const clear = tinyButton("Clear", () => {
    const fields = { ...(visualState.fields || {}) };
    const fieldOptions = { ...(visualState.fieldOptions || {}) };
    delete fields[field.slot];
    delete fieldOptions[field.slot];
    setVisualizerState({ fields, fieldOptions });
  }, false, `Clear ${field.label}`);
  wrap.appendChild(clear);
  return wrap;
}

function renderVisualChannelGuardrail(payload, field, column, visualState, setVisualizerState) {
  const prefix = field.slot === "color" ? "color" : ["facet", "facet_row"].includes(field.slot) ? "facet" : "";
  if (!prefix || !column) return null;
  const distinct = visualColumnDistinctCount(column);
  const currentTop = Number((visualState.options || {})[`${prefix}_top_n`] || 0);
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-channel-guardrail";
  if (distinct >= 16) wrap.classList.add("is-warning");
  const meta = document.createElement("div");
  meta.className = "stateframe-web-visual-channel-meta";
  meta.textContent = Number.isFinite(distinct) ? `${formatInt(distinct)} distinct values` : "Distinct value count unavailable";
  const actions = document.createElement("div");
  actions.className = "stateframe-web-action-row";
  const sourceRows = Number(payload?.view?.row_count || 0);
  const currentSample = Number((visualState.options || {}).sample_rows || 0);
  const roll12 = tinyButton("Top 12 + Other", () => {
    setVisualizerState({
      options: {
        ...(visualState.options || {}),
        [`${prefix}_top_n`]: 12,
        [`${prefix}_top_n_mode`]: "other",
        [`${prefix}_top_n_direction`]: "top",
        [`${prefix}_other_label`]: "Other",
      },
    });
  }, false, `Group ${field.label.toLowerCase()} into top 12 plus Other`);
  const roll24 = tinyButton("Top 24", () => {
    setVisualizerState({
      options: {
        ...(visualState.options || {}),
        [`${prefix}_top_n`]: 24,
        [`${prefix}_top_n_mode`]: "filter",
        [`${prefix}_top_n_direction`]: "top",
      },
    });
  }, false, `Filter ${field.label.toLowerCase()} to top 24`);
  actions.append(roll12, roll24);
  if (currentTop > 0) {
    actions.appendChild(tinyButton("Clear Rollup", () => {
      const options = { ...(visualState.options || {}) };
      delete options[`${prefix}_top_n`];
      delete options[`${prefix}_top_n_mode`];
      delete options[`${prefix}_top_n_direction`];
      delete options[`${prefix}_other_label`];
      setVisualizerState({ options });
    }, false, `Clear ${field.label.toLowerCase()} rollup`));
  }
  if (field.slot === "color") {
    const legendVisible = (visualState.options || {}).show_legend !== false;
    actions.appendChild(tinyButton(legendVisible ? "Hide Legend" : "Show Legend", () => {
      setVisualizerState({ options: { ...(visualState.options || {}), show_legend: !legendVisible } });
    }, false, legendVisible ? "Hide legend" : "Show legend"));
  }
  if (sourceRows > 15000 && !currentSample) {
    actions.appendChild(tinyButton("Sample 10k", () => {
      setVisualizerState({
        options: {
          ...(visualState.options || {}),
          sample_rows: 10000,
          sample_method: "random",
          sample_seed: 42,
        },
      });
    }, false, "Sample rows for faster rendering"));
  } else if (currentSample) {
    actions.appendChild(tinyButton("Full Rows", () => {
      const options = { ...(visualState.options || {}) };
      delete options.sample_rows;
      delete options.sample_method;
      delete options.sample_seed;
      setVisualizerState({ options });
    }, false, "Render all rows"));
  }
  wrap.append(meta, actions);
  return wrap;
}

function visualFieldSelect(label, value, choices, onChange, focusKey) {
  const wrap = document.createElement("label");
  wrap.className = "stateframe-web-visual-field-control";
  const text = document.createElement("span");
  text.textContent = label;
  const select = document.createElement("select");
  select.className = "stateframe-web-select";
  select.dataset.focusKey = focusKey;
  for (const [choiceValue, choiceLabel] of choices) {
    const option = document.createElement("option");
    option.value = choiceValue;
    option.textContent = choiceLabel;
    select.appendChild(option);
  }
  select.value = value;
  select.addEventListener("change", () => onChange(select.value));
  wrap.append(text, select);
  return wrap;
}

function visualStatChoices(kind, slot) {
  const base = [
    ["count", "Record count"],
    ["sum", "Sum"],
    ["mean", "Mean"],
    ["median", "Median"],
    ["min", "Min"],
    ["max", "Max"],
    ["nunique", "Distinct count"],
    ["p25", "P25"],
    ["p75", "P75"],
    ["p90", "P90"],
    ["p95", "P95"],
  ];
  if (["line", "area", "bar", "lollipop", "slope", "bump_chart", "radar"].includes(kind)) {
    return [["none", "Raw values"], ...base];
  }
  return base;
}

function updateVisualFieldOption(slot, patch, visualState, setVisualizerState) {
  const fieldOptions = { ...(visualState.fieldOptions || {}) };
  fieldOptions[slot] = { ...(fieldOptions[slot] || {}), ...patch };
  setVisualizerState({ fieldOptions });
}

function renderVisualColumns(payload, definition, visualState, setVisualizerState) {
  const shell = document.createElement("div");
  shell.className = "stateframe-web-visual-column-shell";
  const queryValue = String(visualState.columnQuery || "");
  const filterMode = visualState.columnTypeFilter || "all";
  const sortMode = visualState.columnSort || "original";
  const assignable = (definition.fields || []).slice(0, 4);
  const assignedSet = visualAssignedColumnIds(visualState);
  const targetSet = visualTargetColumnIds(visualState);
  const acceptanceByColumn = visualColumnAcceptanceMap(payload, definition, visualState);
  const targetScoreByColumn = visualTargetRelevanceScores(payload, visualState);
  const allEntries = (payload.columns || []).map((column, index) => ({ column, index }));
  const visibleEntries = visualSortColumnEntries(allEntries
    .filter(({ column }) => visualColumnMatchesQuery(column, queryValue))
    .filter(({ column }) => visualColumnMatchesTypeFilter(column, filterMode, assignedSet, targetSet, acceptanceByColumn, targetScoreByColumn)), sortMode, assignedSet, targetScoreByColumn);

  const tools = document.createElement("div");
  tools.className = "stateframe-web-visual-column-tools";
  const search = document.createElement("input");
  search.type = "search";
  search.className = "stateframe-web-input";
  search.classList.add("is-search");
  search.placeholder = "Find columns";
  search.value = queryValue;
  search.dataset.focusKey = "visual-column-query";
  search.setAttribute("aria-label", "Find visualizer columns");
  search.addEventListener("input", () => setVisualizerState({ columnQuery: search.value }));
  const typeFilter = document.createElement("select");
  typeFilter.className = "stateframe-web-select";
  typeFilter.classList.add("is-type");
  typeFilter.dataset.focusKey = "visual-column-type-filter";
  typeFilter.setAttribute("aria-label", "Filter visualizer columns");
  for (const [value, label] of [
    ["all", "All"],
    ["numeric", "Numeric"],
    ["categorical", "Categorical"],
    ["date", "Date"],
    ["targets", "Targets"],
    ["target_ready", "Target-ready"],
    ["assigned", "Assigned"],
    ["available", "Available"],
  ]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    typeFilter.appendChild(option);
  }
  typeFilter.value = filterMode;
  typeFilter.addEventListener("change", () => setVisualizerState({ columnTypeFilter: typeFilter.value }));
  const sort = document.createElement("select");
  sort.className = "stateframe-web-select";
  sort.classList.add("is-sort");
  sort.dataset.focusKey = "visual-column-sort";
  sort.setAttribute("aria-label", "Sort visualizer columns");
  for (const [value, label] of [
    ["original", "Source order"],
    ["name", "Name"],
    ["type", "Type"],
    ["unique_desc", "Unique high"],
    ["missing_desc", "Missing high"],
    ["assigned_first", "Assigned first"],
    ["target_relevance", "Target relevance"],
  ]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    sort.appendChild(option);
  }
  sort.value = sortMode;
  sort.addEventListener("change", () => setVisualizerState({ columnSort: sort.value }));
  const count = textSpan(`${formatInt(visibleEntries.length)} / ${formatInt(allEntries.length)} columns`, "stateframe-web-visual-column-count");
  tools.append(count, search, typeFilter, sort);
  if (queryValue || filterMode !== "all" || sortMode !== "original") {
    tools.appendChild(tinyButton("Clear", () => setVisualizerState({
      columnQuery: "",
      columnTypeFilter: "all",
      columnSort: "original",
    }), false, "Clear column shelf search, filter, and sort"));
  }
  shell.appendChild(tools);
  const targetBar = renderVisualTargetBar(payload, visualState, setVisualizerState);
  if (targetBar) shell.appendChild(targetBar);

  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-column-list";
  for (const { column } of visibleEntries) {
    const assignedLabels = visualAssignedLabelsForColumn(definition, visualState, column.id);
    const acceptedFields = acceptanceByColumn.get(column.id) || [];
    const acceptedSlots = new Set(acceptedFields.map((field) => field.slot));
    const isTarget = targetSet.has(column.id);
    const targetScore = targetScoreByColumn.get(column.id) || null;
    const item = document.createElement("div");
    item.className = "stateframe-web-visual-column";
    if (assignedLabels.length) item.classList.add("is-assigned");
    if (isTarget) item.classList.add("is-target");
    item.draggable = true;
    item.dataset.visualColumnId = column.id;
    item.title = [
      "Drag to a visual field",
      assignedLabels.length ? `currently used by ${assignedLabels.join(", ")}` : "",
      isTarget ? "marked as target for suggestions" : "",
    ].filter(Boolean).join(" / ");
    item.addEventListener("dragstart", (event) => {
      item.classList.add("is-dragging");
      if (!event.dataTransfer) return;
      event.dataTransfer.effectAllowed = "copy";
      event.dataTransfer.setData("application/x-stateframe-column-id", column.id);
      event.dataTransfer.setData("text/plain", column.id);
    });
    item.addEventListener("dragend", () => {
      item.classList.remove("is-dragging");
    });
    wireVisualColumnPointerDrag(item, column, payload, definition, visualState, setVisualizerState);
    const name = document.createElement("div");
    name.className = "stateframe-web-visual-column-name";
    name.textContent = visualColumnDisplayName(column);
    const meta = document.createElement("div");
    meta.className = "stateframe-web-visual-column-meta";
    meta.textContent = visualColumnMetaText(column);
    const tags = document.createElement("div");
    tags.className = "stateframe-web-visual-column-tags";
    if (isTarget) tags.appendChild(textSpan("Target", "stateframe-web-visual-column-tag is-target"));
    if (targetScore && !isTarget) {
      tags.appendChild(textSpan(`Against: ${targetScore.targetLabel}`, "stateframe-web-visual-column-tag is-target-ready"));
    }
    if (assignedLabels.length) tags.appendChild(textSpan(`Used: ${assignedLabels.join(", ")}`, "stateframe-web-visual-column-tag is-assigned"));
    if (acceptedFields.length) {
      const labels = acceptedFields.slice(0, 3).map((field) => field.label).join(", ");
      const suffix = acceptedFields.length > 3 ? ` +${acceptedFields.length - 3}` : "";
      tags.appendChild(textSpan(`Fits: ${labels}${suffix}`, "stateframe-web-visual-column-tag"));
    }
    const actions = document.createElement("div");
    actions.className = "stateframe-web-action-row";
    for (const field of assignable) {
      const canAssign = acceptedSlots.has(field.slot);
      const assign = tinyButton(field.label, () => {
        assignVisualColumnToField(payload, definition, field, column.id, visualState, setVisualizerState);
      }, !canAssign, `Use as ${field.label}`);
      actions.appendChild(assign);
    }
    item.append(name, meta);
    if (tags.children.length) item.appendChild(tags);
    const quickActions = renderVisualColumnQuickActions(payload, column, visualState, setVisualizerState);
    if (quickActions) item.appendChild(quickActions);
    item.appendChild(actions);
    wrap.appendChild(item);
  }
  const emptyMessage = filterMode === "target_ready" && !targetSet.size
    ? "Mark a target column to see target-ready comparison fields."
    : filterMode === "target_ready"
      ? "No target-ready columns match the current shelf controls."
      : "No columns match the current shelf controls.";
  shell.appendChild(wrap.children.length ? wrap : empty(emptyMessage));
  return shell;
}

function renderVisualColumnQuickActions(payload, column, visualState, setVisualizerState) {
  if (!column?.id) return null;
  const recipes = visualColumnQuickRecipes(payload, column, visualState);
  const isTarget = visualTargetColumnIds(visualState).has(column.id);
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-column-quick-actions";
  const target = tinyButton(isTarget ? "Targeted" : "Mark Target", () => {
    toggleVisualTargetColumn(payload, column.id, visualState, setVisualizerState);
  }, false, isTarget ? "Remove target marker" : "Mark as target for target-aware suggestions");
  target.classList.add("is-target-marker");
  if (isTarget) target.classList.add("is-active");
  wrap.appendChild(target);
  for (const recipe of recipes.slice(0, 5)) {
    const action = tinyButton(recipe.label, () => {
      applyVisualColumnQuickRecipe(payload, recipe, visualState, setVisualizerState);
    }, false, recipe.title || recipe.description || recipe.label);
    action.classList.add("is-recipe");
    wrap.appendChild(action);
  }
  return wrap;
}

function visualColumnQuickRecipes(payload, column, visualState = {}) {
  if (!column?.id) return [];
  const recipes = [];
  const name = visualColumnDisplayName(column);
  const isNumeric = visualColumnLooksNumeric(column) && !visualColumnLooksIdentifier(column);
  const isDate = visualColumnLooksDate(column);
  const isCategorical = visualColumnLooksCategorical(column) && !visualColumnLooksIdentifier(column);
  const dateColumn = visualBestDateColumn(payload, column.id);
  const numericColumn = visualBestNumericColumn(payload, column.id);
  const categoricalColumn = visualBestCategoricalColumn(payload, column.id);
  recipes.push(...visualColumnTargetRecipes(payload, column, visualState));
  if (isDate && numericColumn) {
    recipes.push(visualQuickRecipe(payload, {
      id: "trend",
      label: "Trend",
      kind: "line",
      fields: { x: column.id, y: numericColumn.id },
      title: `${visualColumnDisplayName(numericColumn)} over ${name}`,
      description: `Trend ${visualColumnDisplayName(numericColumn)} by ${name}`,
    }));
  } else if (isNumeric) {
    recipes.push(visualQuickRecipe(payload, {
      id: "profile",
      label: "Profile",
      kind: "histogram",
      fields: { x: column.id },
      title: `Distribution of ${name}`,
      description: `Profile the distribution of ${name}`,
    }));
  } else if (isCategorical) {
    recipes.push(visualQuickRecipe(payload, {
      id: "profile",
      label: "Profile",
      kind: "bar",
      fields: { x: column.id },
      title: `Count by ${name}`,
      description: `Count records by ${name}`,
    }));
  } else if (isDate) {
    recipes.push(visualQuickRecipe(payload, {
      id: "profile",
      label: "Profile",
      kind: "histogram",
      fields: { x: column.id },
      title: `Records by ${name}`,
      description: `Profile records by ${name}`,
    }));
  }
  if (isNumeric && dateColumn) {
    recipes.push(visualQuickRecipe(payload, {
      id: "trend",
      label: "Trend",
      kind: "line",
      fields: { x: dateColumn.id, y: column.id },
      title: `${name} over ${visualColumnDisplayName(dateColumn)}`,
      description: `Trend ${name} by ${visualColumnDisplayName(dateColumn)}`,
    }));
  }
  if (isNumeric && categoricalColumn) {
    recipes.push(visualQuickRecipe(payload, {
      id: "compare",
      label: "Compare",
      kind: "bar",
      fields: { x: categoricalColumn.id, y: column.id },
      title: `${name} by ${visualColumnDisplayName(categoricalColumn)}`,
      description: `Compare ${name} across ${visualColumnDisplayName(categoricalColumn)}`,
    }));
  } else if (isCategorical && numericColumn) {
    recipes.push(visualQuickRecipe(payload, {
      id: "compare",
      label: "Compare",
      kind: "bar",
      fields: { x: column.id, y: numericColumn.id },
      title: `${visualColumnDisplayName(numericColumn)} by ${name}`,
      description: `Compare ${visualColumnDisplayName(numericColumn)} across ${name}`,
    }));
  }
  if ((isNumeric || isCategorical) && visualDefinitionById(payload, "target_association")) {
    const definition = visualDefinitionById(payload, "target_association");
    const featureField = (definition.fields || []).find((field) => field.slot === "features");
    const features = featureField
      ? defaultMultipleColumnsForVisual(payload, definition, featureField, new Set([column.id])).filter((value) => value !== column.id)
      : [];
    if (features.length) {
      recipes.push(visualQuickRecipe(payload, {
        id: "assoc",
        label: "Assoc",
        kind: "target_association",
        fields: { target: column.id, features },
        title: `Associations with ${name}`,
        description: `Rank columns associated with ${name}`,
      }));
    }
  }
  if (isNumeric && visualDefinitionById(payload, "correlation_heatmap")) {
    const dimensions = [column.id, ...visualTopNumericColumns(payload, column.id).map((item) => item.id)].slice(0, 8);
    if (dimensions.length >= 3) {
      recipes.push(visualQuickRecipe(payload, {
        id: "corr",
        label: "Corr",
        kind: "correlation_heatmap",
        fields: { dimensions },
        title: `${name} correlation matrix`,
        description: `Correlate ${name} against nearby numeric measures`,
      }));
    }
  }
  const seen = new Set();
  return recipes.filter((recipe) => {
    if (!recipe || seen.has(recipe.id)) return false;
    seen.add(recipe.id);
    return true;
  });
}

function visualQuickRecipe(payload, recipe) {
  if (!visualDefinitionById(payload, recipe.kind)) return null;
  return recipe;
}

function applyVisualColumnQuickRecipe(payload, recipe, visualState, setVisualizerState) {
  const definition = visualDefinitionById(payload, recipe.kind);
  if (!definition) return;
  const fields = recipe.fields || {};
  setVisualizerState({
    kind: recipe.kind,
    fields,
    fieldOptions: defaultFieldOptionsForVisual(payload, definition, fields),
    options: recipe.options || {},
    title: recipe.title || "",
  });
}

function renderVisualTargetBar(payload, visualState, setVisualizerState) {
  const targets = visualTargetColumns(payload, visualState);
  if (!targets.length) return null;
  const bar = document.createElement("div");
  bar.className = "stateframe-web-visual-target-bar";
  bar.appendChild(textSpan("Targets", "stateframe-web-visual-target-label"));
  for (const target of targets) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "stateframe-web-visual-target-chip";
    chip.textContent = visualColumnDisplayName(target);
    chip.title = "Remove target marker";
    chip.setAttribute("aria-label", `Remove target ${visualColumnDisplayName(target)}`);
    chip.addEventListener("click", () => toggleVisualTargetColumn(payload, target.id, visualState, setVisualizerState));
    bar.appendChild(chip);
  }
  bar.appendChild(tinyButton("Clear Targets", () => setVisualizerState({ targetColumns: [] }), false, "Clear marked target columns"));
  return bar;
}

function toggleVisualTargetColumn(payload, columnId, visualState, setVisualizerState) {
  const validIds = new Set((payload.columns || []).map((column) => column.id));
  if (!validIds.has(columnId)) return;
  const current = (visualState.targetColumns || []).filter((id, index, items) => validIds.has(id) && items.indexOf(id) === index);
  const next = current.includes(columnId)
    ? current.filter((id) => id !== columnId)
    : [...current, columnId];
  setVisualizerState({ targetColumns: next });
}

function visualTargetColumnIds(visualState) {
  return new Set((visualState.targetColumns || []).filter(Boolean).map((value) => String(value)));
}

function visualTargetColumns(payload, visualState) {
  const byId = new Map((payload.columns || []).map((column) => [column.id, column]));
  return (visualState.targetColumns || [])
    .map((id) => byId.get(id))
    .filter(Boolean);
}

function visualPrimaryTargetColumn(payload, visualState, excludeId = "") {
  return visualTargetColumns(payload, visualState).find((column) => column.id !== excludeId) || null;
}

function visualColumnTargetRecipes(payload, column, visualState) {
  const target = visualPrimaryTargetColumn(payload, visualState, column.id);
  if (!target || visualTargetColumnIds(visualState).has(column.id)) return [];
  return visualTargetRecipesForFeature(payload, target, column);
}

function visualTargetRecipesForFeature(payload, targetColumn, featureColumn) {
  if (!targetColumn?.id || !featureColumn?.id || targetColumn.id === featureColumn.id) return [];
  const recipes = [];
  const trend = visualTargetTrendRecipe(payload, targetColumn, featureColumn);
  if (trend) recipes.push(trend);
  const scatter = visualTargetScatterRecipe(payload, targetColumn, featureColumn);
  if (scatter) recipes.push(scatter);
  const profile = visualTargetProfileRecipe(payload, targetColumn, featureColumn);
  if (profile) recipes.push(profile);
  const association = visualAssociationRecipeForTarget(payload, targetColumn, featureColumn);
  if (association) recipes.push(association);
  return recipes;
}

function visualTargetTrendRecipe(payload, targetColumn, featureColumn) {
  if (!visualDefinitionById(payload, "line")) return null;
  if (!visualColumnLooksNumeric(targetColumn) || !visualColumnLooksDate(featureColumn)) return null;
  const targetName = visualColumnDisplayName(targetColumn);
  const featureName = visualColumnDisplayName(featureColumn);
  return visualQuickRecipe(payload, {
    id: `target-trend:${targetColumn.id}:${featureColumn.id}`,
    label: "Target Trend",
    kind: "line",
    fields: { x: featureColumn.id, y: targetColumn.id },
    title: `${targetName} over ${featureName}`,
    description: `Trend marked target ${targetName} by ${featureName}`,
  });
}

function visualTargetScatterRecipe(payload, targetColumn, featureColumn) {
  if (!visualDefinitionById(payload, "scatter")) return null;
  if (!visualColumnLooksNumeric(targetColumn) || !visualColumnLooksNumeric(featureColumn) || visualColumnLooksIdentifier(featureColumn)) return null;
  const targetName = visualColumnDisplayName(targetColumn);
  const featureName = visualColumnDisplayName(featureColumn);
  return visualQuickRecipe(payload, {
    id: `target-scatter:${targetColumn.id}:${featureColumn.id}`,
    label: "Vs Target",
    kind: "scatter",
    fields: { x: featureColumn.id, y: targetColumn.id },
    title: `${targetName} vs ${featureName}`,
    description: `Compare ${featureName} against marked target ${targetName}`,
  });
}

function visualTargetProfileRecipe(payload, targetColumn, featureColumn) {
  if (!visualDefinitionById(payload, "target_profile")) return null;
  if (visualColumnLooksIdentifier(targetColumn) || visualColumnLooksIdentifier(featureColumn)) return null;
  if (!visualColumnLooksNumeric(targetColumn) && !visualColumnLooksCategorical(targetColumn)) return null;
  if (!visualColumnLooksNumeric(featureColumn) && !visualColumnLooksCategorical(featureColumn) && !visualColumnLooksDate(featureColumn)) return null;
  const targetName = visualColumnDisplayName(targetColumn);
  const featureName = visualColumnDisplayName(featureColumn);
  return visualQuickRecipe(payload, {
    id: `target-profile:${targetColumn.id}:${featureColumn.id}`,
    label: "Target Profile",
    kind: "target_profile",
    fields: { target: targetColumn.id, feature: featureColumn.id },
    title: `${targetName} by ${featureName}`,
    description: `Profile marked target ${targetName} across ${featureName}`,
  });
}

function visualAssociationRecipeForTarget(payload, targetColumn, featureColumn = null) {
  const definition = visualDefinitionById(payload, "target_association");
  if (!definition || !targetColumn?.id || visualColumnLooksIdentifier(targetColumn)) return null;
  if (!visualColumnLooksNumeric(targetColumn) && !visualColumnLooksCategorical(targetColumn)) return null;
  const featureField = (definition.fields || []).find((field) => field.slot === "features");
  if (!featureField) return null;
  const candidateIds = new Set(visualCandidateColumns(payload, definition, featureField).map((column) => column.id));
  const used = new Set([targetColumn.id]);
  const features = [];
  if (featureColumn?.id && featureColumn.id !== targetColumn.id && candidateIds.has(featureColumn.id)) {
    features.push(featureColumn.id);
    used.add(featureColumn.id);
  }
  const defaults = defaultMultipleColumnsForVisual(payload, definition, featureField, used)
    .filter((id) => id !== targetColumn.id && !features.includes(id));
  features.push(...defaults);
  if (!features.length) return null;
  const targetName = visualColumnDisplayName(targetColumn);
  return visualQuickRecipe(payload, {
    id: `target-assoc:${targetColumn.id}${featureColumn?.id ? `:${featureColumn.id}` : ""}`,
    label: "Assoc",
    kind: "target_association",
    fields: { target: targetColumn.id, features: features.slice(0, 12) },
    title: `Associations with ${targetName}`,
    description: `Rank columns associated with marked target ${targetName}`,
  });
}

function visualTargetSuggestions(payload, visualState) {
  const suggestions = [];
  for (const target of visualTargetColumns(payload, visualState).slice(0, 3)) {
    const association = visualAssociationRecipeForTarget(payload, target);
    if (association) suggestions.push(visualSuggestionFromRecipe(association, `Marked target: ${visualColumnDisplayName(target)}`));
    for (const feature of visualTargetFeatureCandidates(payload, target).slice(0, 3)) {
      const recipe = visualTargetPreferredRecipe(payload, target, feature);
      if (recipe) suggestions.push(visualSuggestionFromRecipe(recipe, `Against ${visualColumnDisplayName(target)}`));
    }
  }
  const seen = new Set();
  return suggestions.filter((suggestion) => {
    const key = `${suggestion.spec?.kind || ""}:${suggestion.title || ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 6);
}

function visualTargetFeatureCandidates(payload, targetColumn) {
  const ordered = [
    visualBestCategoricalColumn(payload, targetColumn.id),
    visualBestDateColumn(payload, targetColumn.id),
    visualBestNumericColumn(payload, targetColumn.id),
    ...visualTopNumericColumns(payload, targetColumn.id).slice(0, 3),
  ].filter(Boolean);
  const seen = new Set();
  return ordered.filter((column) => {
    if (column.id === targetColumn.id || seen.has(column.id)) return false;
    seen.add(column.id);
    return true;
  });
}

function visualTargetPreferredRecipe(payload, targetColumn, featureColumn) {
  const recipes = visualTargetRecipesForFeature(payload, targetColumn, featureColumn);
  if (visualColumnLooksDate(featureColumn)) return recipes.find((recipe) => recipe?.kind === "line") || recipes[0] || null;
  if (visualColumnLooksNumeric(featureColumn) && visualColumnLooksNumeric(targetColumn)) return recipes.find((recipe) => recipe?.kind === "scatter") || recipes[0] || null;
  return recipes.find((recipe) => recipe?.kind === "target_profile") || recipes[0] || null;
}

function visualTargetRelevanceScores(payload, visualState) {
  const scores = new Map();
  const targets = visualTargetColumns(payload, visualState);
  if (!targets.length) return scores;
  const targetIds = new Set(targets.map((column) => column.id));
  for (const column of payload.columns || []) {
    if (!column?.id) continue;
    if (targetIds.has(column.id)) {
      scores.set(column.id, {
        score: 1000,
        targetId: column.id,
        targetLabel: visualColumnDisplayName(column),
        modeLabel: "target",
        recipeCount: 0,
      });
      continue;
    }
    let best = null;
    for (const target of targets) {
      const relation = visualTargetRelationScore(payload, target, column);
      if (!relation) continue;
      const candidate = {
        ...relation,
        targetId: target.id,
        targetLabel: visualColumnDisplayName(target),
      };
      if (!best || candidate.score > best.score) best = candidate;
    }
    if (best) scores.set(column.id, best);
  }
  return scores;
}

function visualTargetRelationScore(payload, targetColumn, featureColumn) {
  if (!targetColumn?.id || !featureColumn?.id || targetColumn.id === featureColumn.id) return null;
  if (visualColumnLooksIdentifier(targetColumn) || visualColumnLooksIdentifier(featureColumn)) return null;
  const targetNumeric = visualColumnLooksNumeric(targetColumn);
  const targetCategorical = visualColumnLooksCategorical(targetColumn);
  const featureNumeric = visualColumnLooksNumeric(featureColumn);
  const featureCategorical = visualColumnLooksCategorical(featureColumn);
  const featureDate = visualColumnLooksDate(featureColumn);
  const modes = [];
  let score = 0;
  if (targetNumeric && featureDate && visualDefinitionById(payload, "line")) {
    score += 95;
    modes.push("trend");
  }
  if (targetNumeric && featureNumeric && visualDefinitionById(payload, "scatter")) {
    score += 85;
    modes.push("compare");
  }
  if ((targetNumeric || targetCategorical)
      && (featureNumeric || featureCategorical || featureDate)
      && visualDefinitionById(payload, "target_profile")) {
    score += 70;
    modes.push("profile");
  }
  if ((targetNumeric || targetCategorical)
      && (featureNumeric || featureCategorical)
      && visualDefinitionById(payload, "target_association")) {
    score += 45;
    modes.push("association");
  }
  if (!modes.length) return null;
  score += visualTargetFeatureQualityScore(featureColumn);
  return {
    score,
    modeLabel: modes[0],
    recipeCount: modes.length,
  };
}

function visualTargetFeatureQualityScore(column) {
  if (!column?.id || visualColumnLooksIdentifier(column)) return -100;
  let score = 0;
  const distinct = visualColumnDistinctCount(column);
  if (visualColumnLooksDate(column)) score += 12;
  if (visualColumnLooksNumeric(column)) score += 10 + clampNumber(visualNumericDimensionScore(column), 0, -8, 12);
  if (visualColumnLooksCategorical(column)) {
    if (Number.isFinite(distinct)) {
      if (distinct >= 2 && distinct <= 16) score += 18;
      else if (distinct <= 40) score += 12;
      else if (distinct <= 80) score += 4;
      else score -= 14;
    } else {
      score += 4;
    }
  }
  const missingRatio = visualColumnMissingRatio(column);
  if (Number.isFinite(missingRatio) && missingRatio > 0) score -= Math.min(20, missingRatio * 20);
  return score;
}

function visualSuggestionFromRecipe(recipe, reason) {
  return {
    title: recipe.title,
    reason,
    spec: {
      kind: recipe.kind,
      fields: recipe.fields,
      options: recipe.options || {},
      title: recipe.title,
    },
  };
}

function visualColumnAcceptanceMap(payload, definition, visualState) {
  const result = new Map();
  for (const field of definition.fields || []) {
    for (const column of visualCandidateColumnsForField(payload, definition, field, visualState)) {
      const fields = result.get(column.id) || [];
      fields.push(field);
      result.set(column.id, fields);
    }
  }
  return result;
}

function visualAssignedColumnIds(visualState) {
  const ids = new Set();
  for (const value of Object.values(visualState.fields || {})) {
    if (Array.isArray(value)) {
      value.filter(Boolean).forEach((item) => ids.add(String(item)));
    } else if (value) {
      ids.add(String(value));
    }
  }
  return ids;
}

function visualAssignedLabelsForColumn(definition, visualState, columnId) {
  const labels = [];
  for (const field of definition.fields || []) {
    const value = visualState.fields?.[field.slot];
    if (Array.isArray(value) && value.includes(columnId)) labels.push(field.label);
    else if (value === columnId) labels.push(field.label);
  }
  return labels;
}

function visualColumnMatchesQuery(column, query) {
  const needle = String(query || "").trim().toLowerCase();
  if (!needle) return true;
  return [
    column?.id,
    column?.display_name,
    column?.source_name,
    column?.name,
    column?.label,
    column?.semantic_type,
    column?.dtype,
  ].some((value) => String(value || "").toLowerCase().includes(needle));
}

function visualColumnMatchesTypeFilter(column, filterMode, assignedSet, targetSet, acceptanceByColumn, targetScoreByColumn = new Map()) {
  if (filterMode === "numeric") return visualColumnLooksNumeric(column);
  if (filterMode === "categorical") return visualColumnLooksCategorical(column);
  if (filterMode === "date") return visualColumnLooksDate(column);
  if (filterMode === "targets") return targetSet.has(column.id);
  if (filterMode === "target_ready") return !targetSet.has(column.id) && Boolean(targetScoreByColumn.get(column.id));
  if (filterMode === "assigned") return assignedSet.has(column.id);
  if (filterMode === "available") return Boolean((acceptanceByColumn.get(column.id) || []).length);
  return true;
}

function visualSortColumnEntries(entries, sortMode, assignedSet, targetScoreByColumn = new Map()) {
  const sorted = [...entries];
  sorted.sort((left, right) => {
    if (sortMode === "name") return visualColumnDisplayName(left.column).localeCompare(visualColumnDisplayName(right.column)) || left.index - right.index;
    if (sortMode === "type") {
      const typeCompare = visualColumnTypeRank(left.column) - visualColumnTypeRank(right.column);
      return typeCompare || String(left.column.semantic_type || "").localeCompare(String(right.column.semantic_type || "")) || visualColumnDisplayName(left.column).localeCompare(visualColumnDisplayName(right.column));
    }
    if (sortMode === "unique_desc") return compareNumbersDesc(visualColumnDistinctCount(left.column), visualColumnDistinctCount(right.column)) || visualColumnDisplayName(left.column).localeCompare(visualColumnDisplayName(right.column));
    if (sortMode === "missing_desc") return compareNumbersDesc(visualColumnMissingRatio(left.column), visualColumnMissingRatio(right.column)) || compareNumbersDesc(visualColumnMissingCount(left.column), visualColumnMissingCount(right.column)) || visualColumnDisplayName(left.column).localeCompare(visualColumnDisplayName(right.column));
    if (sortMode === "assigned_first") {
      const assignedCompare = Number(assignedSet.has(right.column.id)) - Number(assignedSet.has(left.column.id));
      return assignedCompare || left.index - right.index;
    }
    if (sortMode === "target_relevance") {
      const targetCompare = compareNumbersDesc(
        visualTargetSortScore(left.column, assignedSet, targetScoreByColumn),
        visualTargetSortScore(right.column, assignedSet, targetScoreByColumn),
      );
      return targetCompare || left.index - right.index;
    }
    return left.index - right.index;
  });
  return sorted;
}

function visualTargetSortScore(column, assignedSet, targetScoreByColumn) {
  const score = Number(targetScoreByColumn.get(column.id)?.score || 0);
  return score + (assignedSet.has(column.id) ? 5 : 0);
}

function visualColumnTypeRank(column) {
  if (visualColumnLooksDate(column)) return 0;
  if (visualColumnLooksNumeric(column)) return 1;
  if (visualColumnLooksCategorical(column)) return 2;
  return 3;
}

function compareNumbersDesc(leftValue, rightValue) {
  const left = Number(leftValue);
  const right = Number(rightValue);
  const leftFinite = Number.isFinite(left);
  const rightFinite = Number.isFinite(right);
  if (leftFinite && rightFinite) return right - left;
  if (leftFinite) return -1;
  if (rightFinite) return 1;
  return 0;
}

function visualColumnDisplayName(column) {
  return column?.display_name || column?.source_name || column?.name || column?.label || column?.id || "";
}

function visualColumnMetaText(column) {
  const typeText = [column?.semantic_type || "unknown", column?.dtype || ""].filter(Boolean).join(" / ");
  const parts = [typeText];
  const distinct = visualColumnDistinctCount(column);
  if (Number.isFinite(distinct)) parts.push(`${formatInt(distinct)} unique`);
  const missingRatio = visualColumnMissingRatio(column);
  const missingCount = visualColumnMissingCount(column);
  if (Number.isFinite(missingRatio) && missingRatio > 0) parts.push(`${formatPercent(missingRatio)} missing`);
  else if (Number.isFinite(missingCount) && missingCount > 0) parts.push(`${formatInt(missingCount)} missing`);
  return parts.filter(Boolean).join(" / ");
}

function visualBestDateColumn(payload, excludeId = "") {
  return (payload.columns || [])
    .filter((column) => column.id !== excludeId && visualColumnLooksDate(column))
    .sort((left, right) => visualDateColumnScore(right) - visualDateColumnScore(left))[0] || null;
}

function visualDateColumnScore(column) {
  const name = String(column?.source_name || column?.display_name || column?.id || "").toLowerCase();
  let score = 0;
  if (/(^|_|\b)(date|time|timestamp|read_date|event_date)($|_|\b)/.test(name)) score += 8;
  if (name.includes("created") || name.includes("updated")) score -= 2;
  const distinct = visualColumnDistinctCount(column);
  if (distinct >= 2) score += Math.min(6, Math.log10(distinct + 1) * 2);
  return score;
}

function visualBestNumericColumn(payload, excludeId = "") {
  return visualTopNumericColumns(payload, excludeId)[0] || null;
}

function visualTopNumericColumns(payload, excludeId = "") {
  return (payload.columns || [])
    .filter((column) => column.id !== excludeId && visualColumnLooksNumeric(column) && !visualColumnLooksIdentifier(column))
    .sort((left, right) => visualNumericDimensionScore(right) - visualNumericDimensionScore(left));
}

function visualBestCategoricalColumn(payload, excludeId = "") {
  return (payload.columns || [])
    .filter((column) => column.id !== excludeId && visualColumnLooksCategorical(column) && !visualColumnLooksIdentifier(column))
    .sort((left, right) => visualCategoricalCompareScore(right) - visualCategoricalCompareScore(left))[0] || null;
}

function visualCategoricalCompareScore(column) {
  const name = String(column?.source_name || column?.display_name || column?.id || "").toLowerCase();
  const distinct = visualColumnDistinctCount(column);
  let score = 0;
  if (Number.isFinite(distinct)) {
    if (distinct >= 2 && distinct <= 16) score += 9;
    else if (distinct <= 40) score += 6;
    else if (distinct <= 80) score += 2;
    else score -= 5;
  }
  if (/(^|_|\b)(type|class|segment|category|city|state|status|group)($|_|\b)/.test(name)) score += 5;
  if (/(^|_|\b)(id|key|uuid|code)($|_|\b)/.test(name)) score -= 8;
  return score;
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

function renderVisualOptions(payload, definition, visualState, setVisualizerState, ui, setUi) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-options";
  const visibleGroups = [];
  let shownCount = 0;
  let availableCount = 0;
  for (const group of definition.option_groups || []) {
    const visibleControls = (group.controls || []).filter((control) => {
      if (!visualControlMatchesMode(control, visualState.controlMode)) return false;
      if (!visualControlMatchesQuery(control, visualState.controlQuery)) return false;
      return visualControlApplies(control, group, definition, visualState, payload);
    });
    const relevantControls = (group.controls || []).filter((control) => visualControlApplies(control, group, definition, visualState, payload));
    availableCount += relevantControls.length;
    shownCount += visibleControls.length;
    if (!visibleControls.length) continue;
    visibleGroups.push({ ...group, controls: visibleControls });
  }

  const toolbar = document.createElement("div");
  toolbar.className = "stateframe-web-visual-control-toolbar";
  const mode = document.createElement("select");
  mode.className = "stateframe-web-select";
  mode.dataset.focusKey = "visual-control-mode";
  [
    ["basic", "Basic"],
    ["advanced", "Advanced"],
    ["expert", "Expert"],
  ].forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    mode.appendChild(option);
  });
  mode.value = visualState.controlMode || "basic";
  mode.addEventListener("change", () => setVisualizerState({ controlMode: mode.value }));
  const query = document.createElement("input");
  query.className = "stateframe-web-input";
  query.placeholder = "Find controls";
  query.dataset.focusKey = "visual-control-query";
  query.value = visualState.controlQuery || "";
  query.addEventListener("input", () => setVisualizerState({ controlQuery: query.value }));
  toolbar.append(mode, query, textSpan(`${shownCount} shown / ${availableCount} relevant`, "stateframe-web-visual-control-count"));
  wrap.appendChild(toolbar);

  if (!visibleGroups.length) {
    wrap.appendChild(empty("No controls match the current mode and search."));
    return wrap;
  }

  for (const group of visibleGroups) {
    const details = document.createElement("details");
    details.className = "stateframe-web-visual-option-group";
    const key = `${definition.id}:${group.id}`;
    const defaultOpen = visualOptionGroupDefaultOpen(group, visualState);
    details.open = Object.prototype.hasOwnProperty.call(ui.visualOptionOpen, key) ? ui.visualOptionOpen[key] !== false : defaultOpen;
    details.addEventListener("toggle", () => {
      ui.visualOptionOpen[key] = details.open;
    });
    const summary = document.createElement("summary");
    summary.textContent = `${group.title} (${group.controls.length})`;
    details.appendChild(summary);
    const body = document.createElement("div");
    body.className = "stateframe-web-visual-option-body";
    for (const control of group.controls) {
      body.appendChild(renderVisualOptionControl(control, visualState, setVisualizerState));
    }
    details.appendChild(body);
    wrap.appendChild(details);
  }
  return wrap;
}

function visualControlMatchesMode(control, mode) {
  const rank = { basic: 0, advanced: 1, expert: 2 };
  const current = rank[mode || "basic"] ?? 0;
  const level = rank[control.level || "advanced"] ?? 1;
  return level <= current;
}

function visualControlMatchesQuery(control, query) {
  const needle = String(query || "").trim().toLowerCase();
  if (!needle) return true;
  return [
    control.id,
    control.label,
    control.help,
    control.level,
    ...(control.choices || []).flatMap((choice) => [choice.value, choice.label]),
  ].some((value) => String(value || "").toLowerCase().includes(needle));
}

function visualControlApplies(control, group, definition, visualState, payload) {
  const id = control.id;
  const fields = visualState.fields || {};
  const slots = new Set((definition.fields || []).map((field) => field.slot));
  if (["facet_col_wrap", "facet_shared_x", "facet_shared_y"].includes(id)) {
    return Boolean(fields.facet || fields.facet_row || slots.has("facet") || slots.has("facet_row"));
  }
  if (id === "x_rangeslider") {
    return Boolean(fields.x || slots.has("x"));
  }
  if (id.startsWith("x_") || ["log_x", "reverse_x", "sort_x", "x_reference", "x_reference_label"].includes(id)) {
    return Boolean(fields.x || fields.theta || fields.values || fields.locations || slots.has("x") || slots.has("theta") || slots.has("values") || slots.has("locations"));
  }
  if (id.startsWith("y_") || ["log_y", "reverse_y", "zero_line"].includes(id)) {
    return Boolean(fields.y || fields.r || fields.values || slots.has("y") || slots.has("r") || slots.has("values"));
  }
  if (["color_sequence", "continuous_color_scale", "show_legend"].includes(id)) {
    return Boolean(fields.color || slots.has("color") || definition.family === "Geographic" || definition.family === "Matrix");
  }
  if (id.startsWith("color_top_n") || id === "color_other_label") {
    return Boolean(fields.color);
  }
  if (id.startsWith("facet_top_n") || id === "facet_other_label") {
    return Boolean(fields.facet || fields.facet_row);
  }
  if (["date_bucket", "rolling_window", "rolling_stat", "cumulative"].includes(id)) {
    if (id === "date_bucket" && fields.x) return false;
    const xColumn = fields.x;
    const column = (payload.columns || []).find((item) => item.id === xColumn);
    const type = String(column?.semantic_type || column?.dtype || "").toLowerCase();
    return Boolean(fields.x && (type.includes("date") || type.includes("time") || ["line", "area", "bar"].includes(definition.id)));
  }
  if (id === "calendar_aggregation" && fields.values && visualSlotSupportsStat(definition.id, "values")) return false;
  if (["top_n", "top_n_direction", "top_n_mode", "other_label", "include_missing_category", "missing_category_label"].includes(id)) {
    return Boolean(fields.x || fields.names || fields.path || fields.locations || definition.id === "missingness");
  }
  if (["sample_rows", "sample_method", "sample_seed", "dedupe_rows"].includes(id)) return true;
  if (id === "aggregation" && visualHasMeasureBehavior(definition, fields)) {
    return false;
  }
  if (["aggregation", "value_transform", "sort_by"].includes(id)) {
    return Boolean(fields.x || fields.y || fields.y2 || fields.values || fields.names || fields.path || definition.id === "missingness");
  }
  if (group.id === "references") {
    return Boolean(fields.x || fields.y || fields.y2 || fields.values || fields.r);
  }
  return true;
}

function visualHasMeasureBehavior(definition, fields) {
  return ["y", "y2", "values", "r", "z"].some((slot) => fields?.[slot] && visualSlotSupportsStat(definition.id, slot));
}

function visualOptionGroupDefaultOpen(group, visualState) {
  if (visualState.controlMode === "expert") return group.id !== "advanced";
  if (visualState.controlMode === "advanced") return ["marks", "data", "axes", "references"].includes(group.id);
  return ["marks", "data"].includes(group.id);
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
    input.type = control.kind === "number" ? "number" : control.kind === "color" ? "color" : "text";
    if (control.kind === "number") input.step = "any";
    input.value = control.kind === "color" ? validHexColor(current, control.default || "#000000") : current ?? "";
    input.addEventListener("input", () => setVisualizerState({ options: { ...(visualState.options || {}), [control.id]: input.value } }));
  }
  input.dataset.focusKey = `visual-option-${control.id}`;
  label.append(title, input);
  if (control.help) label.appendChild(textSpan(control.help, "stateframe-web-visual-help"));
  return label;
}

function validHexColor(value, fallback) {
  const candidate = String(value || "").trim();
  return /^#[0-9a-fA-F]{6}$/.test(candidate) ? candidate : fallback;
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
    pinnedColumnIds: [],
    pinnedRowIndices: [],
    filters: {},
    globalSearch: "",
    sorts: [],
    selectedCell: null,
    columnRenames: {},
  }));
  const loadFull = button("Load Full", () => {
    sendCommand("open_viewer", {
      height: payload.view?.height || 640,
      maxRows: "all",
      viewerState,
    });
  });
  const visualizerButton = button("Visualizer", () => {
    sendCommand("open_visualizer", {
      height: payload.view?.height || 640,
      maxRows: 500,
      viewerState,
    });
  });
  const cleanButton = button("Clean", () => {
    sendCommand("open_cleaning", {
      height: payload.view?.height || 640,
      maxRows: 500,
      viewerState,
    });
  });
  const modelButton = button("Model", () => {
    sendCommand("open_modeling", {
      height: payload.view?.height || 640,
      maxRows: 500,
      viewerState,
    });
  });
  loadFull.disabled = !payload.view?.truncated;
  loadFull.title = payload.view?.truncated
    ? "Send all rows for this selected state to the browser preview."
    : "All rows are already loaded in the browser preview.";
  top.append(title, meta, search, matchCount, previousMatch, nextMatch, columnsToggle, inspectorToggle, clear, loadFull, cleanButton, modelButton, visualizerButton, save);
  shell.appendChild(renderViewerLineageBar(payload, viewerState, ui, setUi));
  shell.appendChild(top);
  shell.appendChild(renderViewerDatasetStrip(payload, viewerState, computed));
  if (viewerState.showFilterBar) {
    shell.appendChild(renderViewerFilterBar(payload, viewerState, computed, setViewerState));
  } else if (hasViewerViewState(viewerState)) {
    const collapsed = document.createElement("div");
    collapsed.className = "stateframe-web-viewer-filterbar is-collapsed";
    collapsed.append(
      textSpan(viewerStateFilterSummary(payload, viewerState, computed), "stateframe-web-filterbar-summary"),
      button("Show Filters", () => setViewerState({ showFilterBar: true })),
    );
    shell.appendChild(collapsed);
  }

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
      min: 220,
      max: 520,
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
    body.appendChild(renderViewerInspector(payload, viewerState, selectedColumn, setViewerState, sendCommand, computed));
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
    for (const [index, entry] of compactLineage(lineage).entries()) {
      if (index > 0) {
        const sep = document.createElement("span");
        sep.className = "stateframe-web-lineage-separator";
        sep.textContent = ">";
        trail.appendChild(sep);
      }
      if (entry?.isEllipsis) {
        const chip = document.createElement("span");
        chip.className = "stateframe-web-lineage-chip is-muted";
        chip.textContent = entry.label;
        chip.title = "Earlier lineage entries are available in Lineage Details";
        trail.appendChild(chip);
        continue;
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

function compactLineage(lineage, limit = 5) {
  if (!Array.isArray(lineage) || lineage.length <= limit) return lineage || [];
  const head = lineage.slice(0, 1);
  const tail = lineage.slice(-(limit - 2));
  return [
    ...head,
    { isEllipsis: true, label: `${lineage.length - head.length - tail.length} more` },
    ...tail,
  ];
}

function renderViewerDatasetStrip(payload, state, computed) {
  const strip = document.createElement("div");
  strip.className = "stateframe-web-viewer-dataset-strip";
  const summary = payload.summary || {};
  const view = payload.view || {};
  const visibleCount = visibleViewerColumns(payload, state).length;
  const hiddenCount = (state.hiddenColumnIds || []).length;
  const pinnedColumnCount = (state.pinnedColumnIds || []).length;
  const pinnedRowCount = (state.pinnedRowIndices || []).length;
  const items = [
    ["Rows", formatInt(view.row_count || summary.row_count)],
    ["Preview", `${formatInt(view.displayed_row_count || 0)}${view.truncated ? " truncated" : ""}`],
    ["Filtered", `${formatInt(computed.indices.length)} (${formatPercent((computed.indices.length || 0) / Math.max(1, Number(view.displayed_row_count || 0)))})`],
    ["Columns", `${formatInt(visibleCount)} visible / ${formatInt(view.column_count || 0)}`],
    ["Missing", formatPercent(summary.missing_cell_ratio)],
    ["Memory", formatBytes(summary.memory_bytes)],
  ];
  if (summary.duplicate_rows !== null && summary.duplicate_rows !== undefined) {
    items.push(["Duplicate rows", formatInt(summary.duplicate_rows)]);
  }
  if (hiddenCount) items.push(["Offloaded", formatInt(hiddenCount)]);
  if (pinnedColumnCount || pinnedRowCount) items.push(["Pinned", `${formatInt(pinnedColumnCount)} col / ${formatInt(pinnedRowCount)} row`]);
  for (const [label, value] of items) {
    const item = document.createElement("div");
    item.className = "stateframe-web-dataset-stat";
    item.append(
      textSpan(label, "stateframe-web-dataset-stat-label"),
      textSpan(value || "0", "stateframe-web-dataset-stat-value"),
    );
    strip.appendChild(item);
  }
  return strip;
}

function renderViewerFilterBar(payload, state, computed, setViewerState) {
  const bar = document.createElement("div");
  bar.className = "stateframe-web-viewer-filterbar";
  const summary = textSpan(viewerStateFilterSummary(payload, state, computed), "stateframe-web-filterbar-summary");
  const chips = document.createElement("div");
  chips.className = "stateframe-web-filter-chips";

  if (state.globalSearch) {
    chips.appendChild(removableChip(`search: ${state.globalSearch}`, () => setViewerState({ globalSearch: "" })));
  }
  for (const [columnId, filter] of Object.entries(state.filters || {})) {
    if (!filter || !Object.keys(filter).length) continue;
    const column = getViewerColumn(payload, columnId);
    if (!column) continue;
    chips.appendChild(removableChip(`${effectiveColumnName(column, state)}: ${filterLabel(filter)}`, () => {
      const next = { ...(state.filters || {}) };
      delete next[columnId];
      setViewerState({ filters: next });
    }));
  }
  for (const [index, sort] of (state.sorts || []).entries()) {
    const column = getViewerColumn(payload, sort.id);
    if (!column) continue;
    chips.appendChild(removableChip(`${index + 1}. ${effectiveColumnName(column, state)} ${sort.direction}`, () => {
      setViewerState({ sorts: (state.sorts || []).filter((_, sortIndex) => sortIndex !== index) });
    }));
  }
  if (!chips.childElementCount) chips.appendChild(textSpan("No filters or sorts", "stateframe-web-filterbar-empty"));

  const copyCode = button("Copy Code", (event) => copyTextToClipboard(viewerCodeForState(payload, state), event.currentTarget));
  const copyCell = button("Copy Cell", (event) => {
    const cell = state.selectedCell;
    const column = getViewerColumn(payload, cell?.columnId);
    const value = cell && column ? valueFor(payload, cell.rowIndex, column) : "";
    copyTextToClipboard(String(value ?? ""), event.currentTarget);
  });
  copyCell.disabled = !state.selectedCell;
  const clearFilters = button("Clear Filters", () => setViewerState({ filters: {}, globalSearch: "" }));
  clearFilters.disabled = !state.globalSearch && !Object.keys(state.filters || {}).length;
  const clearSorts = button("Clear Sorts", () => setViewerState({ sorts: [] }));
  clearSorts.disabled = !(state.sorts || []).length;
  const hide = button("Hide Filters", () => setViewerState({ showFilterBar: false }));
  bar.append(summary, chips, clearFilters, clearSorts, copyCell, copyCode, hide);
  return bar;
}

function removableChip(label, onRemove) {
  const chip = document.createElement("button");
  chip.type = "button";
  chip.className = "stateframe-web-filter-chip";
  chip.textContent = `${label} x`;
  chip.title = "Remove";
  chip.addEventListener("click", onRemove);
  return chip;
}

function viewerStateFilterSummary(payload, state, computed) {
  const shown = computed.indices.length;
  const total = Number(payload.view?.displayed_row_count || 0);
  const sorts = (state.sorts || []).length;
  const filters = Object.keys(state.filters || {}).length + (state.globalSearch ? 1 : 0);
  const parts = [`${formatInt(shown)} of ${formatInt(total)} preview rows`];
  if (filters) parts.push(`${formatInt(filters)} filter${filters === 1 ? "" : "s"}`);
  if (sorts) parts.push(`${formatInt(sorts)} sort${sorts === 1 ? "" : "s"}`);
  if (state.globalSearch && computed.matchStats?.capped) {
    parts.push(`${formatInt(computed.matches.length)} highlighted`);
  }
  return parts.join(" / ");
}

function hasViewerViewState(state) {
  return Boolean(
    state.globalSearch
    || Object.keys(state.filters || {}).length
    || Object.keys(state.columnRenames || {}).length
    || (state.sorts || []).length
    || (state.pinnedColumnIds || []).length
    || (state.pinnedRowIndices || []).length
  );
}

function numericFilterLabel(filter) {
  const mode = filter.mode || "between";
  const value = numericFilterInput(filter.value);
  const min = numericFilterInput(filter.min);
  const max = numericFilterInput(filter.max);
  if (mode === "eq") return value === null ? "equals" : `= ${value}`;
  if (mode === "neq") return value === null ? "not equal" : `!= ${value}`;
  if (mode === "gt") return value === null ? "greater than" : `> ${value}`;
  if (mode === "gte") return value === null ? "at least" : `>= ${value}`;
  if (mode === "lt") return value === null ? "less than" : `< ${value}`;
  if (mode === "lte") return value === null ? "at most" : `<= ${value}`;
  if (mode === "outside") {
    const parts = [];
    if (min !== null) parts.push(`< ${min}`);
    if (max !== null) parts.push(`> ${max}`);
    return parts.join(" or ") || "outside range";
  }
  const parts = [];
  if (min !== null) parts.push(`>= ${min}`);
  if (max !== null) parts.push(`<= ${max}`);
  return parts.join(" and ") || "between";
}

function numericFilterCodeLines(columnName, filter) {
  const series = `pd.to_numeric(view[${columnName}], errors="coerce")`;
  const mode = filter.mode || "between";
  const value = numericFilterInput(filter.value);
  const min = numericFilterInput(filter.min);
  const max = numericFilterInput(filter.max);
  if (mode === "eq" && value !== null) return [`view = view[${series}.eq(${JSON.stringify(value)})]`];
  if (mode === "neq" && value !== null) return [`view = view[${series}.ne(${JSON.stringify(value)})]`];
  if (mode === "gt" && value !== null) return [`view = view[${series} > ${JSON.stringify(value)}]`];
  if (mode === "gte" && value !== null) return [`view = view[${series} >= ${JSON.stringify(value)}]`];
  if (mode === "lt" && value !== null) return [`view = view[${series} < ${JSON.stringify(value)}]`];
  if (mode === "lte" && value !== null) return [`view = view[${series} <= ${JSON.stringify(value)}]`];
  if (mode === "outside") {
    const parts = [];
    if (min !== null) parts.push(`(${series} < ${JSON.stringify(min)})`);
    if (max !== null) parts.push(`(${series} > ${JSON.stringify(max)})`);
    return parts.length ? [`view = view[${parts.join(" | ")}]`] : [];
  }
  const lines = [];
  if (min !== null) lines.push(`view = view[${series} >= ${JSON.stringify(min)}]`);
  if (max !== null) lines.push(`view = view[${series} <= ${JSON.stringify(max)}]`);
  return lines;
}

function filterLabel(filter) {
  if (filter.kind === "numeric") {
    return numericFilterLabel(filter);
  }
  if (filter.kind === "datetime") {
    const parts = [];
    if (filter.min) parts.push(`from ${filter.min}`);
    if (filter.max) parts.push(`to ${filter.max}`);
    return parts.join(" ") || "date filter";
  }
  if (filter.kind === "empty") return "is empty";
  if (filter.kind === "not_empty") return "is not empty";
  const textLabels = {
    contains: "contains",
    not_contains: "does not contain",
    equals: "equals",
    not_equals: "not equal",
    starts: "starts with",
  };
  return `${textLabels[filter.mode || "contains"] || filter.mode || "contains"} ${filter.value || ""}`;
}

function viewerCodeForState(payload, state, frameName = "df") {
  const lines = [`view = ${frameName}`];
  for (const [columnId, filter] of Object.entries(state.filters || {})) {
    const column = getViewerColumn(payload, columnId);
    if (!column || !filter || !Object.keys(filter).length) continue;
    const name = JSON.stringify(column.source_name);
    if (filter.kind === "numeric") {
      lines.push(...numericFilterCodeLines(name, filter));
    } else if (filter.kind === "datetime") {
      if (filter.min) lines.push(`view = view[pd.to_datetime(view[${name}], errors="coerce") >= pd.to_datetime(${JSON.stringify(filter.min)})]`);
      if (filter.max) lines.push(`view = view[pd.to_datetime(view[${name}], errors="coerce") <= pd.to_datetime(${JSON.stringify(filter.max)})]`);
    } else if (filter.kind === "empty") {
      lines.push(`view = view[view[${name}].isna() | view[${name}].astype("string").str.strip().eq("")]`);
    } else if (filter.kind === "not_empty") {
      lines.push(`view = view[~(view[${name}].isna() | view[${name}].astype("string").str.strip().eq(""))]`);
    } else if (filter.value) {
      const value = JSON.stringify(String(filter.value).toLowerCase());
      if (filter.mode === "equals") lines.push(`view = view[view[${name}].astype("string").str.lower().eq(${value})]`);
      else if (filter.mode === "not_equals") lines.push(`view = view[view[${name}].astype("string").str.lower().ne(${value}).fillna(True)]`);
      else if (filter.mode === "starts") lines.push(`view = view[view[${name}].astype("string").str.lower().str.startswith(${value}, na=False)]`);
      else if (filter.mode === "not_contains") lines.push(`view = view[~view[${name}].astype("string").str.lower().str.contains(${value}, na=False, regex=False)]`);
      else lines.push(`view = view[view[${name}].astype("string").str.lower().str.contains(${value}, na=False, regex=False)]`);
    }
  }
  if (state.globalSearch) {
    const search = JSON.stringify(String(state.globalSearch).toLowerCase());
    lines.push(`mask = view.astype("string").apply(lambda col: col.str.lower().str.contains(${search}, na=False, regex=False)).any(axis=1)`);
    lines.push("view = view[mask]");
  }
  if ((state.sorts || []).length) {
    const by = (state.sorts || []).map((sort) => getViewerColumn(payload, sort.id)?.source_name).filter(Boolean);
    const ascending = (state.sorts || []).filter((sort) => getViewerColumn(payload, sort.id)).map((sort) => sort.direction !== "desc");
    lines.push(`view = view.sort_values(${JSON.stringify(by)}, ascending=${JSON.stringify(ascending)})`);
  }
  const hidden = new Set(state.hiddenColumnIds || []);
  const visible = orderedViewerColumns(payload, state)
    .filter((column) => !hidden.has(column.id))
    .map((column) => column.source_name);
  if (visible.length) lines.push(`view = view[${JSON.stringify(visible)}]`);
  const renameEntries = Object.entries(state.columnRenames || {})
    .map(([id, name]) => {
      const column = getViewerColumn(payload, id);
      const requested = String(name || "").trim();
      return column && requested && requested !== originalColumnName(column)
        ? [column.source_name, requested]
        : null;
    })
    .filter(Boolean);
  if (renameEntries.length) lines.push(`view = view.rename(columns=${JSON.stringify(Object.fromEntries(renameEntries))})`);
  return lines.join("\n");
}

function renderViewerHeaderCell(column, state, setViewerState) {
  const cell = th("");
  const sortIndex = (state.sorts || []).findIndex((sort) => sort.id === column.id);
  const sort = sortIndex >= 0 ? state.sorts[sortIndex] : null;
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-table-header-cell";
  const nameWrap = document.createElement("div");
  nameWrap.className = "stateframe-web-table-header-name-row";
  const name = textSpan(effectiveColumnName(column, state), "stateframe-web-table-header-name");
  const renameBadge = renderRenameBadge(column, state);
  nameWrap.append(name);
  if (renameBadge) nameWrap.appendChild(renameBadge);
  const dtype = textSpan(column.dtype || column.semantic_type || "", "stateframe-web-table-header-type");
  wrap.append(nameWrap, dtype);
  if (sort) {
    wrap.appendChild(textSpan(`${sort.direction === "desc" ? "Down" : "Up"} ${sortIndex + 1}`, "stateframe-web-sort-badge"));
  }
  if ((state.pinnedColumnIds || []).includes(column.id)) {
    wrap.appendChild(textSpan("Pinned", "stateframe-web-pin-badge"));
  }
  cell.replaceChildren(wrap);
  cell.addEventListener("click", (event) => setViewerState({
    selectedColumnId: column.id,
    sorts: nextSorts(state.sorts, column.id, { append: event.shiftKey || event.ctrlKey || event.metaKey }),
  }));
  cell.addEventListener("dblclick", () => setViewerState({
    pinnedColumnIds: toggleArrayValue(state.pinnedColumnIds, column.id),
  }));
  cell.title = "Click to sort. Shift/Ctrl/Cmd-click to add a sort layer. Double-click to pin.";
  return cell;
}

function renderViewerColumns(payload, state, setViewerState) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-viewer-columns";
  panel.dataset.scrollKey = "viewer-columns";
  const header = document.createElement("div");
  header.className = "stateframe-web-panel-header";
  header.textContent = "Column Summary";
  const search = filterInput("Search columns", state.columnSearch || "", (value) => setViewerState({ columnSearch: value }), "viewer-column-search");
  search.classList.add("stateframe-web-column-search");
  const sort = document.createElement("select");
  sort.className = "stateframe-web-select";
  for (const [value, label] of [
    ["original", "Original order"],
    ["name_asc", "Name A-Z"],
    ["name_desc", "Name Z-A"],
    ["type_asc", "Type A-Z"],
    ["type_desc", "Type Z-A"],
    ["missing_desc", "Most missing"],
    ["unique_desc", "Most unique"],
    ["issues_desc", "Most issues"],
  ]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    sort.appendChild(option);
  }
  sort.value = state.columnSort || "original";
  sort.addEventListener("change", () => setViewerState({ columnSort: sort.value }));
  const controls = document.createElement("div");
  controls.className = "stateframe-web-column-panel-controls";
  controls.append(search, sort);
  panel.append(header, controls);

  const ordered = summaryViewerColumns(payload, state);
  const hidden = new Set(state.hiddenColumnIds || []);
  const pinned = new Set(state.pinnedColumnIds || []);
  const list = document.createElement("div");
  list.className = "stateframe-web-viewer-column-list";
  if (!ordered.length) {
    list.appendChild(empty("No columns match this search."));
  }
  ordered.forEach((column, index) => {
    const row = document.createElement("div");
    row.className = "stateframe-web-viewer-column";
    if (column.id === state.selectedColumnId) row.classList.add("is-selected");
    if (hidden.has(column.id)) row.classList.add("is-hidden");
    if (pinned.has(column.id)) row.classList.add("is-pinned");
    row.addEventListener("dblclick", () => setViewerState({
      selectedColumnId: column.id,
      collapsedPanels: { ...state.collapsedPanels, columns: true },
    }));
    const main = document.createElement("button");
    main.type = "button";
    main.className = "stateframe-web-column-summary-main";
    main.addEventListener("click", () => setViewerState({ selectedColumnId: column.id }));
    const topLine = document.createElement("div");
    topLine.className = "stateframe-web-column-summary-top";
    const nameWrap = document.createElement("div");
    nameWrap.className = "stateframe-web-column-name-row";
    nameWrap.appendChild(textSpan(effectiveColumnName(column, state), "stateframe-web-column-name"));
    const renameBadge = renderRenameBadge(column, state);
    if (renameBadge) nameWrap.appendChild(renameBadge);
    topLine.append(nameWrap, textSpan(column.semantic_type || column.dtype || "unknown", "stateframe-web-column-type"));
    const statLine = document.createElement("div");
    statLine.className = "stateframe-web-column-summary-stats";
    statLine.append(
      textSpan(`Missing ${formatPercent(column.missing_ratio) || "0.0%"}`, "stateframe-web-column-stat"),
      textSpan(`Unique ${formatInt(column.distinct_count)}`, "stateframe-web-column-stat"),
    );
    main.append(topLine, renderColumnMissingBar(column), renderColumnSparkline(column), statLine);
    const actualIndex = orderedViewerColumns(payload, state).findIndex((item) => item.id === column.id);
    const originalSort = (state.columnSort || "original") === "original" && !(state.columnSearch || "").trim();
    const actions = document.createElement("div");
    actions.className = "stateframe-web-column-actions";
    actions.append(
      tinyButton(pinned.has(column.id) ? "Unpin" : "Pin", () => {
        const nextPinned = pinned.has(column.id)
          ? state.pinnedColumnIds.filter((id) => id !== column.id)
          : [...state.pinnedColumnIds, column.id];
        setViewerState({ pinnedColumnIds: nextPinned });
      }, hidden.has(column.id), pinned.has(column.id) ? "Unpin column" : "Pin column"),
      tinyButton("Up", () => setViewerState({ columnOrder: moveId(state.columnOrder, column.id, -1) }), !originalSort || actualIndex <= 0, "Move column up"),
      tinyButton("Down", () => setViewerState({ columnOrder: moveId(state.columnOrder, column.id, 1) }), !originalSort || actualIndex < 0 || actualIndex === orderedViewerColumns(payload, state).length - 1, "Move column down"),
      tinyButton(hidden.has(column.id) ? "\u21e4" : "\u21e5", () => {
        const nextPinned = state.pinnedColumnIds.filter((id) => id !== column.id);
        const next = hidden.has(column.id)
          ? state.hiddenColumnIds.filter((id) => id !== column.id)
          : [...state.hiddenColumnIds, column.id];
        setViewerState({ hiddenColumnIds: next, pinnedColumnIds: nextPinned });
      }, false, hidden.has(column.id) ? "Load column back into view" : "Offload column from view", true),
    );
    row.append(main, actions);
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
  const pinnedColumns = new Set(state.pinnedColumnIds || []);
  const pinnedVisibleColumns = visibleColumns.filter((column) => pinnedColumns.has(column.id));
  const pinnedOffsets = new Map();
  let pinnedLeft = state.showIndex ? 64 : 0;
  for (const column of pinnedVisibleColumns) {
    pinnedOffsets.set(column.id, pinnedLeft);
    pinnedLeft += viewerColumnWidth(state, column);
  }
  const colgroup = document.createElement("colgroup");
  if (state.showIndex) {
    const indexCol = document.createElement("col");
    indexCol.style.width = "64px";
    colgroup.appendChild(indexCol);
  }
  for (const column of visibleColumns) {
    const col = document.createElement("col");
    col.style.width = `${viewerColumnWidth(state, column)}px`;
    colgroup.appendChild(col);
  }
  table.appendChild(colgroup);
  const thead = document.createElement("thead");
  const header = document.createElement("tr");
  if (state.showIndex) {
    const indexHeader = th("#");
    indexHeader.classList.add("is-index-column");
    header.appendChild(indexHeader);
  }
  for (const column of visibleColumns) {
    const cell = renderViewerHeaderCell(column, state, setViewerState);
    applyViewerColumnSizing(cell, state, column);
    if (pinnedColumns.has(column.id)) applyPinnedColumnCell(cell, pinnedOffsets.get(column.id), true);
    header.appendChild(cell);
  }
  thead.appendChild(header);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  const visibleCellWidth = Math.max(1, visibleColumns.length + (state.showIndex ? 1 : 0));
  const limit = Math.max(40, Math.min(500, Math.floor(VIEWER_GRID_CELL_BUDGET / visibleCellWidth)));
  const activeVirtualIndex = activeMatch?.virtualIndex ?? 0;
  const start = activeVirtualIndex >= limit ? Math.max(0, activeVirtualIndex - 25) : 0;
  const pinnedRowSet = new Set(state.pinnedRowIndices || []);
  const matchedPinnedRows = (state.pinnedRowIndices || []).filter((rowIndex) => computed.indices.includes(rowIndex));
  const bodyRows = computed.indices
    .slice(start, start + limit)
    .filter((rowIndex) => !pinnedRowSet.has(rowIndex));
  const rows = [...matchedPinnedRows, ...bodyRows];
  const bodyFragment = document.createDocumentFragment();
  let pinnedRowOrder = 0;
  for (const rowIndex of rows) {
    const tr = document.createElement("tr");
    const isPinnedRow = pinnedRowSet.has(rowIndex);
    if (isPinnedRow) tr.classList.add("is-pinned-row");
    if (state.showIndex) {
      const indexCell = td(payload.index?.[rowIndex] ?? rowIndex);
      indexCell.classList.add("is-index-column");
      if (isPinnedRow) applyPinnedRowCell(indexCell, pinnedRowOrder);
      indexCell.title = isPinnedRow ? "Pinned row. Double-click to unpin." : "Double-click to pin this row.";
      indexCell.addEventListener("dblclick", () => setViewerState({
        pinnedRowIndices: toggleNumberValue(state.pinnedRowIndices, rowIndex),
      }));
      tr.appendChild(indexCell);
    }
    for (const column of visibleColumns) {
      const value = valueFor(payload, rowIndex, column);
      const cell = td(value);
      applyViewerColumnSizing(cell, state, column);
      if (pinnedColumns.has(column.id)) applyPinnedColumnCell(cell, pinnedOffsets.get(column.id), false);
      if (isPinnedRow) applyPinnedRowCell(cell, pinnedRowOrder);
      cell.title = String(value ?? "");
      cell.addEventListener("click", () => setViewerState({
        selectedCell: { rowIndex, columnId: column.id },
        selectedColumnId: column.id,
      }));
      cell.addEventListener("dblclick", () => copyTextToClipboard(String(value ?? ""), null));
      if (searchNeedle && cellMatches(value, searchNeedle)) {
        cell.classList.add("is-search-match");
      }
      if (
        state.selectedCell
        && state.selectedCell.rowIndex === rowIndex
        && state.selectedCell.columnId === column.id
      ) {
        cell.classList.add("is-selected-cell");
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
    bodyFragment.appendChild(tr);
    if (isPinnedRow) pinnedRowOrder += 1;
  }
  tbody.appendChild(bodyFragment);
  table.appendChild(tbody);
  wrap.appendChild(table);
  if (computed.indices.length > limit) {
    const note = document.createElement("div");
    note.className = "stateframe-web-grid-note";
    const end = Math.min(computed.indices.length, start + limit);
    note.textContent = `Showing rows ${formatInt(start + 1)}-${formatInt(end)} of ${formatInt(computed.indices.length)} matched preview rows across ${formatInt(visibleColumns.length)} visible columns. Save branch still applies the full viewer state in Python.`;
    wrap.appendChild(note);
  }
  return wrap;
}

function renderViewerInspector(payload, state, column, setViewerState, sendCommand, computed) {
  const inspector = document.createElement("aside");
  inspector.className = "stateframe-web-viewer-inspector";
  inspector.dataset.scrollKey = "viewer-inspector";
  if (!column) {
    inspector.appendChild(empty("Select a column."));
    return inspector;
  }

  const title = renderColumnRenameEditor(column, state, setViewerState);
  const meta = document.createElement("div");
  meta.className = "stateframe-web-viewer-meta";
  const metaParts = [`${column.semantic_type || "unknown"} / ${column.dtype || ""}`];
  if (columnIsRenamed(column, state)) metaParts.push(`source ${originalColumnName(column)}`);
  meta.textContent = metaParts.join(" / ");
  inspector.append(title, meta);

  inspector.appendChild(renderViewerStats(column));
  const selectedCellPanel = renderSelectedCellPanel(payload, state, column, setViewerState);
  if (selectedCellPanel) inspector.appendChild(section("Selected Cell", selectedCellPanel));
  const selectedRowSnapshot = renderSelectedRowSnapshot(payload, state, column);
  if (selectedRowSnapshot) inspector.appendChild(section("Row Snapshot", selectedRowSnapshot));
  const selectedValueOverview = renderSelectedValueOverview(payload, state, column, setViewerState, sendCommand, computed);
  if (selectedValueOverview) inspector.appendChild(section("Value Overview", selectedValueOverview));

  const actions = document.createElement("div");
  actions.className = "stateframe-web-action-row";
  actions.append(
    button("Sort Asc", () => setViewerState({ sorts: [{ id: column.id, direction: "asc" }] })),
    button("Sort Desc", () => setViewerState({ sorts: [{ id: column.id, direction: "desc" }] })),
    button("Add Asc", () => setViewerState({ sorts: nextSorts(state.sorts, column.id, { append: true, direction: "asc" }) })),
    button("Add Desc", () => setViewerState({ sorts: nextSorts(state.sorts, column.id, { append: true, direction: "desc" }) })),
  );
  inspector.appendChild(actions);

  inspector.appendChild(section("Filter", renderViewerFilter(column, state, setViewerState)));
  inspector.appendChild(section("Visualize", renderViewerPlotControls(column, state, sendCommand)));
  if (column.histogram) inspector.appendChild(section("Spread", renderHistogram(column.histogram, column, state, setViewerState)));
  if (column.binary_profile) {
    inspector.appendChild(section("Binary Flag", keyValueList({
      Kind: column.binary_profile.kind,
      Confidence: formatPercent(column.binary_profile.confidence),
      Nulls: column.binary_profile.null_policy,
      Ambiguous: column.binary_profile.ambiguous ? "yes" : "no",
    })));
  }
  if (column.datetime_range) inspector.appendChild(section("Time Range", keyValueList(column.datetime_range)));
  if (column.top_values?.length) inspector.appendChild(section("Top Values", renderTopValues(column, state, setViewerState)));
  if (column.issues?.length) inspector.appendChild(section("Issues", renderBullets(column.issues.map((issue) => issue.title))));
  if (column.insights?.length) inspector.appendChild(section("Insights", renderBullets(column.insights.map((insight) => insight.message))));
  if (column.metrics && Object.keys(column.metrics).length) inspector.appendChild(section("Metrics", keyValueList(column.metrics)));
  if (column.recommendations?.length) inspector.appendChild(section("Recommendations", renderColumnRecommendations(column.recommendations)));
  return inspector;
}

function renderColumnRenameEditor(column, state, setViewerState) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-column-name-editor";
  const row = document.createElement("div");
  row.className = "stateframe-web-column-name-editor-row";
  const input = document.createElement("input");
  input.className = "stateframe-web-input stateframe-web-column-name-input";
  input.value = effectiveColumnName(column, state);
  input.placeholder = originalColumnName(column);
  input.dataset.focusKey = `rename-${column.id}`;
  input.setAttribute("aria-label", `Rename column ${originalColumnName(column)}`);
  input.title = `Rename ${originalColumnName(column)} for this branch draft`;
  input.addEventListener("input", () => setColumnRename(column, input.value, state, setViewerState));
  row.appendChild(input);
  const renameBadge = renderRenameBadge(column, state);
  if (renameBadge) row.appendChild(renameBadge);
  if (columnIsRenamed(column, state)) {
    row.appendChild(tinyButton("Revert", () => clearColumnRename(column, state, setViewerState), false, `Revert to ${originalColumnName(column)}`));
  }
  wrap.appendChild(row);
  return wrap;
}

function renderViewerPlotControls(column, state, sendCommand) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-plot-controls";
  if (!column) return empty("Select a column to build a plot leaf.");
  const kind = plotKindForColumn(column);
  const label = effectiveColumnName(column, state);
  const save = button("Save Plot Leaf", () => sendCommand("save_plot_leaf", {
    plotKind: kind,
    columnName: column.source_name,
    title: `${label} plot`,
    viewerState: state,
  }));
  const auto = button("Auto Plot", () => sendCommand("save_plot_leaf", {
    plotKind: "column",
    columnName: column.source_name,
    title: `${label} auto plot`,
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

function renderSelectedCellPanel(payload, state, column, setViewerState) {
  const cell = state.selectedCell;
  if (!cell || cell.columnId !== column.id) return null;
  const value = valueFor(payload, cell.rowIndex, column);
  const panel = document.createElement("div");
  panel.className = "stateframe-web-selected-cell-panel";
  panel.appendChild(keyValueList({
    Row: payload.index?.[cell.rowIndex] ?? cell.rowIndex,
    Value: formatCell(value),
  }));
  panel.appendChild(inlineControls(
    button("Only This", () => setColumnFilter(column.id, valueFilterForColumn(column, value), state, setViewerState)),
    button("Exclude This", () => setColumnFilter(column.id, valueFilterForColumn(column, value, { exclude: true }), state, setViewerState)),
    button(
      (state.pinnedRowIndices || []).map(Number).includes(Number(cell.rowIndex)) ? "Unpin Row" : "Pin Row",
      () => setViewerState({ pinnedRowIndices: toggleNumberValue(state.pinnedRowIndices, cell.rowIndex) }),
    ),
    button("Copy", (event) => copyTextToClipboard(String(value ?? ""), event.currentTarget)),
  ));
  return panel;
}

function renderSelectedRowSnapshot(payload, state, column) {
  const cell = state.selectedCell;
  if (!cell || cell.columnId !== column.id) return null;
  const visibleColumns = visibleViewerColumns(payload, state);
  const shownColumns = visibleColumns.slice(0, 12);
  const panel = document.createElement("div");
  panel.className = "stateframe-web-row-snapshot";
  panel.appendChild(renderRowSnapshotValues(payload, cell.rowIndex, shownColumns, state));
  if (visibleColumns.length > shownColumns.length) {
    const note = document.createElement("div");
    note.className = "stateframe-web-row-snapshot-note";
    note.textContent = `${formatInt(visibleColumns.length - shownColumns.length)} more visible columns hidden in this snapshot.`;
    panel.appendChild(note);
  }
  panel.appendChild(inlineControls(
    button("Copy Row", (event) => copyTextToClipboard(JSON.stringify(rowObjectForIndex(payload, cell.rowIndex, state), null, 2), event.currentTarget)),
  ));
  return panel;
}

function renderRowSnapshotValues(payload, rowIndex, columns, state = null) {
  const list = document.createElement("div");
  list.className = "stateframe-web-row-snapshot-list";
  for (const column of columns) {
    const label = effectiveColumnName(column, state);
    const value = formatCell(valueFor(payload, rowIndex, column));
    if (value === "") continue;
    const item = document.createElement("div");
    item.className = "stateframe-web-row-snapshot-item";
    const key = textSpan(label, "stateframe-web-row-snapshot-key");
    key.title = label;
    item.append(
      key,
      textSpan(value, "stateframe-web-row-snapshot-value"),
    );
    list.appendChild(item);
  }
  if (!list.childElementCount) list.appendChild(empty("No visible row values."));
  return list;
}

function renderSelectedValueOverview(payload, state, column, setViewerState, sendCommand, computed) {
  const cell = state.selectedCell;
  if (!cell || cell.columnId !== column.id) return null;
  const value = valueFor(payload, cell.rowIndex, column);
  const loadedRows = payload.rows || [];
  const loadedMatches = selectedValueRows(payload, column, value);
  const currentRows = computed?.indices || [];
  const currentMatches = currentRows.filter((rowIndex) => valueMatchesForColumn(column, valueFor(payload, rowIndex, column), value));
  const panel = document.createElement("div");
  panel.className = "stateframe-web-value-overview";

  const stats = document.createElement("div");
  stats.className = "stateframe-web-value-overview-stats";
  stats.append(
    valueOverviewStat("Current view", formatInt(currentMatches.length), `${formatPercent(safeRatio(currentMatches.length, currentRows.length)) || "0.0%"} of visible rows`),
    valueOverviewStat("Loaded preview", formatInt(loadedMatches.length), `${formatPercent(safeRatio(loadedMatches.length, loadedRows.length)) || "0.0%"} of loaded rows`),
    valueOverviewStat("Selected row", formatCell(payload.index?.[cell.rowIndex] ?? cell.rowIndex), effectiveColumnName(column, state)),
  );
  panel.appendChild(stats);

  const profile = selectedValueProfile(payload, state, column, loadedMatches);
  if (profile.length) {
    const profileList = document.createElement("div");
    profileList.className = "stateframe-web-value-profile";
    for (const item of profile) {
      const row = document.createElement("div");
      row.className = "stateframe-web-value-profile-row";
      row.title = item.title || "";
      row.append(
        textSpan(item.label, "stateframe-web-value-profile-label"),
        textSpan(item.value, "stateframe-web-value-profile-value"),
        textSpan(item.signal || "", `stateframe-web-value-profile-signal is-${item.tone || "neutral"}`),
        textSpan(item.detail, "stateframe-web-value-profile-detail"),
      );
      profileList.appendChild(row);
    }
    panel.appendChild(profileList);
  } else {
    panel.appendChild(empty("No comparable rows are loaded for this value."));
  }

  const overview = selectedValueOverviewPayload({
    payload,
    state,
    column,
    cell,
    value,
    currentMatches,
    currentRows,
    loadedMatches,
    loadedRows,
    profile,
  });
  panel.appendChild(inlineControls(
    button("Only This Value", () => setColumnFilter(column.id, valueFilterForColumn(column, value), state, setViewerState)),
    button("Exclude Value", () => setColumnFilter(column.id, valueFilterForColumn(column, value, { exclude: true }), state, setViewerState)),
    button("Save Overview Leaf", () => sendCommand("save_value_overview_leaf", {
      title: `${overview.label}: ${overview.formatted_value}`,
      overview,
      viewerState: state,
    })),
  ));
  return panel;
}

function selectedValueOverviewPayload({
  payload,
  state,
  column,
  cell,
  value,
  currentMatches,
  currentRows,
  loadedMatches,
  loadedRows,
  profile,
}) {
  return {
    kind: "selected_value_overview",
    column: originalColumnName(column),
    column_id: column.id,
    label: effectiveColumnName(column, state),
    value,
    formatted_value: formatCell(value),
    row_index: cell.rowIndex,
    selected_row_label: formatCell(payload.index?.[cell.rowIndex] ?? cell.rowIndex),
    current_match_count: currentMatches.length,
    current_row_count: currentRows.length,
    current_match_ratio: safeRatio(currentMatches.length, currentRows.length),
    loaded_match_count: loadedMatches.length,
    loaded_row_count: loadedRows.length,
    loaded_match_ratio: safeRatio(loadedMatches.length, loadedRows.length),
    preview_truncated: Boolean(payload.view?.truncated),
    profile: profile.map((item) => ({
      label: item.label,
      value: item.value,
      signal: item.signal || "",
      tone: item.tone || "neutral",
      detail: item.detail,
      score: item.score,
      title: item.title || "",
    })),
  };
}

function renderViewerFilter(column, state, setViewerState) {
  const filter = state.filters?.[column.id] || {};
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-filter";
  if (isNumericColumn(column)) {
    wrap.appendChild(renderNumericFilter(column, filter, state, setViewerState));
  } else if (isDatetimeColumn(column)) {
    const min = filterInput("Start", filter.min ?? "", (value) => setColumnFilter(column.id, { ...filter, kind: "datetime", min: value }, state, setViewerState), `filter-${column.id}-start`);
    const max = filterInput("End", filter.max ?? "", (value) => setColumnFilter(column.id, { ...filter, kind: "datetime", max: value }, state, setViewerState), `filter-${column.id}-end`);
    wrap.append(min, max);
  } else {
    const mode = document.createElement("select");
    mode.className = "stateframe-web-select";
    for (const [value, label] of [
      ["contains", "contains"],
      ["not_contains", "does not contain"],
      ["equals", "equals"],
      ["not_equals", "not equal"],
      ["starts", "starts with"],
    ]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      mode.appendChild(option);
    }
    mode.value = filter.mode || "contains";
    mode.addEventListener("change", () => setColumnFilter(column.id, { ...filter, kind: "text", mode: mode.value }, state, setViewerState));
    const text = filterInput("Value", filter.value ?? "", (value) => setColumnFilter(column.id, { ...filter, kind: "text", mode: mode.value, value }, state, setViewerState), `filter-${column.id}-value`);
    wrap.append(mode, text);
  }
  wrap.append(
    inlineControls(
      button("Empty", () => setColumnFilter(column.id, { kind: "empty" }, state, setViewerState)),
      button("Not Empty", () => setColumnFilter(column.id, { kind: "not_empty" }, state, setViewerState)),
      button("Clear Filter", () => clearColumnFilter(column.id, state, setViewerState)),
    ),
  );
  return wrap;
}

function renderNumericFilter(column, filter, state, setViewerState) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-numeric-filter";
  const mode = filter.mode || "between";
  const modeSelect = document.createElement("select");
  modeSelect.className = "stateframe-web-select";
  const choices = [
    ["between", "Between"],
    ["outside", "Outside range"],
    ["eq", "Equals"],
    ["neq", "Not equal"],
    ["gt", "Greater than"],
    ["gte", "At least"],
    ["lt", "Less than"],
    ["lte", "At most"],
  ];
  for (const [value, label] of choices) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    modeSelect.appendChild(option);
  }
  modeSelect.value = mode;
  modeSelect.addEventListener("change", () => {
    const nextMode = modeSelect.value;
    if (["between", "outside"].includes(nextMode)) {
      setColumnFilter(column.id, {
        kind: "numeric",
        mode: nextMode,
        min: filter.min ?? "",
        max: filter.max ?? "",
      }, state, setViewerState);
      return;
    }
    setColumnFilter(column.id, {
      kind: "numeric",
      mode: nextMode,
      value: filter.value ?? filter.min ?? filter.max ?? "",
    }, state, setViewerState);
  });
  wrap.appendChild(modeSelect);
  if (["between", "outside"].includes(mode)) {
    const min = filterInput("Min", filter.min ?? "", (value) => setColumnFilter(column.id, { kind: "numeric", mode, min: value, max: filter.max ?? "" }, state, setViewerState), `filter-${column.id}-min`);
    const max = filterInput("Max", filter.max ?? "", (value) => setColumnFilter(column.id, { kind: "numeric", mode, min: filter.min ?? "", max: value }, state, setViewerState), `filter-${column.id}-max`);
    wrap.append(min, max);
  } else {
    const value = filterInput("Value", filter.value ?? "", (nextValue) => setColumnFilter(column.id, { kind: "numeric", mode, value: nextValue }, state, setViewerState), `filter-${column.id}-value`);
    wrap.appendChild(value);
  }
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

function renderHistogram(histogram, column = null, state = null, setViewerState = null) {
  const chart = document.createElement("div");
  chart.className = "stateframe-web-histogram";
  const interactive = Boolean(column && state && setViewerState && isNumericColumn(column));
  const activeFilter = state?.filters?.[column?.id] || {};
  for (const bin of histogram.bins || []) {
    const bar = document.createElement(interactive ? "button" : "div");
    bar.className = "stateframe-web-histogram-bar";
    const label = `${formatNumber(bin.lower)} to ${formatNumber(bin.upper)}: ${formatInt(bin.count)}`;
    if (interactive) {
      bar.type = "button";
      bar.classList.add("is-clickable");
      if (histogramBinMatchesFilter(bin, activeFilter)) bar.classList.add("is-active");
      bar.setAttribute("aria-label", `Filter ${effectiveColumnName(column, state)} from ${formatNumber(bin.lower)} to ${formatNumber(bin.upper)}`);
      bar.addEventListener("click", () => setColumnFilter(column.id, {
        kind: "numeric",
        mode: "between",
        min: String(bin.lower),
        max: String(bin.upper),
      }, state, setViewerState));
    }
    const height = histogram.max_count ? Math.max(4, (bin.count / histogram.max_count) * 72) : 4;
    bar.style.height = `${height}px`;
    bar.title = `${label}${interactive ? ". Click to filter this range." : ""}`;
    chart.appendChild(bar);
  }
  return chart;
}

function histogramBinMatchesFilter(bin, filter) {
  if (!filter || filter.kind !== "numeric" || (filter.mode || "between") !== "between") return false;
  return numericFilterInput(filter.min) === numericFilterInput(bin.lower)
    && numericFilterInput(filter.max) === numericFilterInput(bin.upper);
}

function renderTopValues(column, state, setViewerState) {
  const topValues = column.top_values || [];
  const list = document.createElement("div");
  list.className = "stateframe-web-top-values";
  const activeFilter = state.filters?.[column.id] || {};
  for (const item of topValues.slice(0, 12)) {
    const row = document.createElement("div");
    row.className = "stateframe-web-top-value";
    const filter = topValueFilter(column, item.value);
    const excludeFilter = valueFilterForColumn(column, item.value, { exclude: true });
    if (filtersEqual(activeFilter, filter)) row.classList.add("is-active");
    if (filtersEqual(activeFilter, excludeFilter)) row.classList.add("is-excluded");
    const value = document.createElement("span");
    value.className = "stateframe-web-top-value-name";
    value.textContent = formatCell(item.value);
    const count = document.createElement("span");
    count.className = "stateframe-web-top-value-count";
    count.textContent = `${formatInt(item.count)} ${item.ratio !== undefined ? formatPercent(item.ratio) : ""}`;
    const only = tinyButton("Only", () => setColumnFilter(column.id, filter, state, setViewerState), false, `Filter to ${formatCell(item.value)}`);
    const exclude = tinyButton("Exclude", () => setColumnFilter(column.id, excludeFilter, state, setViewerState), false, `Exclude ${formatCell(item.value)}`);
    row.append(value, count, only, exclude);
    list.appendChild(row);
  }
  return list;
}

function topValueFilter(column, value) {
  return valueFilterForColumn(column, value);
}

function valueFilterForColumn(column, value, options = {}) {
  if (value === null || value === undefined || value === "") {
    return options.exclude ? { kind: "not_empty" } : { kind: "empty" };
  }
  if (isNumericColumn(column)) {
    return { kind: "numeric", mode: options.exclude ? "neq" : "eq", value: String(value) };
  }
  return { kind: "text", mode: options.exclude ? "not_equals" : "equals", value: String(value) };
}

function selectedValueRows(payload, column, value) {
  const cache = viewerPayloadCache(payload);
  const cacheKey = `${column.id}\u0001${comparableValueKey(column, value)}`;
  const cached = cache.selectedValueRows.get(cacheKey);
  if (cached) return cached;
  const rows = payload.rows || [];
  const matches = [];
  for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
    if (valueMatchesForColumn(column, valueFor(payload, rowIndex, column), value)) {
      matches.push(rowIndex);
    }
  }
  cache.selectedValueRows.set(cacheKey, matches);
  return matches;
}

function selectedValueProfile(payload, state, selectedColumn, rowIndices) {
  const cohortRows = rowIndices.slice(0, VALUE_OVERVIEW_ROW_LIMIT);
  if (!cohortRows.length) return [];
  const restRows = complementRows(payload, rowIndices).slice(0, VALUE_OVERVIEW_ROW_LIMIT);
  return visibleViewerColumns(payload, state)
    .filter((column) => column.id !== selectedColumn.id)
    .map((column) => profileColumnForRows(payload, state, column, cohortRows, restRows))
    .filter(Boolean)
    .sort((left, right) => right.score - left.score)
    .slice(0, VALUE_OVERVIEW_PROFILE_LIMIT);
}

function profileColumnForRows(payload, state, column, rowIndices, restRows) {
  if (isNumericColumn(column)) return numericProfileColumnForRows(payload, state, column, rowIndices, restRows);
  if (isDatetimeColumn(column)) return datetimeProfileColumnForRows(payload, state, column, rowIndices, restRows);
  return categoricalProfileColumnForRows(payload, state, column, rowIndices, restRows);
}

function categoricalProfileColumnForRows(payload, state, column, rowIndices, restRows) {
  const counts = valueCountsForRows(payload, column, rowIndices);
  if (!counts.length) return null;
  const top = counts[0];
  const ratio = safeRatio(top.count, rowIndices.length);
  const restCount = valueCountAcrossRows(payload, column, restRows, top.value);
  const restRatio = safeRatio(restCount, restRows.length);
  const lift = ratio - restRatio;
  return {
    label: effectiveColumnName(column, state),
    value: formatCell(top.value),
    signal: formatSignedPercentPoints(lift),
    tone: deltaTone(lift),
    detail: `${formatInt(top.count)} rows (${formatPercent(ratio) || "0.0%"}) / rest ${formatPercent(restRatio) || "0.0%"}`,
    score: ratio + Math.abs(lift),
    title: `Top value in selected cohort for ${effectiveColumnName(column, state)}`,
  };
}

function numericProfileColumnForRows(payload, state, column, rowIndices, restRows) {
  const stats = numericStatsForRows(payload, column, rowIndices);
  if (!stats.count) return null;
  const restStats = numericStatsForRows(payload, column, restRows);
  const delta = Number.isFinite(restStats.average) ? stats.average - restStats.average : 0;
  const detail = Number.isFinite(restStats.average)
    ? `rest avg ${formatNumber(restStats.average)}`
    : `${formatInt(stats.count)} numeric rows`;
  return {
    label: effectiveColumnName(column, state),
    value: `avg ${formatNumber(stats.average)}`,
    signal: Number.isFinite(restStats.average) ? signedFormatNumber(delta) : "",
    tone: deltaTone(delta),
    detail,
    score: 0.35 + Math.min(2, Math.abs(delta) / Math.max(1, Math.abs(restStats.average || 0))),
    title: `Numeric average in selected cohort for ${effectiveColumnName(column, state)}`,
  };
}

function datetimeProfileColumnForRows(payload, state, column, rowIndices, restRows) {
  const range = datetimeRangeForRows(payload, column, rowIndices);
  if (!range) return null;
  const restRange = datetimeRangeForRows(payload, column, restRows);
  return {
    label: effectiveColumnName(column, state),
    value: formatShortDate(range.min),
    signal: "",
    tone: "neutral",
    detail: range.min === range.max
      ? `single date${restRange ? ` / rest ${formatShortDate(restRange.min)}-${formatShortDate(restRange.max)}` : ""}`
      : `to ${formatShortDate(range.max)}${restRange ? ` / rest ${formatShortDate(restRange.min)}-${formatShortDate(restRange.max)}` : ""}`,
    score: 0.25,
    title: `Date range in selected cohort for ${effectiveColumnName(column, state)}`,
  };
}

function valueCountsForRows(payload, column, rowIndices) {
  const counts = new Map();
  for (const rowIndex of rowIndices) {
    const value = valueFor(payload, rowIndex, column);
    const key = comparableValueKey(column, value);
    const current = counts.get(key) || { value, count: 0 };
    current.count += 1;
    counts.set(key, current);
  }
  return [...counts.values()].sort((left, right) => right.count - left.count);
}

function valueCountAcrossPayload(payload, column, value) {
  let count = 0;
  for (let rowIndex = 0; rowIndex < (payload.rows || []).length; rowIndex += 1) {
    if (valueMatchesForColumn(column, valueFor(payload, rowIndex, column), value)) count += 1;
  }
  return count;
}

function valueCountAcrossRows(payload, column, rowIndices, value) {
  let count = 0;
  for (const rowIndex of rowIndices || []) {
    if (valueMatchesForColumn(column, valueFor(payload, rowIndex, column), value)) count += 1;
  }
  return count;
}

function numericValuesForRows(payload, column, rowIndices) {
  return rowIndices
    .map((rowIndex) => Number(valueFor(payload, rowIndex, column)))
    .filter((value) => Number.isFinite(value));
}

function numericStatsForRows(payload, column, rowIndices) {
  let count = 0;
  let sum = 0;
  for (const rowIndex of rowIndices || []) {
    const value = Number(valueFor(payload, rowIndex, column));
    if (!Number.isFinite(value)) continue;
    count += 1;
    sum += value;
  }
  return {
    count,
    sum,
    average: count ? sum / count : NaN,
  };
}

function numericValuesForColumn(payload, column) {
  const cache = viewerPayloadCache(payload);
  const cached = cache.numericValuesByColumn.get(column.id);
  if (cached) return cached;
  const values = [];
  for (let rowIndex = 0; rowIndex < (payload.rows || []).length; rowIndex += 1) {
    const value = Number(valueFor(payload, rowIndex, column));
    if (Number.isFinite(value)) values.push(value);
  }
  cache.numericValuesByColumn.set(column.id, values);
  return values;
}

function datetimeRangeForRows(payload, column, rowIndices) {
  let min = Infinity;
  let max = -Infinity;
  for (const rowIndex of rowIndices || []) {
    const value = new Date(valueFor(payload, rowIndex, column)).getTime();
    if (!Number.isFinite(value)) continue;
    min = Math.min(min, value);
    max = Math.max(max, value);
  }
  return Number.isFinite(min) && Number.isFinite(max) ? { min, max } : null;
}

function complementRows(payload, excludedRowIndices) {
  const excluded = new Set((excludedRowIndices || []).map((value) => Number(value)));
  const rows = payload.rows || [];
  const result = [];
  for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
    if (!excluded.has(rowIndex)) result.push(rowIndex);
  }
  return result;
}

function valueMatchesForColumn(column, left, right) {
  if (isEmptyValue(right)) return isEmptyValue(left);
  if (isNumericColumn(column)) {
    const leftNumber = Number(left);
    const rightNumber = Number(right);
    return Number.isFinite(leftNumber) && Number.isFinite(rightNumber) && leftNumber === rightNumber;
  }
  if (isDatetimeColumn(column)) {
    const leftTime = new Date(left).getTime();
    const rightTime = new Date(right).getTime();
    if (Number.isFinite(leftTime) && Number.isFinite(rightTime)) return leftTime === rightTime;
  }
  return String(left ?? "").toLowerCase() === String(right ?? "").toLowerCase();
}

function comparableValueKey(column, value) {
  if (isEmptyValue(value)) return "__empty__";
  if (isNumericColumn(column)) {
    const number = Number(value);
    return Number.isFinite(number) ? `number:${number}` : `text:${String(value).toLowerCase()}`;
  }
  if (isDatetimeColumn(column)) {
    const time = new Date(value).getTime();
    return Number.isFinite(time) ? `date:${time}` : `text:${String(value).toLowerCase()}`;
  }
  return `text:${String(value).toLowerCase()}`;
}

function valueOverviewStat(label, value, caption) {
  const item = document.createElement("div");
  item.className = "stateframe-web-value-overview-stat";
  item.append(
    textSpan(label, "stateframe-web-value-overview-label"),
    textSpan(value, "stateframe-web-value-overview-value"),
    textSpan(caption, "stateframe-web-value-overview-caption"),
  );
  return item;
}

function rowObjectForIndex(payload, rowIndex, state = null) {
  const result = {};
  for (const column of payload.columns || []) {
    result[effectiveColumnName(column, state)] = valueFor(payload, rowIndex, column);
  }
  return result;
}

function isNumericColumn(column) {
  const semantic = column.semantic_type || "";
  return semantic.includes("numeric") || ["amount", "percentage", "proportion"].includes(semantic);
}

function isDatetimeColumn(column) {
  return String(column.semantic_type || "").includes("datetime");
}

function isEmptyValue(value) {
  return value === null || value === undefined || String(value).trim() === "";
}

function safeRatio(value, total) {
  const denominator = Number(total || 0);
  if (!denominator) return 0;
  return Number(value || 0) / denominator;
}

function mean(values) {
  if (!values.length) return NaN;
  return values.reduce((total, value) => total + value, 0) / values.length;
}

function signedFormatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || Math.abs(number) < 0.0005) return "0";
  return `${number > 0 ? "+" : ""}${formatNumber(number)}`;
}

function formatSignedPercentPoints(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || Math.abs(number) < 0.0005) return "0.0 pts";
  return `${number > 0 ? "+" : ""}${(number * 100).toFixed(1)} pts`;
}

function deltaTone(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || Math.abs(number) < 0.0005) return "neutral";
  return number > 0 ? "positive" : "negative";
}

function filtersEqual(left, right) {
  const leftKeys = Object.keys(left || {}).sort();
  const rightKeys = Object.keys(right || {}).sort();
  if (leftKeys.length !== rightKeys.length) return false;
  return leftKeys.every((key, index) => key === rightKeys[index] && String(left?.[key]) === String(right?.[key]));
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
    field_options: cleanObject(state.fieldOptions || {}),
    filters: (state.filters || []).filter((filter) => filter?.column && filter?.op),
    options: cleanObject(state.options || {}),
  };
}

function visualDefinitionById(payload, kind) {
  const plotTypes = payload?.catalog?.plot_types || [];
  return plotTypes.find((item) => item.id === kind) || null;
}

function visualDefinition(payload, kind) {
  const plotTypes = payload?.catalog?.plot_types || [];
  return visualDefinitionById(payload, kind) || plotTypes[0] || { id: "histogram", fields: [], option_groups: [] };
}

function defaultFieldsForVisual(payload, definition) {
  const fields = {};
  const fieldDefs = definition.fields || [];
  const requiredFields = fieldDefs.filter((field) => field.required);
  const fieldsToFill = requiredFields.length ? requiredFields : fieldDefs.slice(0, 1);
  const used = new Set();
  for (const field of fieldsToFill) {
    if (field.multiple) {
      const columns = defaultMultipleColumnsForVisual(payload, definition, field, used);
      if (columns.length) {
        fields[field.slot] = columns;
        columns.forEach((column) => used.add(column));
      }
      continue;
    }
    const column = defaultVisualColumn(payload, definition, field, used);
    if (column) {
      fields[field.slot] = column;
      used.add(column);
    }
  }
  return fields;
}

function defaultMultipleColumnsForVisual(payload, definition, field, used = new Set()) {
  let candidates = visualCandidateColumns(payload, definition, field).filter((column) => !used.has(column.id));
  const kind = definition?.id || "";
  if (field?.slot === "dimensions" && ["correlation_heatmap", "scatter_matrix", "pca_scatter", "parallel_coordinates"].includes(kind)) {
    candidates = [...candidates].sort((left, right) => visualNumericDimensionScore(right) - visualNumericDimensionScore(left));
  }
  const limits = {
    correlation_heatmap: 8,
    association_heatmap: 12,
    scatter_matrix: 4,
    pca_scatter: 6,
    parallel_coordinates: 6,
    parallel_categories: 5,
    treemap: 3,
    sunburst: 3,
    missingness_matrix: 12,
  };
  const limit = limits[kind] || (field.slot === "path" ? 3 : 6);
  return candidates.slice(0, limit).map((column) => column.id);
}

function visualNumericDimensionScore(column) {
  const name = String(column?.source_name || column?.display_name || column?.id || "").toLowerCase();
  const semantic = String(column?.semantic_type || "").toLowerCase();
  let score = 0;
  if (["amount", "nonnegative_amount", "percentage", "proportion", "numeric"].includes(semantic)) score += 2;
  if (/(sold|list|price|amount|revenue|value|hoa|fee|concession)/.test(name)) score += 5;
  if (/(sqft|square|bed|bath|garage|lot|days|year|age|floor|living|total)/.test(name)) score += 4;
  if (/(rate|ratio|percent|score)/.test(name)) score += 3;
  if (/(\b|_)(lat|lon|lng|long|zip|postal|geo|code|id|key)(\b|_)/.test(name)) score -= 8;
  if (name === "area" || name.endsWith("_area")) score -= 5;
  return score;
}

function visualCandidateColumns(payload, definition, field) {
  const columns = payload?.columns || [];
  const kind = definition?.id || "";
  if (!columns.length) return [];
  if (field?.slot === "dimensions" && ["correlation_heatmap", "scatter_matrix", "pca_scatter", "parallel_coordinates"].includes(kind)) {
    return columns.filter(visualColumnLooksNumeric).filter((column) => !visualColumnLooksIdentifier(column));
  }
  if ((field?.slot === "dimensions" && kind === "association_heatmap") || (field?.slot === "features" && kind === "target_association")) {
    return columns
      .filter((column) => !visualColumnLooksIdentifier(column))
      .filter((column) => visualColumnLooksNumeric(column) || visualColumnLooksCategorical(column));
  }
  if (kind === "target_profile" && field?.slot === "target") {
    return columns
      .filter((column) => !visualColumnLooksIdentifier(column))
      .filter((column) => visualColumnLooksNumeric(column) || visualColumnLooksCategorical(column));
  }
  if (kind === "target_profile" && field?.slot === "feature") {
    return columns
      .filter((column) => !visualColumnLooksIdentifier(column))
      .filter((column) => visualColumnLooksNumeric(column) || visualColumnLooksCategorical(column) || visualColumnLooksDate(column));
  }
  if (kind === "target_profile" && field?.slot === "color") {
    return columns.filter(visualColumnLooksCategorical).filter((column) => !visualColumnLooksIdentifier(column));
  }
  if (field?.slot === "dimensions" && kind === "missingness_matrix") {
    return columns.filter((column) => Number(column?.missing_count || 0) > 0 || Number(column?.missing_ratio || 0) > 0);
  }
  if (field?.slot === "dimensions" && kind === "parallel_categories") {
    return columns.filter(visualColumnLooksCategorical);
  }
  if (field?.slot === "path") {
    return columns.filter(visualColumnLooksCategorical);
  }
  if (field?.slot === "locations" && kind === "choropleth") {
    return columns.filter(visualColumnLooksChoroplethLocation);
  }
  if (Array.isArray(field?.semantic) && field.semantic.length) {
    const wanted = new Set(field.semantic.map((item) => String(item).toLowerCase()));
    const matches = columns.filter((column) => wanted.has(String(column.semantic_type || "").toLowerCase()));
    if (matches.length) return matches;
  }
  return columns;
}

function defaultVisualColumn(payload, definition, field = null, used = new Set()) {
  const columns = visualCandidateColumns(payload, definition, field);
  if (!columns.length) return null;
  const available = columns.filter((column) => !used.has(column.id));
  const pool = available.length ? available : columns;
  const wanted = new Set(field?.semantic || []);
  const nameOf = (column) => String(column.source_name || column.display_name || column.id || "").toLowerCase();
  const semanticOf = (column) => String(column.semantic_type || "").toLowerCase();
  const numeric = pool.find((column) => ["numeric", "amount", "numeric-like", "percentage", "proportion", "numeric_discrete"].includes(semanticOf(column)));
  const datetime = pool.find((column) => semanticOf(column).includes("datetime"));
  const categorical = pool.find((column) => ["category", "string", "postal_code", "geographic", "binary", "nullable_binary", "boolean"].includes(semanticOf(column)));
  const latitude = pool.find((column) => /(^|_|\b)(lat|latitude)($|_|\b)/.test(nameOf(column)));
  const longitude = pool.find((column) => /(^|_|\b)(lon|lng|long|longitude)($|_|\b)/.test(nameOf(column)));
  const location = pool.find((column) => ["geographic", "postal_code"].includes(semanticOf(column)) || /(^|_|\b)(state|country|county|zip|postal|postcode)($|_|\b)/.test(nameOf(column)));
  if (wanted.size) {
    const match = pool.find((column) => wanted.has(semanticOf(column)));
    if (match) return match.id;
  }
  if (field?.slot === "lat" && latitude) return latitude.id;
  if (field?.slot === "lon" && longitude) return longitude.id;
  if (field?.slot === "locations" && location) return location.id;
  if (field?.slot === "target" && numeric) return numeric.id;
  if (field?.slot === "feature" && definition?.id === "target_profile") return categorical?.id || numeric?.id || datetime?.id || pool[0].id;
  if (field?.slot === "color" && definition?.id === "target_profile" && categorical) return categorical.id;
  if (field?.slot === "path" && categorical) return categorical.id;
  if (field?.slot === "values" && numeric) return numeric.id;
  if (["y", "y2"].includes(field?.slot) && numeric) return numeric.id;
  if (field?.slot === "x" && definition?.id === "combo") return categorical?.id || datetime?.id || numeric?.id || pool[0].id;
  if (field?.slot === "x" && definition?.id === "line" && datetime) return datetime.id;
  if (["histogram", "box", "violin", "strip", "ecdf", "scatter", "density_heatmap", "density_contour", "line", "area"].includes(definition?.id) && numeric) return numeric.id;
  if (["bar", "pie", "treemap", "sunburst", "parallel_categories"].includes(definition?.id) && categorical) return categorical.id;
  return pool[0].id || null;
}

function normalizeVisualFieldOptions(payload, definition, fields, rawOptions, legacyOptions = {}) {
  const result = {};
  const raw = rawOptions && typeof rawOptions === "object" && !Array.isArray(rawOptions) ? rawOptions : {};
  for (const field of definition.fields || []) {
    const value = fields?.[field.slot];
    if (!value || field.multiple) continue;
    const defaults = defaultFieldOptionForSlot(payload, definition, field.slot, value);
    const current = raw[field.slot] && typeof raw[field.slot] === "object" && !Array.isArray(raw[field.slot])
      ? raw[field.slot]
      : {};
    if (!Object.keys(current).length && defaults.stat && legacyOptions?.aggregation && visualSlotSupportsStat(definition.id, field.slot)) {
      current.stat = legacyOptions.aggregation;
    }
    if (!Object.keys(current).length && defaults.bucket && legacyOptions?.date_bucket && ["x", "date"].includes(field.slot)) {
      current.bucket = legacyOptions.date_bucket;
    }
    const merged = { ...defaults, ...current };
    if (Object.keys(merged).length) result[field.slot] = merged;
  }
  return result;
}

function defaultFieldOptionsForVisual(payload, definition, fields) {
  const result = {};
  for (const field of definition.fields || []) {
    const value = fields?.[field.slot];
    if (!value || field.multiple) continue;
    const defaults = defaultFieldOptionForSlot(payload, definition, field.slot, value);
    if (Object.keys(defaults).length) result[field.slot] = defaults;
  }
  return result;
}

function defaultFieldOptionForSlot(payload, definition, slot, columnId) {
  const options = {};
  const column = (payload?.columns || []).find((item) => item.id === columnId);
  const kind = definition?.id || "";
  if (["y", "y2", "values", "r", "z"].includes(slot) && visualSlotSupportsStat(kind, slot)) {
    options.stat = defaultVisualStat(column, kind, slot);
  }
  if (["x", "date"].includes(slot) && visualColumnLooksDate(column) && ["line", "area", "bar", "combo"].includes(kind)) {
    options.bucket = "none";
  }
  return options;
}

function visualSlotSupportsStat(kind, slot) {
  if (["scatter", "box", "violin", "strip", "ecdf", "histogram", "scatter_matrix", "parallel_coordinates", "parallel_categories", "pca_scatter", "qq_plot", "autocorrelation", "association_heatmap", "target_association", "target_profile"].includes(kind)) {
    return false;
  }
  if (slot === "z") return kind === "heatmap";
  if (slot === "values") return ["pie", "treemap", "sunburst", "choropleth", "calendar_heatmap"].includes(kind);
  if (slot === "r") return kind === "radar";
  if (slot === "y") return ["line", "area", "bar", "combo", "lollipop", "slope", "bump_chart", "pareto", "waterfall", "funnel"].includes(kind);
  if (slot === "y2") return kind === "combo";
  return false;
}

function defaultVisualStat(column, kind, slot) {
  if (!column) return slot === "values" && kind === "pie" ? "count" : "mean";
  const name = String(column.source_name || column.display_name || column.id || "").toLowerCase();
  const semantic = String(column.semantic_type || "").toLowerCase();
  if (kind === "pie" && slot === "values" && !visualColumnLooksNumeric(column)) return "count";
  if (semantic.includes("percentage") || semantic.includes("proportion") || name.includes("rate") || name.includes("ratio")) return "mean";
  if (["price", "score", "percent", "sqft", "square_foot", "bed", "bath"].some((token) => name.includes(token))) return "mean";
  if (["revenue", "volume", "total", "amount", "qty", "quantity", "count"].some((token) => name.includes(token))) return "sum";
  if (["amount", "nonnegative_amount"].includes(semantic)) return "sum";
  return "mean";
}

function visualColumnLooksNumeric(column) {
  const semantic = String(column?.semantic_type || "").toLowerCase();
  if (["category", "string", "postal_code", "geographic", "binary", "nullable_binary", "boolean", "constant"].includes(semantic)) return false;
  const text = `${semantic} ${column?.dtype || ""}`.toLowerCase();
  return ["numeric", "amount", "int", "float", "double", "decimal", "percentage", "proportion"].some((token) => text.includes(token));
}

function visualColumnLooksCategorical(column) {
  const semantic = String(column?.semantic_type || "").toLowerCase();
  const dtype = String(column?.dtype || "").toLowerCase();
  return ["category", "string", "postal_code", "geographic", "binary", "nullable_binary", "boolean"].includes(semantic)
    || dtype.includes("object")
    || dtype.includes("string")
    || dtype.includes("bool");
}

function visualColumnDistinctCount(column) {
  for (const value of [column?.distinct_count, column?.metrics?.distinct_count, column?.profile?.distinct_count]) {
    const number = Number(value);
    if (Number.isFinite(number)) return number;
  }
  return NaN;
}

function visualColumnMissingRatio(column) {
  for (const value of [column?.missing_ratio, column?.metrics?.missing_ratio, column?.profile?.missing_ratio]) {
    const number = Number(value);
    if (Number.isFinite(number)) return number;
  }
  return NaN;
}

function visualColumnMissingCount(column) {
  for (const value of [column?.missing_count, column?.metrics?.missing_count, column?.profile?.missing_count]) {
    const number = Number(value);
    if (Number.isFinite(number)) return number;
  }
  return NaN;
}

function visualColumnLooksIdentifier(column) {
  const name = String(column?.source_name || column?.display_name || column?.id || "").toLowerCase();
  const semantic = String(column?.semantic_type || "").toLowerCase();
  return semantic.includes("identifier") || name === "id" || name.endsWith("_id") || name.endsWith("_key") || name.includes("uuid");
}

function visualColumnLooksChoroplethLocation(column) {
  const name = String(column?.source_name || column?.display_name || column?.id || "").toLowerCase();
  return ["state", "state_code", "us_state", "country", "country_name", "country_code", "iso3", "iso_3", "iso_alpha3"].some((token) => name === token || name.includes(token));
}

function visualColumnLooksDate(column) {
  const text = `${column?.semantic_type || ""} ${column?.dtype || ""}`.toLowerCase();
  return text.includes("date") || text.includes("time");
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

function viewerPayloadCache(payload) {
  let cache = VIEWER_PAYLOAD_CACHE.get(payload);
  if (cache) return cache;
  const columns = payload.columns || [];
  const columnById = new Map();
  const columnIndexById = new Map();
  columns.forEach((column, index) => {
    columnById.set(column.id, column);
    columnIndexById.set(column.id, index);
  });
  cache = {
    columnById,
    columnIndexById,
    computedRows: null,
    numericValuesByColumn: new Map(),
    rowSearchText: null,
    selectedValueRows: new Map(),
  };
  VIEWER_PAYLOAD_CACHE.set(payload, cache);
  return cache;
}

function viewerRowsSignature(state) {
  return JSON.stringify({
    globalSearch: state.globalSearch || "",
    filters: state.filters || {},
    sorts: state.sorts || [],
    hiddenColumnIds: state.hiddenColumnIds || [],
    columnOrder: state.columnOrder || [],
  });
}

function rowSearchText(payload) {
  const cache = viewerPayloadCache(payload);
  if (cache.rowSearchText) return cache.rowSearchText;
  cache.rowSearchText = (payload.rows || []).map((row) => (
    row || []
  ).map((value) => String(value ?? "")).join("\u0001").toLowerCase());
  return cache.rowSearchText;
}

function computeViewerRows(payload, state) {
  const cache = viewerPayloadCache(payload);
  const signature = viewerRowsSignature(state);
  if (cache.computedRows?.signature === signature) {
    return cache.computedRows.value;
  }
  const indices = [];
  const query = String(state.globalSearch || "").trim().toLowerCase();
  const searchText = query ? rowSearchText(payload) : null;
  for (let rowIndex = 0; rowIndex < (payload.rows || []).length; rowIndex += 1) {
    if (query && !searchText[rowIndex]?.includes(query)) continue;
    if (!passesFilters(payload, state, rowIndex)) continue;
    indices.push(rowIndex);
  }
  const sorts = state.sorts || [];
  if (sorts.length) {
    indices.sort((a, b) => compareRows(payload, a, b, sorts));
  }
  const matchResult = query
    ? findViewerMatches(payload, visibleViewerColumns(payload, state), indices, query)
    : { matches: [], scannedRows: 0, capped: false };
  const value = {
    indices,
    matches: matchResult.matches,
    matchStats: {
      scannedRows: matchResult.scannedRows,
      capped: matchResult.capped,
      limit: VIEWER_MATCH_LIMIT,
      rowScanLimit: VIEWER_MATCH_ROW_SCAN_LIMIT,
    },
  };
  cache.computedRows = { signature, value };
  return value;
}

function findViewerMatches(payload, visibleColumns, indices, needle) {
  const matches = [];
  let scannedRows = 0;
  for (let virtualIndex = 0; virtualIndex < indices.length; virtualIndex += 1) {
    if (virtualIndex >= VIEWER_MATCH_ROW_SCAN_LIMIT) {
      return { matches, scannedRows, capped: true };
    }
    const rowIndex = indices[virtualIndex];
    scannedRows += 1;
    for (const column of visibleColumns) {
      if (cellMatches(valueFor(payload, rowIndex, column), needle)) {
        matches.push({ rowIndex, virtualIndex, columnId: column.id });
        if (matches.length >= VIEWER_MATCH_LIMIT) {
          return {
            matches,
            scannedRows,
            capped: virtualIndex < indices.length - 1,
          };
        }
      }
    }
  }
  return { matches, scannedRows, capped: false };
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
    if (filter.kind === "empty") {
      if (!(raw === null || raw === undefined || text.trim() === "")) return false;
    } else if (filter.kind === "not_empty") {
      if (raw === null || raw === undefined || text.trim() === "") return false;
    } else if (filter.kind === "numeric") {
      if (!passesNumericFilter(raw, filter)) return false;
    } else if (filter.kind === "datetime") {
      const value = new Date(raw).getTime();
      if (filter.min && !(value >= new Date(filter.min).getTime())) return false;
      if (filter.max && !(value <= new Date(filter.max).getTime())) return false;
    } else {
      const needle = String(filter.value || "").toLowerCase();
      if (!needle) continue;
      const haystack = text.toLowerCase();
      if (filter.mode === "equals" && haystack !== needle) return false;
      if (filter.mode === "not_equals" && haystack === needle) return false;
      if (filter.mode === "starts" && !haystack.startsWith(needle)) return false;
      if (filter.mode === "not_contains" && haystack.includes(needle)) return false;
      if ((!filter.mode || filter.mode === "contains") && !haystack.includes(needle)) return false;
    }
  }
  return true;
}

function passesNumericFilter(raw, filter) {
  const value = Number(raw);
  if (!Number.isFinite(value)) return false;
  const mode = filter.mode || "between";
  const target = numericFilterInput(filter.value);
  const min = numericFilterInput(filter.min);
  const max = numericFilterInput(filter.max);
  if (mode === "eq") return target === null ? true : value === target;
  if (mode === "neq") return target === null ? true : value !== target;
  if (mode === "gt") return target === null ? true : value > target;
  if (mode === "gte") return target === null ? true : value >= target;
  if (mode === "lt") return target === null ? true : value < target;
  if (mode === "lte") return target === null ? true : value <= target;
  if (mode === "outside") {
    if (min === null && max === null) return true;
    return (min !== null && value < min) || (max !== null && value > max);
  }
  if (min !== null && value < min) return false;
  if (max !== null && value > max) return false;
  return true;
}

function numericFilterInput(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
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
  const byId = viewerPayloadCache(payload).columnById;
  return (state.columnOrder || []).map((id) => byId.get(id)).filter(Boolean);
}

function visibleViewerColumns(payload, state) {
  const hidden = new Set(state.hiddenColumnIds || []);
  const pinned = new Set(state.pinnedColumnIds || []);
  const ordered = orderedViewerColumns(payload, state).filter((column) => !hidden.has(column.id));
  return [
    ...ordered.filter((column) => pinned.has(column.id)),
    ...ordered.filter((column) => !pinned.has(column.id)),
  ];
}

function originalColumnName(column) {
  return String(column?.source_name || column?.display_name || column?.name || column?.id || "");
}

function effectiveColumnName(column, state) {
  const requested = String(state?.columnRenames?.[column?.id] || "").trim();
  return requested || originalColumnName(column);
}

function columnIsRenamed(column, state) {
  const requested = String(state?.columnRenames?.[column?.id] || "").trim();
  return Boolean(requested && requested !== originalColumnName(column));
}

function setColumnRename(column, name, state, setViewerState) {
  if (!column) return;
  const next = { ...(state.columnRenames || {}) };
  const requested = String(name || "").trim();
  if (!requested || requested === originalColumnName(column)) {
    delete next[column.id];
  } else {
    next[column.id] = requested;
  }
  setViewerState({ columnRenames: next });
}

function clearColumnRename(column, state, setViewerState) {
  if (!column) return;
  const next = { ...(state.columnRenames || {}) };
  delete next[column.id];
  setViewerState({ columnRenames: next });
}

function renderRenameBadge(column, state) {
  if (!columnIsRenamed(column, state)) return null;
  const badge = textSpan("*", "stateframe-web-rename-badge");
  badge.title = `Renamed from ${originalColumnName(column)}`;
  return badge;
}

function summaryViewerColumns(payload, state) {
  const query = String(state.columnSearch || "").trim().toLowerCase();
  let columns = orderedViewerColumns(payload, state);
  if (query) {
    columns = columns.filter((column) => [
      effectiveColumnName(column, state),
      originalColumnName(column),
      column.dtype,
      column.semantic_type,
      column.role,
    ].join(" ").toLowerCase().includes(query));
  }
  const sort = state.columnSort || "original";
  const byName = (a, b) => effectiveColumnName(a, state).localeCompare(effectiveColumnName(b, state));
  const byType = (a, b) => String(a.semantic_type || a.dtype || "").localeCompare(String(b.semantic_type || b.dtype || ""));
  if (sort === "name_asc") columns = [...columns].sort(byName);
  else if (sort === "name_desc") columns = [...columns].sort((a, b) => byName(b, a));
  else if (sort === "type_asc") columns = [...columns].sort(byType);
  else if (sort === "type_desc") columns = [...columns].sort((a, b) => byType(b, a));
  else if (sort === "missing_desc") columns = [...columns].sort((a, b) => Number(b.missing_ratio || 0) - Number(a.missing_ratio || 0));
  else if (sort === "unique_desc") columns = [...columns].sort((a, b) => Number(b.distinct_count || 0) - Number(a.distinct_count || 0));
  else if (sort === "issues_desc") columns = [...columns].sort((a, b) => (b.issues || []).length - (a.issues || []).length);
  return columns;
}

function getViewerColumn(payload, id) {
  return viewerPayloadCache(payload).columnById.get(id) || null;
}

function valueFor(payload, rowIndex, column) {
  const index = viewerPayloadCache(payload).columnIndexById.get(column.id);
  if (index === undefined) return undefined;
  return payload.rows?.[rowIndex]?.[index];
}

function viewerColumnWidth(state, column) {
  const raw = state.widths?.[column.id] || column.width || 140;
  return clampNumber(raw, 140, 84, 420);
}

function applyViewerColumnSizing(cell, state, column) {
  const width = viewerColumnWidth(state, column);
  cell.style.width = `${width}px`;
  cell.style.minWidth = `${width}px`;
  cell.style.maxWidth = `${width}px`;
}

function applyPinnedColumnCell(cell, left, header) {
  cell.classList.add("is-pinned-column");
  if (header) cell.classList.add("is-pinned-header");
  cell.style.left = `${Number(left || 0)}px`;
}

function applyPinnedRowCell(cell, order) {
  cell.classList.add("is-pinned-row-cell");
  cell.style.top = `${34 + Number(order || 0) * 35}px`;
}

function renderColumnMissingBar(column) {
  const outer = document.createElement("div");
  outer.className = "stateframe-web-column-missing";
  const inner = document.createElement("div");
  inner.className = "stateframe-web-column-missing-fill";
  inner.style.width = `${Math.max(0, Math.min(100, Number(column.missing_ratio || 0) * 100))}%`;
  outer.title = `${formatInt(column.missing_count)} missing (${formatPercent(column.missing_ratio)})`;
  outer.appendChild(inner);
  return outer;
}

function renderColumnSparkline(column) {
  if (column.histogram?.bins?.length) {
    const chart = document.createElement("div");
    chart.className = "stateframe-web-column-spark";
    for (const bin of column.histogram.bins.slice(0, 24)) {
      const bar = document.createElement("span");
      const height = column.histogram.max_count ? Math.max(2, (bin.count / column.histogram.max_count) * 22) : 2;
      bar.style.height = `${height}px`;
      bar.title = `${formatNumber(bin.lower)} to ${formatNumber(bin.upper)}: ${formatInt(bin.count)}`;
      chart.appendChild(bar);
    }
    return chart;
  }
  if (column.top_values?.length) {
    const chart = document.createElement("div");
    chart.className = "stateframe-web-column-spark is-frequency";
    const max = Math.max(...column.top_values.slice(0, 8).map((item) => Number(item.count || 0)), 1);
    for (const item of column.top_values.slice(0, 8)) {
      const bar = document.createElement("span");
      const width = Math.max(4, (Number(item.count || 0) / max) * 100);
      bar.style.width = `${width}%`;
      bar.title = `${formatCell(item.value)}: ${formatInt(item.count)}`;
      chart.appendChild(bar);
    }
    return chart;
  }
  const emptySpark = document.createElement("div");
  emptySpark.className = "stateframe-web-column-spark is-empty";
  return emptySpark;
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
    .map(([id, spec]) => ({ column: effectiveColumnName(byId.get(id), state), spec }));
  if (filters.length) pills.push({ kind: "filters", label: `${filters.length} filter${filters.length === 1 ? "" : "s"}`, details: filters });
  if (state.globalSearch) pills.push({ kind: "search", label: `search: ${state.globalSearch}`, details: state.globalSearch });
  if ((state.sorts || []).length) {
    const sorts = (state.sorts || []).map((sort) => ({
      column: byId.has(sort.id) ? effectiveColumnName(byId.get(sort.id), state) : sort.id,
      direction: sort.direction,
    }));
    pills.push({ kind: "sorts", label: `${sorts.length} sort${sorts.length === 1 ? "" : "s"}`, details: sorts });
  }
  if ((state.hiddenColumnIds || []).length) {
    const hidden = state.hiddenColumnIds.map((id) => (byId.has(id) ? effectiveColumnName(byId.get(id), state) : id));
    pills.push({ kind: "hidden_columns", label: `${hidden.length} offloaded`, details: hidden });
  }
  if (JSON.stringify(order) !== JSON.stringify(defaultOrder)) {
    pills.push({ kind: "column_order", label: "reordered columns", details: order.map((id) => (byId.has(id) ? effectiveColumnName(byId.get(id), state) : id)) });
  }
  const renames = Object.entries(state.columnRenames || {})
    .filter(([id, name]) => byId.has(id) && String(name || "").trim() && String(name || "").trim() !== originalColumnName(byId.get(id)))
    .map(([id, name]) => ({ from: originalColumnName(byId.get(id)), to: String(name).trim() }));
  if (renames.length) {
    pills.push({ kind: "column_renames", label: `${renames.length} renamed`, details: renames });
  }
  return { has_changes: Boolean(pills.length), pills };
}

function nextSorts(sorts, columnId, { append = false, direction = null } = {}) {
  const currentSorts = Array.isArray(sorts) ? sorts : [];
  const index = currentSorts.findIndex((sort) => sort.id === columnId);
  const current = index >= 0 ? currentSorts[index] : null;
  const nextDirection = direction || (!current ? "asc" : current.direction === "asc" ? "desc" : null);
  if (!append) {
    return nextDirection ? [{ id: columnId, direction: nextDirection }] : [];
  }
  if (index < 0) {
    return nextDirection ? [...currentSorts, { id: columnId, direction: nextDirection }] : currentSorts;
  }
  if (!nextDirection) {
    return currentSorts.filter((_, sortIndex) => sortIndex !== index);
  }
  return currentSorts.map((sort, sortIndex) => (
    sortIndex === index ? { ...sort, direction: nextDirection } : sort
  ));
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
  } else if (entry.has_ancestor_snapshot) {
    title.textContent = "Ready to pull";
    body.textContent = "stateframe can load the nearest saved data snapshot and replay this branch.";
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
    if (value === null || value === undefined || value === "") continue;
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

function disclosureBlock(title, child, { open = false } = {}) {
  const details = document.createElement("details");
  details.className = "stateframe-web-disclosure";
  details.open = open;
  const summary = document.createElement("summary");
  summary.textContent = title;
  details.append(summary, child);
  return details;
}

function renderEntryParams(params) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-param-summary";
  const summary = summarizeEntryParams(params);
  if (summary && Object.keys(summary).length) wrap.appendChild(keyValueList(summary));
  wrap.appendChild(disclosureBlock("Raw params", jsonBlock(params)));
  return wrap;
}

function renderLeafSummary(summary) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-param-summary";
  const rows = {};
  if (summary.title) rows.Title = summary.title;
  if (summary.visual_kind) rows.Visual = summary.visual_kind;
  if (summary.engine) rows.Engine = summary.engine;
  if (summary.row_count !== undefined) rows.Rows = formatInt(summary.row_count);
  if (summary.column_count !== undefined) rows.Columns = formatInt(summary.column_count);
  if (summary.fields && Object.keys(summary.fields).length) rows.Fields = fieldSummary(summary.fields);
  if (summary.filter_count !== undefined) rows.Filters = formatInt(summary.filter_count);
  if (Object.keys(rows).length) wrap.appendChild(keyValueList(rows));
  wrap.appendChild(disclosureBlock("Raw summary", jsonBlock(summary)));
  return wrap;
}

function summarizeEntryParams(params) {
  const rows = {};
  const viewer = params.viewer_summary;
  if (viewer && typeof viewer === "object") {
    if (viewer.output_name) rows.Output = viewer.output_name;
    if (viewer.row_count !== undefined && viewer.source_row_count !== undefined) {
      rows.Rows = `${formatInt(viewer.row_count)} of ${formatInt(viewer.source_row_count)}`;
    }
    if (viewer.filters && Object.keys(viewer.filters).length) rows.Filters = filterSummary(viewer.filters);
    if (Array.isArray(viewer.sorts) && viewer.sorts.length) rows.Sorts = sortSummary(viewer.sorts);
    if (Array.isArray(viewer.hidden_columns) && viewer.hidden_columns.length) rows.Hidden = viewer.hidden_columns.join(", ");
    if (viewer.selected_column) rows.Selected = viewer.selected_column;
    if (viewer.global_search) rows.Search = viewer.global_search;
    if (viewer.message) rows.Message = viewer.message;
    return rows;
  }

  const visual = params.visual_spec;
  if (visual && typeof visual === "object") {
    if (visual.title) rows.Title = visual.title;
    if (visual.kind) rows.Visual = visual.kind;
    if (visual.fields && Object.keys(visual.fields).length) rows.Fields = fieldSummary(visual.fields);
    if (Array.isArray(visual.filters) && visual.filters.length) rows.Filters = `${visual.filters.length} filter${visual.filters.length === 1 ? "" : "s"}`;
    if (visual.note) rows.Note = visual.note;
    return rows;
  }

  if (params.output_name) rows.Output = params.output_name;
  if (params.message) rows.Message = params.message;
  return rows;
}

function filterSummary(filters) {
  return Object.entries(filters)
    .map(([column, filter]) => `${column} ${filter?.mode || filter?.kind || "filter"} ${filterValue(filter)}`.trim())
    .join("; ");
}

function sortSummary(sorts) {
  return sorts
    .map((sort) => `${sort.column || sort.name || sort.id || "column"} ${sort.direction || (sort.desc ? "desc" : "asc")}`)
    .join("; ");
}

function fieldSummary(fields) {
  return Object.entries(fields)
    .map(([slot, value]) => `${slot}: ${Array.isArray(value) ? value.join(", ") : value}`)
    .join("; ");
}

function filterValue(filter) {
  if (!filter || typeof filter !== "object") return "";
  if (filter.value !== undefined && filter.value !== "") return String(filter.value);
  const parts = [];
  if (filter.min !== undefined && filter.min !== "") parts.push(`>= ${filter.min}`);
  if (filter.max !== undefined && filter.max !== "") parts.push(`<= ${filter.max}`);
  return parts.join(" ");
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

function toggleNumberValue(values, value) {
  const number = Number(value);
  const set = new Set((values || []).map((item) => Number(item)));
  if (set.has(number)) set.delete(number);
  else set.add(number);
  return Array.from(set).filter((item) => Number.isInteger(item)).sort((a, b) => a - b);
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

function commandIsLoading(status, ...actions) {
  if (status?.status !== "loading") return false;
  return !actions.length || actions.includes(status.action);
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

function formatShortDate(value) {
  if (!value && value !== 0) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString();
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
