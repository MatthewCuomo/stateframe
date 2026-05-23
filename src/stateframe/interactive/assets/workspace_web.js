const VIEWER_PAYLOAD_CACHE = new WeakMap();
const VIEWER_GRID_CELL_BUDGET = 12000;

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

  function setState(patch) {
    captureFocus(root, ui);
    state = normalizeState({ ...state, ...patch }, payload);
    model.set("state", state);
    model.save_changes();
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
    model.save_changes();
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
    model.save_changes();
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
    model.save_changes();
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
    model.save_changes();
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
    model.save_changes();
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
    body.appendChild(renderDetail(payload, selected, selectedEntry, state, setState, openSelectedViewer, openSelectedVisualizer, openSelectedCleaning, openSelectedModeling));
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
    search: raw?.search || "",
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
  return {
    kind,
    fields,
    fieldOptions,
    filters,
    options: raw?.options || {},
    controlMode: ["basic", "advanced", "expert"].includes(raw?.controlMode) ? raw.controlMode : "basic",
    controlQuery: raw?.controlQuery || "",
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
  const rawOrder = Array.isArray(raw?.columnOrder) ? raw.columnOrder : [];
  const rawOrderSet = new Set(rawOrder);
  const columnOrder = [
    ...rawOrder.filter((id) => allIdSet.has(id)),
    ...allIds.filter((id) => !rawOrderSet.has(id)),
  ];
  const hiddenColumnIds = Array.isArray(raw?.hiddenColumnIds)
    ? raw.hiddenColumnIds.filter((id) => allIdSet.has(id))
    : [];
  const sorts = Array.isArray(raw?.sorts)
    ? raw.sorts.filter((sort) => allIdSet.has(sort.id) && ["asc", "desc"].includes(sort.direction))
    : [];
  return {
    columnOrder,
    hiddenColumnIds,
    sorts,
    filters: raw?.filters || {},
    globalSearch: raw?.globalSearch || "",
    selectedColumnId: allIdSet.has(raw?.selectedColumnId) ? raw.selectedColumnId : allIds[0] || null,
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

function renderDetail(payload, tree, selectedEntry, state, setState, openSelectedViewer, openSelectedVisualizer, openSelectedCleaning, openSelectedModeling) {
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
    panel.appendChild(section("Selected State", renderEntryDetail(tree, selectedEntry, openSelectedViewer, openSelectedVisualizer, openSelectedCleaning, openSelectedModeling, setState)));
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

function renderEntryDetail(tree, entry, openSelectedViewer, openSelectedVisualizer, openSelectedCleaning, openSelectedModeling, setState) {
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
  const defaults = button("Select Defaults", () => setModelingState({
    selectedActionIds: actions.filter((action) => action.applies_by_default !== false).map((action) => action.id).filter(Boolean),
  }));
  const all = button("All", () => setModelingState({ selectedActionIds: actions.map((action) => action.id).filter(Boolean) }));
  const none = button("None", () => setModelingState({ selectedActionIds: [] }));
  top.append(title, meta, defaults, all, none, run, apply);
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
  } else if (commandStatus?.status === "error") {
    const error = document.createElement("div");
    error.className = "stateframe-web-status is-error";
    error.textContent = commandStatus.message || "Action failed";
    shell.appendChild(error);
  }
  if (modeling.preview?.kind === "modeling_experiment") {
    shell.appendChild(renderModelingExperimentResult(modeling.preview.result || {}));
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
  const targetColumn = modelingColumnForValue(payload, experiment.target || summary.target);
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
  panel.appendChild(section("Feature Scope", renderModelingFeaturePicker(payload, modelingState, setModelingState)));
  panel.appendChild(section("Columns", renderCleaningColumnSummary(payload.columns || [])));
  return panel;
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
    selectSetting("Task", experiment.task || "auto", (catalog.tasks || []).map((item) => [item.id, item.label || item.id]), (value) => updateExperiment({ task: value }), "modeling-exp-task"),
    selectSetting("Estimator", experiment.estimator || "random_forest", (catalog.estimators || []).map((item) => [item.id, item.label || item.id]), (value) => updateExperiment({ estimator: value }), "modeling-exp-estimator"),
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
    numberSetting("Clusters", experiment.clustering?.n_clusters ?? 3, (value) => updateExperiment({ clustering: { n_clusters: Number(value) } }), "modeling-exp-clusters", "2", "30", "1"),
  );
  return stack;
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

function renderModelingExperimentResult(result) {
  const panel = document.createElement("section");
  panel.className = "stateframe-web-cleaning-detail";
  const title = document.createElement("div");
  title.className = "stateframe-web-cleaning-detail-title";
  title.textContent = `Experiment: ${result.estimator || "model"} / ${result.task || ""}`;
  panel.appendChild(title);
  panel.appendChild(section("Training Setup", renderModelingTrainingSetup(result)));
  panel.appendChild(section("Metrics", renderModelingMetricTiles(result.metrics || {})));
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
    row.append(textSpan(key, "stateframe-web-cleaning-preview-key"), textSpan(cleaningPreviewText(item), "stateframe-web-cleaning-preview-value"));
    wrap.appendChild(row);
  }
  return wrap;
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
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-suggestions";
  const title = document.createElement("div");
  title.className = "stateframe-web-visual-family-title";
  title.textContent = "Suggested";
  wrap.appendChild(title);
  if (!suggestions.length) {
    const hint = document.createElement("div");
    hint.className = "stateframe-web-visual-type-description";
    hint.textContent = "No automatic suggestions for this state yet.";
    wrap.appendChild(hint);
    return wrap;
  }
  for (const suggestion of suggestions.slice(0, 8)) {
    const spec = suggestion.spec || {};
    const item = document.createElement("button");
    item.type = "button";
    item.className = "stateframe-web-visual-suggestion";
    if (spec.kind === visualState.kind && spec.title === visualState.title) item.classList.add("is-selected");
    item.addEventListener("click", () => setVisualizerState({
      kind: spec.kind || visualState.kind,
      fields: spec.fields || {},
      fieldOptions: spec.field_options || spec.fieldOptions || {},
      filters: Array.isArray(spec.filters) ? spec.filters : [],
      options: spec.options || {},
      title: spec.title || suggestion.title || "",
    }));
    const itemTitle = document.createElement("div");
    itemTitle.className = "stateframe-web-visual-type-title";
    itemTitle.textContent = suggestion.title || spec.title || spec.kind || "Suggested visual";
    const meta = document.createElement("div");
    meta.className = "stateframe-web-visual-type-description";
    meta.textContent = [spec.kind, suggestion.reason].filter(Boolean).join(" / ");
    item.append(itemTitle, meta);
    wrap.appendChild(item);
  }
  return wrap;
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
  render.disabled = commandIsLoading(commandStatus, "render_visualizer", "save_visualizer_leaf");
  save.disabled = commandIsLoading(commandStatus, "render_visualizer", "save_visualizer_leaf");
  controls.append(title, render, save);
  panel.appendChild(controls);
  panel.appendChild(section("Plot Recipe", renderVisualRecipe(payload, visualState)));
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
  const measureSlot = ["y", "values", "r", "z", "size"].find((slot) => fields[slot]);
  if (measureSlot) {
    const stat = fieldOptions[measureSlot]?.stat || defaultFieldOptionForSlot(payload, definition, measureSlot, fields[measureSlot]).stat || "raw";
    rows.Measure = `${visualStatLabel(stat)} ${visualFieldLabel(payload, fields[measureSlot])}`;
  } else if (Array.isArray(fields.dimensions) && fields.dimensions.length) {
    rows.Measure = "Not used";
  } else {
    rows.Measure = "Record count";
  }
  const bucketSlot = ["x", "date"].find((slot) => fieldOptions[slot]?.bucket && fieldOptions[slot].bucket !== "none");
  rows.Bucket = bucketSlot ? `${bucketSlot}: ${fieldOptions[bucketSlot].bucket}` : "";
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
    const row = document.createElement(field.multiple ? "div" : "label");
    row.className = "stateframe-web-visual-field";
    const label = document.createElement("span");
    label.textContent = `${field.label}${field.required ? " *" : ""}`;
    const current = visualState.fields?.[field.slot];
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
    for (const column of visualCandidateColumns(payload, definition, field)) {
      const option = document.createElement("option");
      option.value = column.id;
      option.textContent = column.display_name || column.source_name || column.id;
      select.appendChild(option);
    }
    select.value = current || "";
    select.addEventListener("change", () => {
      const next = { ...(visualState.fields || {}) };
      const nextFieldOptions = { ...(visualState.fieldOptions || {}) };
      if (select.value) {
        next[field.slot] = select.value;
        const defaults = defaultFieldOptionForSlot(payload, definition, field.slot, select.value);
        if (Object.keys(defaults).length) nextFieldOptions[field.slot] = { ...defaults, ...(nextFieldOptions[field.slot] || {}) };
        else delete nextFieldOptions[field.slot];
      } else {
        delete next[field.slot];
        delete nextFieldOptions[field.slot];
      }
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

function renderVisualMultiField(payload, definition, field, visualState, setVisualizerState) {
  const current = Array.isArray(visualState.fields?.[field.slot]) ? visualState.fields[field.slot] : [];
  const currentSet = new Set(current);
  const candidates = visualCandidateColumns(payload, definition, field);
  const panel = document.createElement("div");
  panel.className = "stateframe-web-visual-multi";
  const toolbar = document.createElement("div");
  toolbar.className = "stateframe-web-visual-multi-toolbar";
  const suggested = tinyButton("Suggested", () => {
    const values = defaultMultipleColumnsForVisual(payload, definition, field);
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
  if (!controls.length) return null;
  const wrap = document.createElement("div");
  wrap.className = "stateframe-web-visual-field-behavior";
  wrap.append(...controls);
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
    return Boolean(fields.x || fields.y || fields.values || fields.names || fields.path || definition.id === "missingness");
  }
  if (group.id === "references") {
    return Boolean(fields.x || fields.y || fields.values || fields.r);
  }
  return true;
}

function visualHasMeasureBehavior(definition, fields) {
  return ["y", "values", "r", "z"].some((slot) => fields?.[slot] && visualSlotSupportsStat(definition.id, slot));
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
  const visibleCellWidth = Math.max(1, visibleColumns.length + (state.showIndex ? 1 : 0));
  const limit = Math.max(40, Math.min(500, Math.floor(VIEWER_GRID_CELL_BUDGET / visibleCellWidth)));
  const activeVirtualIndex = activeMatch?.virtualIndex ?? 0;
  const start = activeVirtualIndex >= limit ? Math.max(0, activeVirtualIndex - 25) : 0;
  const rows = computed.indices.slice(start, start + limit);
  const bodyFragment = document.createDocumentFragment();
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
    bodyFragment.appendChild(tr);
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
    field_options: cleanObject(state.fieldOptions || {}),
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
    scatter_matrix: 4,
    pca_scatter: 6,
    parallel_coordinates: 6,
    parallel_categories: 5,
    treemap: 3,
    sunburst: 3,
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
  if (field?.slot === "path" && categorical) return categorical.id;
  if (field?.slot === "values" && numeric) return numeric.id;
  if (field?.slot === "y" && numeric) return numeric.id;
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
  if (["y", "values", "r", "z"].includes(slot) && visualSlotSupportsStat(kind, slot)) {
    options.stat = defaultVisualStat(column, kind, slot);
  }
  if (["x", "date"].includes(slot) && visualColumnLooksDate(column) && ["line", "area", "bar"].includes(kind)) {
    options.bucket = "none";
  }
  return options;
}

function visualSlotSupportsStat(kind, slot) {
  if (["scatter", "box", "violin", "strip", "ecdf", "histogram", "scatter_matrix", "parallel_coordinates", "parallel_categories", "pca_scatter", "qq_plot", "autocorrelation"].includes(kind)) {
    return false;
  }
  if (slot === "z") return kind === "heatmap";
  if (slot === "values") return ["pie", "treemap", "sunburst", "choropleth", "calendar_heatmap"].includes(kind);
  if (slot === "r") return kind === "radar";
  if (slot === "y") return ["line", "area", "bar", "lollipop", "slope", "bump_chart", "pareto", "waterfall", "funnel"].includes(kind);
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
    rowSearchText: null,
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
  const value = {
    indices,
    matches: query ? findViewerMatches(payload, visibleViewerColumns(payload, state), indices, query) : [],
  };
  cache.computedRows = { signature, value };
  return value;
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
  const byId = viewerPayloadCache(payload).columnById;
  return (state.columnOrder || []).map((id) => byId.get(id)).filter(Boolean);
}

function visibleViewerColumns(payload, state) {
  const hidden = new Set(state.hiddenColumnIds || []);
  return orderedViewerColumns(payload, state).filter((column) => !hidden.has(column.id));
}

function getViewerColumn(payload, id) {
  return viewerPayloadCache(payload).columnById.get(id) || null;
}

function valueFor(payload, rowIndex, column) {
  const index = viewerPayloadCache(payload).columnIndexById.get(column.id);
  if (index === undefined) return undefined;
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
