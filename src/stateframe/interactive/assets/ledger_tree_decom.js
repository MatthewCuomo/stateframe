function render({ model, el, signal }) {
  const payload = model.get("payload");
  let state = normalizeState(model.get("state"), payload);
  const ui = {
    focus: null,
    searchDraft: state.search || "",
    searchTimer: null,
  };

  el.classList.add("stateframe-ledger-host");
  el.style.setProperty("--stateframe-ledger-height", `${payload.view.height}px`);

  const root = document.createElement("div");
  root.className = "stateframe-tree";
  el.replaceChildren(root);

  function setState(patch) {
    captureFocus(root, ui);
    state = normalizeState({ ...state, ...patch }, payload);
    model.set("state", state);
    model.save_changes();
    draw();
  }

  function onStateChange() {
    state = normalizeState(model.get("state"), payload);
    if (focusedKey(root) !== "ledger-search") ui.searchDraft = state.search || "";
    draw();
  }

  model.on("change:state", onStateChange);
  signal.addEventListener("abort", () => {
    model.off("change:state", onStateChange);
    if (ui.searchTimer) clearTimeout(ui.searchTimer);
  });

  function draw() {
    const ledger = payload.ledger || {};
    const entries = ledger.entries || [];
    const filtered = filterEntries(entries, state);
    const selected =
      getEntry(entries, state.selectedEntryId)
      || getEntry(entries, ledger.active_entry_id)
      || entries[0]
      || null;

    root.innerHTML = "";
    root.appendChild(renderToolbar(payload, entries, state, setState, ui));
    root.appendChild(renderStats(payload));

    const body = document.createElement("div");
    body.className = "stateframe-tree-body";
    body.appendChild(renderTreePanel(payload, filtered, selected, state, setState));
    body.appendChild(renderDetailPanel(payload, selected));
    root.appendChild(body);
    requestAnimationFrame(() => restoreFocus(root, ui));
  }

  draw();
}

function normalizeState(raw, payload) {
  const entries = payload.ledger?.entries || [];
  const ids = new Set(entries.map((entry) => entry.id));
  const active = payload.ledger?.active_entry_id;
  const selected =
    ids.has(raw?.selectedEntryId) ? raw.selectedEntryId
    : ids.has(active) ? active
    : entries[0]?.id || null;
  const kinds = new Set(["all", ...entries.map((entry) => entry.kind || "unknown")]);
  return {
    selectedEntryId: selected,
    search: raw?.search || "",
    kindFilter: kinds.has(raw?.kindFilter) ? raw.kindFilter : "all",
    showOnlyStateful: Boolean(raw?.showOnlyStateful),
    collapsedEntryIds: Array.isArray(raw?.collapsedEntryIds)
      ? raw.collapsedEntryIds.filter((id) => ids.has(id))
      : [],
  };
}

function renderToolbar(payload, entries, state, setState, ui) {
  const toolbar = document.createElement("div");
  toolbar.className = "stateframe-tree-toolbar";

  const titleGroup = document.createElement("div");
  titleGroup.className = "stateframe-tree-title-group";
  const title = document.createElement("div");
  title.className = "stateframe-tree-title";
  title.textContent = payload.title || "stateframe analysis tree";
  const subtitle = document.createElement("div");
  subtitle.className = "stateframe-tree-subtitle";
  subtitle.textContent = subtitleText(payload);
  titleGroup.append(title, subtitle);

  const search = document.createElement("input");
  search.className = "stateframe-tree-input";
  search.type = "search";
  search.placeholder = "Search operations, notes, code";
  search.dataset.focusKey = "ledger-search";
  search.value = ui.searchDraft ?? state.search ?? "";
  search.addEventListener("input", () => {
    ui.searchDraft = search.value;
    if (ui.searchTimer) clearTimeout(ui.searchTimer);
    ui.searchTimer = setTimeout(() => {
      ui.searchTimer = null;
      setState({ search: ui.searchDraft || "" });
    }, 160);
  });

  const kindFilter = document.createElement("select");
  kindFilter.className = "stateframe-tree-select";
  const kinds = ["all", ...Array.from(new Set(entries.map((entry) => entry.kind || "unknown"))).sort()];
  for (const kind of kinds) {
    const option = document.createElement("option");
    option.value = kind;
    option.textContent = kind === "all" ? "All kinds" : kind;
    kindFilter.appendChild(option);
  }
  kindFilter.value = state.kindFilter || "all";
  kindFilter.addEventListener("change", () => setState({ kindFilter: kindFilter.value }));

  const stateful = document.createElement("button");
  stateful.type = "button";
  stateful.className = `stateframe-tree-button ${state.showOnlyStateful ? "is-active" : ""}`;
  stateful.textContent = "States";
  stateful.title = "Show only entries with dataframe states";
  stateful.addEventListener("click", () => setState({ showOnlyStateful: !state.showOnlyStateful }));

  const active = document.createElement("button");
  active.type = "button";
  active.className = "stateframe-tree-button";
  active.textContent = "Active";
  active.title = "Select the active ledger entry";
  active.addEventListener("click", () => setState({ selectedEntryId: payload.ledger?.active_entry_id }));

  const controls = document.createElement("div");
  controls.className = "stateframe-tree-controls";
  controls.append(search, kindFilter, stateful, active);
  toolbar.append(titleGroup, controls);
  return toolbar;
}

function renderStats(payload) {
  const stats = payload.ledger?.stats || {};
  const row = document.createElement("div");
  row.className = "stateframe-tree-stats";
  row.append(
    statCard("Entries", formatInt(stats.entry_count || 0)),
    statCard("States", formatInt(stats.state_count || 0)),
    statCard("Leaves", formatInt(stats.leaf_count || 0)),
    statCard("Depth", formatInt(stats.max_depth || 0)),
  );
  return row;
}

function statCard(label, value) {
  const card = document.createElement("div");
  card.className = "stateframe-tree-stat";
  const valueEl = document.createElement("div");
  valueEl.className = "stateframe-tree-stat-value";
  valueEl.textContent = value;
  const labelEl = document.createElement("div");
  labelEl.className = "stateframe-tree-stat-label";
  labelEl.textContent = label;
  card.append(valueEl, labelEl);
  return card;
}

function renderTreePanel(payload, entries, selected, state, setState) {
  const panel = document.createElement("section");
  panel.className = "stateframe-tree-panel";

  const header = document.createElement("div");
  header.className = "stateframe-tree-panel-header";
  header.textContent = "Workflow Tree";
  panel.appendChild(header);

  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "stateframe-tree-empty";
    empty.textContent = "No matching ledger entries.";
    panel.appendChild(empty);
    return panel;
  }

  const pathIds = new Set((selected?.path || []).map((item) => item.id));
  const hierarchy = buildEntryHierarchy(entries);
  const collapsed = new Set(state.collapsedEntryIds || []);
  const visited = new Set();
  const list = document.createElement("div");
  list.className = "stateframe-tree-list";

  function appendEntry(entry, depth, trail = new Set()) {
    if (!entry?.id || trail.has(entry.id) || visited.has(entry.id)) return;
    visited.add(entry.id);
    const children = hierarchy.byParent.get(entry.id) || [];
    const hasChildren = children.length > 0;
    const isCollapsed = hasChildren && collapsed.has(entry.id);

    const row = document.createElement("div");
    row.className = "stateframe-tree-row";
    if (depth > 0) row.classList.add("is-nested");
    if (hasChildren) row.classList.add("has-children");
    if (isCollapsed) row.classList.add("is-collapsed");
    row.style.setProperty("--entry-depth", String(Math.min(Number(depth || 0), 8)));

    if (hasChildren) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "stateframe-tree-toggle";
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
      spacer.className = "stateframe-tree-toggle-spacer";
      row.appendChild(spacer);
    }

    const node = document.createElement("button");
    node.type = "button";
    node.className = "stateframe-tree-node";
    node.classList.add(...entryKindClasses(entry, "stateframe-tree"));
    if (entry.id === selected?.id) node.classList.add("is-selected");
    if (entry.is_active) node.classList.add("is-active");
    if (pathIds.has(entry.id)) node.classList.add("is-in-path");
    if (!entryMatchesFilters(entry, state)) node.classList.add("is-context-only");
    if (isCollapsed) node.classList.add("is-collapsed");
    node.addEventListener("click", () => setState({ selectedEntryId: entry.id }));

    const line = document.createElement("div");
    line.className = "stateframe-tree-node-line";
    const kind = document.createElement("span");
    kind.className = "stateframe-tree-kind";
    kind.classList.add(`stateframe-tree-kind-${safeClassName(entry.kind)}`);
    kind.textContent = entry.kind || "entry";
    const name = document.createElement("span");
    name.className = "stateframe-tree-node-title";
    name.textContent = entry.title || entry.operation || entry.id;
    line.append(kind, name);

    const meta = document.createElement("div");
    meta.className = "stateframe-tree-node-meta";
    const stateText = isOutputEntry(entry) ? " / output leaf" : entry.has_state ? " / state" : "";
    const childText = entry.child_count ? ` / ${entry.child_count} child${entry.child_count === 1 ? "" : "ren"}` : "";
    const hidden = isCollapsed ? ` / ${descendantCount(entry.id, hierarchy.byParent)} hidden` : "";
    meta.textContent = `${entry.operation || entry.kind}${stateText}${childText}${hidden}`;

    node.append(line, meta);
    row.appendChild(node);
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
  panel.appendChild(list);
  return panel;
}

function renderDetailPanel(payload, entry) {
  const panel = document.createElement("aside");
  panel.className = "stateframe-tree-detail";

  if (!entry) {
    const empty = document.createElement("div");
    empty.className = "stateframe-tree-empty";
    empty.textContent = "Select an entry to inspect it.";
    panel.appendChild(empty);
    return panel;
  }

  const header = document.createElement("div");
  header.className = "stateframe-tree-detail-header";
  const title = document.createElement("div");
  title.className = "stateframe-tree-detail-title";
  title.textContent = entry.title || entry.operation || entry.id;
  const subtitle = document.createElement("div");
  subtitle.className = "stateframe-tree-detail-subtitle";
  subtitle.textContent = `${entry.kind || "entry"} / ${entry.operation || "operation"}`;
  header.append(title, subtitle);
  panel.appendChild(header);

  if (entry.path?.length) {
    panel.appendChild(section("Path", renderPath(entry.path)));
  }

  panel.appendChild(section("Entry", keyValueList({
    id: entry.id,
    parent: entry.parent_id || "root",
    status: entry.status,
    time: entry.timestamp,
    state: entry.state_id || "",
  })));

  if (entry.state) {
    panel.appendChild(section("Data State", keyValueList({
      label: entry.state.label,
      rows: entry.state.row_count,
      columns: entry.state.column_count,
      memory: formatBytes(entry.state.memory_bytes),
      materialized: entry.state.has_data ? "yes" : "metadata only",
    })));
  }

  if (entry.summary && Object.keys(entry.summary).length) {
    panel.appendChild(section("Summary", keyValueList(entry.summary)));
  }
  if (entry.metrics && Object.keys(entry.metrics).length) {
    panel.appendChild(section("Metrics", keyValueList(entry.metrics)));
  }
  if (entry.columns?.length) {
    panel.appendChild(section("Columns", renderPills(entry.columns)));
  }
  if (entry.code) {
    panel.appendChild(section("Code", codeBlock(entry.code)));
  }
  if (entry.params && Object.keys(entry.params).length) {
    panel.appendChild(section("Parameters", jsonBlock(entry.params)));
  }
  if (entry.artifacts?.length) {
    panel.appendChild(section("Artifacts", renderArtifacts(entry.artifacts)));
  }
  if (entry.note) {
    const note = document.createElement("div");
    note.className = "stateframe-tree-note";
    note.textContent = entry.note;
    panel.appendChild(section("Note", note));
  }
  if (entry.options?.length) {
    panel.appendChild(section("Options From Here", renderOptions(entry.options)));
  }
  if (payload.recommendations?.length && entry.is_active) {
    panel.appendChild(section("Current Top Recommendations", renderOptions(payload.recommendations)));
  }
  return panel;
}

function filterEntries(entries, state) {
  const byId = new Map(entries.map((entry) => [entry.id, entry]));
  const visible = new Set();
  for (const entry of entries) {
    if (!entryMatchesFilters(entry, state)) continue;
    visible.add(entry.id);
    let parentId = entry.parent_id;
    const seen = new Set([entry.id]);
    while (parentId && byId.has(parentId) && !seen.has(parentId)) {
      visible.add(parentId);
      seen.add(parentId);
      parentId = byId.get(parentId).parent_id;
    }
  }
  return entries.filter((entry) => visible.has(entry.id));
}

function entryMatchesFilters(entry, state) {
  const query = String(state.search || "").trim().toLowerCase();
  if (state.kindFilter !== "all" && entry.kind !== state.kindFilter) return false;
  if (state.showOnlyStateful && !entry.has_state) return false;
  if (!query) return true;
  const haystack = [
    entry.title,
    entry.kind,
    entry.operation,
    entry.id,
    entry.code,
    entry.note,
    ...(entry.columns || []),
  ].join(" ").toLowerCase();
  return haystack.includes(query);
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

function safeClassName(value) {
  return String(value || "entry").toLowerCase().replace(/[^a-z0-9_-]+/g, "-");
}

function renderPath(path) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-tree-path";
  for (const step of path) {
    const item = document.createElement("span");
    item.className = "stateframe-tree-path-item";
    item.textContent = step.title || step.operation || step.id;
    wrap.appendChild(item);
  }
  return wrap;
}

function renderPills(items) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-tree-pills";
  for (const item of items) {
    const pill = document.createElement("span");
    pill.className = "stateframe-tree-pill";
    pill.textContent = item;
    wrap.appendChild(pill);
  }
  return wrap;
}

function renderOptions(options) {
  const list = document.createElement("div");
  list.className = "stateframe-tree-options";
  for (const option of options.slice(0, 8)) {
    const item = document.createElement("div");
    item.className = "stateframe-tree-option";
    const title = document.createElement("div");
    title.className = "stateframe-tree-option-title";
    title.textContent = option.title || option.lens || option.id;
    const meta = document.createElement("div");
    meta.className = "stateframe-tree-option-meta";
    const score = typeof option.score === "number" ? ` / score ${option.score.toFixed(2)}` : "";
    meta.textContent = `${option.lens || option.id || "option"}${score}`;
    item.append(title, meta);
    if (option.code) item.appendChild(codeBlock(option.code));
    list.appendChild(item);
  }
  return list;
}

function section(title, content) {
  const wrapper = document.createElement("section");
  wrapper.className = "stateframe-tree-section";
  const heading = document.createElement("div");
  heading.className = "stateframe-tree-section-title";
  heading.textContent = title;
  wrapper.append(heading, content);
  return wrapper;
}

function keyValueList(data) {
  const list = document.createElement("dl");
  list.className = "stateframe-tree-kv";
  for (const [key, value] of Object.entries(data || {})) {
    if (value === undefined || value === "") continue;
    const dt = document.createElement("dt");
    dt.textContent = key.replaceAll("_", " ");
    const dd = document.createElement("dd");
    dd.textContent = formatValue(value);
    list.append(dt, dd);
  }
  return list;
}

function codeBlock(text) {
  const code = document.createElement("code");
  code.className = "stateframe-tree-code";
  code.textContent = text;
  return code;
}

function jsonBlock(value) {
  const pre = document.createElement("pre");
  pre.className = "stateframe-tree-json";
  pre.textContent = JSON.stringify(value, null, 2);
  return pre;
}

function renderArtifacts(artifacts) {
  const list = document.createElement("div");
  list.className = "stateframe-tree-artifacts";
  for (const artifact of artifacts) {
    if (artifact?.kind === "code_leaf") {
      list.appendChild(renderCodeLeafArtifact(artifact));
    } else if (artifact?.kind === "plot" && artifact.preview_data_url) {
      const item = document.createElement("div");
      item.className = "stateframe-tree-plot-artifact";
      const title = document.createElement("div");
      title.className = "stateframe-tree-plot-artifact-title";
      title.textContent = artifact.title || artifact.plot_id || "Plot";
      const image = document.createElement("img");
      image.className = "stateframe-tree-plot-artifact-image";
      image.src = artifact.preview_data_url;
      image.alt = artifact.title || "stateframe plot leaf";
      item.append(title, image, jsonBlock({ spec: artifact.spec, source_lens: artifact.source_lens }));
      list.appendChild(item);
    } else {
      list.appendChild(jsonBlock(artifact));
    }
  }
  return list;
}

function renderCodeLeafArtifact(artifact) {
  const item = document.createElement("div");
  item.className = "stateframe-tree-code-leaf";
  const title = document.createElement("div");
  title.className = "stateframe-tree-code-leaf-title";
  title.textContent = artifact.title || "Code leaf";
  const meta = document.createElement("div");
  meta.className = "stateframe-tree-code-leaf-meta";
  meta.textContent = `${artifact.dependency || "branch"}${artifact.saved ? " / saved" : " / metadata only"}`;
  item.append(title, meta);
  for (const preview of artifact.previews || []) {
    item.appendChild(renderLeafPreview(preview));
  }
  return item;
}

function renderLeafPreview(preview) {
  if (preview.kind === "terminal") {
    const pre = document.createElement("pre");
    pre.className = "stateframe-tree-terminal-preview";
    pre.textContent = [preview.stdout || "", preview.stderr || ""].filter(Boolean).join("\n");
    return section("Terminal", pre);
  }
  if ((preview.kind === "image" || preview.kind === "matplotlib" || preview.kind === "plotly") && preview.preview_data_url) {
    const image = document.createElement("img");
    image.className = "stateframe-tree-leaf-image";
    image.src = preview.preview_data_url;
    image.alt = preview.name || "stateframe leaf preview";
    return section(preview.name || "Preview", image);
  }
  if (preview.kind === "plotly") {
    const placeholder = document.createElement("div");
    placeholder.className = "stateframe-tree-leaf-placeholder";
    placeholder.textContent = "Interactive Plotly output saved for the full web leaf view.";
    return section(preview.name || "Plotly", placeholder);
  }
  if (preview.kind === "dataframe") {
    return section(preview.name || "DataFrame", renderDataFramePreview(preview));
  }
  return section(preview.name || preview.kind || "Preview", jsonBlock(preview));
}

function renderDataFramePreview(preview) {
  const wrap = document.createElement("div");
  wrap.className = "stateframe-tree-dataframe-preview";
  const meta = document.createElement("div");
  meta.className = "stateframe-tree-code-leaf-meta";
  meta.textContent = `${formatInt(preview.row_count || 0)} rows x ${formatInt(preview.column_count || 0)} columns`;
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const tr = document.createElement("tr");
  for (const column of (preview.columns || []).slice(0, 6)) {
    const th = document.createElement("th");
    th.textContent = column;
    tr.appendChild(th);
  }
  thead.appendChild(tr);
  const tbody = document.createElement("tbody");
  for (const row of (preview.rows || []).slice(0, 8)) {
    const bodyRow = document.createElement("tr");
    for (const column of (preview.columns || []).slice(0, 6)) {
      const td = document.createElement("td");
      td.textContent = formatValue(row[column]);
      bodyRow.appendChild(td);
    }
    tbody.appendChild(bodyRow);
  }
  table.append(thead, tbody);
  wrap.append(meta, table);
  return wrap;
}

// Text inputs that update synced widget state must carry a stable focus key.
// The widget redraws after state sync, so this preserves caret position.
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

function focusedKey(root) {
  const active = root.ownerDocument.activeElement;
  return active && root.contains(active) ? active.dataset?.focusKey || null : null;
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

function getEntry(entries, id) {
  return entries.find((entry) => entry.id === id) || null;
}

function subtitleText(payload) {
  const summary = payload.summary || {};
  const view = payload.view || {};
  const shape = `${formatInt(summary.row_count || 0)} rows x ${formatInt(summary.column_count || 0)} columns`;
  const target = view.target ? ` / target ${view.target}` : "";
  const time = view.time ? ` / time ${view.time}` : "";
  return `${shape}${target}${time}`;
}

function formatValue(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "";
    if (Math.abs(value) >= 1000) return value.toLocaleString();
    if (!Number.isInteger(value)) return value.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function formatInt(value) {
  return Number(value || 0).toLocaleString();
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let current = bytes / 1024;
  for (const unit of units) {
    if (current < 1024) return `${current.toFixed(current >= 10 ? 1 : 2)} ${unit}`;
    current /= 1024;
  }
  return `${current.toFixed(1)} PB`;
}

export default { render };
