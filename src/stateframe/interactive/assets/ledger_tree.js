function render({ model, el, signal }) {
  const payload = model.get("payload");
  let state = normalizeState(model.get("state"), payload);

  el.classList.add("stateframe-ledger-host");
  el.style.setProperty("--stateframe-ledger-height", `${payload.view.height}px`);

  const root = document.createElement("div");
  root.className = "stateframe-tree";
  el.replaceChildren(root);

  function setState(patch) {
    state = normalizeState({ ...state, ...patch }, payload);
    model.set("state", state);
    model.save_changes();
    draw();
  }

  function onStateChange() {
    state = normalizeState(model.get("state"), payload);
    draw();
  }

  model.on("change:state", onStateChange);
  signal.addEventListener("abort", () => model.off("change:state", onStateChange));

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
    root.appendChild(renderToolbar(payload, entries, state, setState));
    root.appendChild(renderStats(payload));

    const body = document.createElement("div");
    body.className = "stateframe-tree-body";
    body.appendChild(renderTreePanel(payload, filtered, selected, state, setState));
    body.appendChild(renderDetailPanel(payload, selected));
    root.appendChild(body);
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
  };
}

function renderToolbar(payload, entries, state, setState) {
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
  search.value = state.search || "";
  search.addEventListener("input", () => setState({ search: search.value }));

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
  const list = document.createElement("div");
  list.className = "stateframe-tree-list";

  for (const entry of entries) {
    const node = document.createElement("button");
    node.type = "button";
    node.className = "stateframe-tree-node";
    if (entry.id === selected?.id) node.classList.add("is-selected");
    if (entry.is_active) node.classList.add("is-active");
    if (pathIds.has(entry.id)) node.classList.add("is-in-path");
    node.style.paddingLeft = `${12 + (entry.depth || 0) * 18}px`;
    node.addEventListener("click", () => setState({ selectedEntryId: entry.id }));

    const line = document.createElement("div");
    line.className = "stateframe-tree-node-line";
    const kind = document.createElement("span");
    kind.className = "stateframe-tree-kind";
    kind.textContent = entry.kind || "entry";
    const name = document.createElement("span");
    name.className = "stateframe-tree-node-title";
    name.textContent = entry.title || entry.operation || entry.id;
    line.append(kind, name);

    const meta = document.createElement("div");
    meta.className = "stateframe-tree-node-meta";
    const stateText = entry.has_state ? " / state" : "";
    const children = entry.child_count ? ` / ${entry.child_count} child${entry.child_count === 1 ? "" : "ren"}` : "";
    meta.textContent = `${entry.operation || entry.kind}${stateText}${children}`;

    node.append(line, meta);
    list.appendChild(node);
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
  const query = String(state.search || "").trim().toLowerCase();
  return entries.filter((entry) => {
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
  });
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
