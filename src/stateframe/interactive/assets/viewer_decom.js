const ROW_HEIGHT = 32;
const HEADER_HEIGHT = 42;
const OVERSCAN = 8;
const SEARCH_DEBOUNCE_MS = 220;

function render({ model, el, signal }) {
  const payload = model.get("payload");
  let state = normalizeState(model.get("state"), payload);
  const ui = {
    menuColumnId: null,
    showColumns: true,
    showInspector: true,
    inspectorMode: "column",
    gridScrollLeft: 0,
    gridScrollTop: 0,
    columnPanelScrollTop: 0,
    inspectorScrollTop: 0,
    restoringGridScroll: false,
    focus: null,
    searchDraft: state.globalSearch || "",
    searchTimer: null,
    activeMatchIndex: 0,
    lastGlobalSearch: state.globalSearch || "",
    pendingMatchScroll: false,
    saveBranchOpen: false,
    saveBranchName: "",
    saveBranchMessage: "",
    branchStatus: model.get("branch_status") || null,
  };

  el.classList.add("stateframe-viewer-host");
  el.style.setProperty("--stateframe-viewer-height", `${payload.view.height}px`);

  const root = document.createElement("div");
  root.className = "stateframe-viewer";
  el.replaceChildren(root);

  function setState(patch) {
    captureUiState();
    state = normalizeState({ ...state, ...patch }, payload);
    model.set("state", state);
    model.save_changes();
    draw();
  }

  function setUi(patch) {
    captureUiState();
    Object.assign(ui, patch);
    draw();
  }

  function onStateChange() {
    captureUiState();
    state = normalizeState(model.get("state"), payload);
    draw();
  }

  model.on("change:state", onStateChange);
  model.on("change:branch_status", onBranchStatus);
  signal.addEventListener("abort", () => {
    model.off("change:state", onStateChange);
    model.off("change:branch_status", onBranchStatus);
    if (ui.searchTimer) clearTimeout(ui.searchTimer);
  });

  function onBranchStatus() {
    ui.branchStatus = model.get("branch_status") || null;
    draw();
  }

  function draw() {
    const computed = computeRows(payload, state);
    const query = state.globalSearch || "";
    if (query !== ui.lastGlobalSearch) {
      ui.activeMatchIndex = 0;
      ui.lastGlobalSearch = query;
      ui.searchDraft = query;
      ui.pendingMatchScroll = Boolean(query);
    }
    if (!computed.matches.length) {
      ui.activeMatchIndex = 0;
    } else {
      ui.activeMatchIndex = Math.min(ui.activeMatchIndex, computed.matches.length - 1);
    }
    const visibleColumns = getVisibleColumns(payload, state);
    const selectedColumn = getColumn(payload, state.selectedColumnId) || visibleColumns[0] || payload.columns[0];
    if (selectedColumn && state.selectedColumnId !== selectedColumn.id) {
      state.selectedColumnId = selectedColumn.id;
    }

    root.innerHTML = "";
    root.appendChild(renderToolbar(payload, state, computed, setState, setUi, ui));
    if (ui.branchStatus?.status) {
      root.appendChild(renderBranchStatus(ui, setUi));
    }
    root.appendChild(renderActiveBar(payload, state, computed, setState));

    const workspace = document.createElement("div");
    workspace.className = "stateframe-workspace";
    workspace.style.gridTemplateColumns = workspaceColumns(ui);

    if (ui.showColumns) {
      workspace.appendChild(renderColumnPanel(payload, state, setState, setUi, ui));
    }

    workspace.appendChild(renderGrid(payload, state, computed, setState, setUi, ui));
    if (ui.showInspector) {
      workspace.appendChild(renderInspector(payload, state, selectedColumn, setState, setUi, ui));
    }
    root.appendChild(workspace);
    if (ui.saveBranchOpen) {
      root.appendChild(renderSaveBranchDialog(model, setUi, ui));
    }
    requestAnimationFrame(() => {
      restoreFocus();
      if (ui.pendingMatchScroll) {
        requestAnimationFrame(() => {
          scrollToActiveMatch(computed);
          ui.pendingMatchScroll = false;
        });
      }
    });
  }

  function captureUiState() {
    const grid = root.querySelector(".stateframe-grid-scroll");
    if (grid) {
      ui.gridScrollLeft = grid.scrollLeft;
      ui.gridScrollTop = grid.scrollTop;
    }
    const columnPanel = root.querySelector(".stateframe-column-panel");
    if (columnPanel) {
      ui.columnPanelScrollTop = columnPanel.scrollTop;
    }
    const inspector = root.querySelector(".stateframe-inspector");
    if (inspector) {
      ui.inspectorScrollTop = inspector.scrollTop;
    }
    const active = root.ownerDocument.activeElement;
    if (active && root.contains(active) && active.dataset?.focusKey) {
      const selection = readSelection(active);
      ui.focus = {
        key: active.dataset.focusKey,
        start: selection.start,
        end: selection.end,
      };
    } else {
      ui.focus = null;
    }
  }

  function restoreFocus() {
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

  function scrollToActiveMatch(computed) {
    const match = computed.matches[ui.activeMatchIndex];
    const scroll = root.querySelector(".stateframe-grid-scroll");
    if (!match || !scroll) return;

    const visibleColumns = getVisibleColumns(payload, state);
    let left = state.showIndex ? 74 : 0;
    for (const column of visibleColumns) {
      if (column.id === match.columnId) break;
      left += state.widths[column.id] || initialWidth(column);
    }

    ui.restoringGridScroll = true;
    scroll.scrollLeft = Math.max(0, left - 24);
    scroll.scrollTop = Math.max(0, HEADER_HEIGHT + match.virtualIndex * ROW_HEIGHT - ROW_HEIGHT * 2);
    ui.gridScrollLeft = scroll.scrollLeft;
    ui.gridScrollTop = scroll.scrollTop;
    requestAnimationFrame(() => {
      ui.restoringGridScroll = false;
    });
  }

  draw();
}

function workspaceColumns(ui) {
  const columns = [];
  if (ui.showColumns) columns.push("220px");
  columns.push("minmax(280px, 1fr)");
  if (ui.showInspector) columns.push("320px");
  return columns.join(" ");
}

function normalizeState(raw, payload) {
  const allIds = payload.columns.map((column) => column.id);
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
  const widths = { ...(raw?.widths || {}) };
  for (const column of payload.columns) {
    if (!widths[column.id]) {
      widths[column.id] = initialWidth(column);
    }
  }
  return {
    columnOrder,
    hiddenColumnIds,
    sorts,
    filters: raw?.filters || {},
    globalSearch: raw?.globalSearch || "",
    selectedColumnId: allIds.includes(raw?.selectedColumnId) ? raw.selectedColumnId : allIds[0] || null,
    showIndex: raw?.showIndex !== false,
    widths,
  };
}

function renderToolbar(payload, state, computed, setState, setUi, ui) {
  const toolbar = document.createElement("div");
  toolbar.className = "stateframe-toolbar";

  const titleGroup = document.createElement("div");
  titleGroup.className = "stateframe-title-group";

  const title = document.createElement("div");
  title.className = "stateframe-title";
  title.textContent = payload.title;

  const subtitle = document.createElement("div");
  subtitle.className = "stateframe-subtitle";
  subtitle.textContent = `${formatInt(computed.indices.length)} of ${formatInt(payload.view.displayed_row_count)} rows`;
  if (payload.view.truncated) {
    subtitle.textContent += ` shown from ${formatInt(payload.view.row_count)} total`;
  }

  titleGroup.append(title, subtitle);

  const searchGroup = document.createElement("div");
  searchGroup.className = "stateframe-search-group";

  const search = document.createElement("input");
  search.className = "stateframe-search";
  search.dataset.focusKey = "global-search";
  search.type = "search";
  search.placeholder = "Find and filter visible data";
  search.value = ui.searchDraft ?? state.globalSearch ?? "";

  function commitSearch(value) {
    const nextValue = String(value || "");
    ui.searchDraft = nextValue;
    ui.activeMatchIndex = 0;
    ui.pendingMatchScroll = Boolean(nextValue.trim());
    setState({ globalSearch: nextValue });
  }

  function navigateMatch(delta) {
    if (!computed.matches.length) return;
    ui.activeMatchIndex = positiveModulo(ui.activeMatchIndex + delta, computed.matches.length);
    ui.pendingMatchScroll = true;
    const match = computed.matches[ui.activeMatchIndex];
    setState({ selectedColumnId: match.columnId });
  }

  search.addEventListener("input", (event) => {
    ui.searchDraft = event.target.value;
    if (ui.searchTimer) clearTimeout(ui.searchTimer);
    ui.searchTimer = setTimeout(() => {
      ui.searchTimer = null;
      commitSearch(ui.searchDraft);
    }, SEARCH_DEBOUNCE_MS);
  });
  search.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      if (ui.searchTimer) clearTimeout(ui.searchTimer);
      ui.searchTimer = null;
      if ((ui.searchDraft || "") !== (state.globalSearch || "")) {
        commitSearch(ui.searchDraft);
      } else {
        navigateMatch(event.shiftKey ? -1 : 1);
      }
    }
    if (event.key === "Escape") {
      event.preventDefault();
      if (ui.searchTimer) clearTimeout(ui.searchTimer);
      ui.searchTimer = null;
      commitSearch("");
    }
  });

  const matchCount = document.createElement("span");
  matchCount.className = "stateframe-match-count";
  if (state.globalSearch) {
    matchCount.textContent = computed.matches.length
      ? `${ui.activeMatchIndex + 1}/${computed.matches.length}`
      : "0 matches";
  } else {
    matchCount.textContent = "Find";
  }

  const previousMatch = button("Prev", () => navigateMatch(-1));
  previousMatch.disabled = !computed.matches.length;
  const nextMatch = button("Next", () => navigateMatch(1));
  nextMatch.disabled = !computed.matches.length;

  searchGroup.append(search, matchCount, previousMatch, nextMatch);

  const buttons = document.createElement("div");
  buttons.className = "stateframe-toolbar-buttons";

  buttons.appendChild(toggleButton("Columns", ui.showColumns, () => {
    setUi({ showColumns: !ui.showColumns });
  }));

  buttons.appendChild(toggleButton("Inspector", ui.showInspector, () => {
    setUi({ showInspector: !ui.showInspector });
  }));

  buttons.appendChild(toggleButton("Ledger", ui.showInspector && ui.inspectorMode === "ledger", () => {
    setUi({ showInspector: true, inspectorMode: ui.inspectorMode === "ledger" ? "column" : "ledger" });
  }));

  buttons.appendChild(button(state.showIndex ? "Index on" : "Index off", () => {
    setState({ showIndex: !state.showIndex });
  }));

  buttons.appendChild(button("Clear", () => {
    if (ui.searchTimer) clearTimeout(ui.searchTimer);
    ui.searchTimer = null;
    ui.searchDraft = "";
    setState({
      sorts: [],
      filters: {},
      globalSearch: "",
      hiddenColumnIds: [],
    });
  }));

  buttons.appendChild(button("CSV", () => {
    exportCsv(payload, state, computed);
  }));

  buttons.appendChild(button("Save branch", () => {
    setUi({ saveBranchOpen: true, branchStatus: null });
  }));

  toolbar.append(titleGroup, searchGroup, buttons);
  return toolbar;
}

function renderBranchStatus(ui, setUi) {
  const bar = document.createElement("div");
  bar.className = `stateframe-branch-status is-${ui.branchStatus.status}`;
  const text = document.createElement("span");
  text.textContent = ui.branchStatus.status === "saved"
    ? `Saved branch: ${ui.branchStatus.title || ui.branchStatus.entry_id || ""}`
    : `Branch save failed: ${ui.branchStatus.message || "Unknown error"}`;
  const close = tinyButton("dismiss", () => setUi({ branchStatus: null }));
  bar.append(text, close);
  return bar;
}

function renderSaveBranchDialog(model, setUi, ui) {
  const overlay = document.createElement("div");
  overlay.className = "stateframe-dialog-overlay";

  const dialog = document.createElement("div");
  dialog.className = "stateframe-dialog";

  const title = document.createElement("div");
  title.className = "stateframe-dialog-title";
  title.textContent = "Save Branch";

  const name = document.createElement("input");
  name.className = "stateframe-dialog-input";
  name.type = "text";
  name.placeholder = "Branch name";
  name.value = ui.saveBranchName || "";
  name.dataset.focusKey = "save-branch-name";
  name.addEventListener("input", (event) => {
    ui.saveBranchName = event.target.value;
  });

  const message = document.createElement("textarea");
  message.className = "stateframe-dialog-textarea";
  message.placeholder = "Message";
  message.value = ui.saveBranchMessage || "";
  message.addEventListener("input", (event) => {
    ui.saveBranchMessage = event.target.value;
  });

  const actions = document.createElement("div");
  actions.className = "stateframe-dialog-actions";
  const cancel = button("Cancel", () => {
    setUi({ saveBranchOpen: false });
  });
  const save = button("Save", () => {
    const request = {
      nonce: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      name: ui.saveBranchName || "",
      message: ui.saveBranchMessage || "",
    };
    model.set("branch_request", request);
    model.save_changes();
    setUi({
      saveBranchOpen: false,
      saveBranchName: "",
      saveBranchMessage: "",
    });
  });
  actions.append(cancel, save);

  dialog.append(title, name, message, actions);
  overlay.appendChild(dialog);
  return overlay;
}

function renderActiveBar(payload, state, computed, setState) {
  const active = document.createElement("div");
  active.className = "stateframe-active-bar";

  const chips = [];
  if (state.globalSearch) {
    chips.push({
      label: `search: ${state.globalSearch}`,
      clear: () => setState({ globalSearch: "" }),
    });
  }
  for (const sort of state.sorts) {
    const column = getColumn(payload, sort.id);
    if (column) {
      chips.push({
        label: `sort ${column.display_name} ${sort.direction}`,
        clear: () => setState({ sorts: state.sorts.filter((item) => item.id !== sort.id) }),
      });
    }
  }
  for (const [columnId, filterSpec] of Object.entries(state.filters || {})) {
    const column = getColumn(payload, columnId);
    if (column) {
      chips.push({
        label: `filter ${column.display_name}: ${describeFilter(filterSpec)}`,
        clear: () => {
          const filters = { ...state.filters };
          delete filters[columnId];
          setState({ filters });
        },
      });
    }
  }
  if (state.hiddenColumnIds.length) {
    chips.push({
      label: `${state.hiddenColumnIds.length} hidden columns`,
      clear: () => setState({ hiddenColumnIds: [] }),
    });
  }

  const count = document.createElement("span");
  count.className = "stateframe-active-count";
  count.textContent = `${formatInt(computed.indices.length)} rows`;
  active.appendChild(count);

  for (const chip of chips) {
    const chipEl = document.createElement("button");
    chipEl.className = "stateframe-chip";
    chipEl.type = "button";
    chipEl.textContent = chip.label;
    chipEl.title = "Clear this state";
    chipEl.addEventListener("click", chip.clear);
    active.appendChild(chipEl);
  }

  return active;
}

function renderColumnPanel(payload, state, setState, setUi, ui) {
  const panel = document.createElement("aside");
  panel.className = "stateframe-column-panel";

  const heading = document.createElement("div");
  heading.className = "stateframe-panel-heading";
  const headingText = document.createElement("span");
  headingText.textContent = "Columns";
  heading.append(
    headingText,
    tinyButton("collapse", () => setUi({ showColumns: false })),
  );
  panel.appendChild(heading);

  const list = document.createElement("div");
  list.className = "stateframe-column-list";

  const ordered = getOrderedColumns(payload, state);
  for (const column of ordered) {
    const hidden = state.hiddenColumnIds.includes(column.id);
    const item = document.createElement("div");
    item.className = "stateframe-column-item";
    if (hidden) item.classList.add("is-hidden");
    if (state.selectedColumnId === column.id) item.classList.add("is-selected");

    const name = document.createElement("button");
    name.className = "stateframe-column-name";
    name.type = "button";
    name.textContent = column.display_name;
    name.addEventListener("click", () => {
      setState({ selectedColumnId: column.id });
    });

    const meta = document.createElement("span");
    meta.className = "stateframe-column-meta";
    meta.textContent = column.semantic_type || "unknown";

    const actions = document.createElement("div");
    actions.className = "stateframe-column-actions";
    actions.appendChild(tinyButton("up", () => moveColumn(column.id, -1, state, setState)));
    actions.appendChild(tinyButton("down", () => moveColumn(column.id, 1, state, setState)));
    actions.appendChild(tinyButton(hidden ? "show" : "hide", () => {
      const hiddenIds = hidden
        ? state.hiddenColumnIds.filter((id) => id !== column.id)
        : [...state.hiddenColumnIds, column.id];
      setState({ hiddenColumnIds: hiddenIds, selectedColumnId: column.id });
    }));

    item.append(name, meta, actions);
    list.appendChild(item);
  }

  panel.appendChild(list);
  panel.addEventListener("scroll", () => {
    ui.columnPanelScrollTop = panel.scrollTop;
  });
  requestAnimationFrame(() => {
    panel.scrollTop = ui.columnPanelScrollTop || 0;
  });
  return panel;
}

function renderGrid(payload, state, computed, setState, setUi, ui) {
  const shell = document.createElement("section");
  shell.className = "stateframe-grid-shell";

  const scroll = document.createElement("div");
  scroll.className = "stateframe-grid-scroll";

  const visibleColumns = getVisibleColumns(payload, state);
  const template = gridTemplate(visibleColumns, state);
  const minWidth = gridWidth(visibleColumns, state);

  const header = document.createElement("div");
  header.className = "stateframe-grid-header";
  header.style.gridTemplateColumns = template;
  header.style.minWidth = `${minWidth}px`;

  if (state.showIndex) {
    const indexHeader = document.createElement("div");
    indexHeader.className = "stateframe-header-cell stateframe-index-cell";
    indexHeader.textContent = "#";
    header.appendChild(indexHeader);
  }

  for (const column of visibleColumns) {
    header.appendChild(renderHeaderCell(column, payload, state, setState, setUi, ui));
  }

  const virtual = document.createElement("div");
  virtual.className = "stateframe-grid-virtual";
  virtual.style.minWidth = `${minWidth}px`;
  virtual.style.height = `${computed.indices.length * ROW_HEIGHT}px`;
  const activeMatch = computed.matches[ui.activeMatchIndex] || null;
  const searchNeedle = (state.globalSearch || "").trim().toLowerCase();

  function renderRows() {
    virtual.innerHTML = "";
    const offset = Math.max(0, scroll.scrollTop - HEADER_HEIGHT);
    const start = Math.max(0, Math.floor(offset / ROW_HEIGHT) - OVERSCAN);
    const visibleCount = Math.ceil(scroll.clientHeight / ROW_HEIGHT) + OVERSCAN * 2;
    const end = Math.min(computed.indices.length, start + visibleCount);

    for (let virtualIndex = start; virtualIndex < end; virtualIndex += 1) {
      const rowIndex = computed.indices[virtualIndex];
      const row = payload.rows[rowIndex];
      const rowEl = document.createElement("div");
      rowEl.className = "stateframe-row";
      rowEl.style.top = `${virtualIndex * ROW_HEIGHT}px`;
      rowEl.style.gridTemplateColumns = template;
      rowEl.style.minWidth = `${minWidth}px`;

      if (state.showIndex) {
        const indexCell = document.createElement("div");
        indexCell.className = "stateframe-cell stateframe-index-cell";
        indexCell.textContent = formatValue(payload.index[rowIndex]);
        rowEl.appendChild(indexCell);
      }

      for (const column of visibleColumns) {
        const cell = document.createElement("div");
        cell.className = "stateframe-cell";
        if (isNumericColumn(column)) cell.classList.add("is-numeric");
        const value = row[column.position];
        if (value === null || value === "") cell.classList.add("is-null");
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
        cell.textContent = formatValue(value);
        cell.title = formatValue(value);
        rowEl.appendChild(cell);
      }

      virtual.appendChild(rowEl);
    }
  }

  scroll.addEventListener("scroll", () => {
    if (!ui.restoringGridScroll) {
      ui.gridScrollLeft = scroll.scrollLeft;
      ui.gridScrollTop = scroll.scrollTop;
    }
    renderRows();
  });
  scroll.append(header, virtual);
  shell.appendChild(scroll);
  requestAnimationFrame(() => {
    const maxLeft = Math.max(0, scroll.scrollWidth - scroll.clientWidth);
    const maxTop = Math.max(0, scroll.scrollHeight - scroll.clientHeight);
    ui.restoringGridScroll = true;
    scroll.scrollLeft = Math.min(ui.gridScrollLeft || 0, maxLeft);
    scroll.scrollTop = Math.min(ui.gridScrollTop || 0, maxTop);
    renderRows();
    requestAnimationFrame(() => {
      ui.restoringGridScroll = false;
      ui.gridScrollLeft = scroll.scrollLeft;
      ui.gridScrollTop = scroll.scrollTop;
    });
  });
  return shell;
}

function renderHeaderCell(column, payload, state, setState, setUi, ui) {
  const cell = document.createElement("div");
  cell.className = "stateframe-header-cell";
  cell.draggable = true;
  if (state.selectedColumnId === column.id) cell.classList.add("is-selected");
  if (state.filters[column.id]) cell.classList.add("is-filtered");

  cell.addEventListener("dragstart", (event) => {
    event.dataTransfer.setData("text/plain", column.id);
  });
  cell.addEventListener("dragover", (event) => event.preventDefault());
  cell.addEventListener("drop", (event) => {
    event.preventDefault();
    const movingId = event.dataTransfer.getData("text/plain");
    reorderColumn(movingId, column.id, state, setState);
  });

  const label = document.createElement("button");
  label.className = "stateframe-header-label";
  label.type = "button";
  label.title = "Click to sort. Shift-click to add to a multi-column sort.";
  label.addEventListener("click", (event) => {
    const nextSorts = nextSortState(column.id, state.sorts, event.shiftKey);
    setState({ sorts: nextSorts, selectedColumnId: column.id });
  });

  const name = document.createElement("span");
  name.className = "stateframe-header-name";
  name.textContent = column.display_name;

  const badges = document.createElement("span");
  badges.className = "stateframe-header-badges";
  const sort = state.sorts.find((item) => item.id === column.id);
  if (sort) {
    const sortBadge = document.createElement("span");
    sortBadge.className = "stateframe-badge";
    sortBadge.textContent = sort.direction;
    badges.appendChild(sortBadge);
  }
  if (state.filters[column.id]) {
    const filterBadge = document.createElement("span");
    filterBadge.className = "stateframe-badge";
    filterBadge.textContent = "filter";
    badges.appendChild(filterBadge);
  }

  label.append(name, badges);

  const menu = document.createElement("button");
  menu.className = "stateframe-header-menu-button";
  menu.type = "button";
  menu.textContent = "...";
  menu.title = "Column actions";
  menu.addEventListener("click", (event) => {
    event.stopPropagation();
    setUi({ menuColumnId: ui.menuColumnId === column.id ? null : column.id });
  });

  const resizer = document.createElement("div");
  resizer.className = "stateframe-resizer";
  resizer.addEventListener("mousedown", (event) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = state.widths[column.id] || initialWidth(column);
    function onMove(moveEvent) {
      const next = Math.max(88, startWidth + moveEvent.clientX - startX);
      setState({ widths: { ...state.widths, [column.id]: next } });
    }
    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  });

  cell.append(label, menu, resizer);

  if (ui.menuColumnId === column.id) {
    cell.appendChild(renderColumnMenu(column, payload, state, setState));
  }

  return cell;
}

function renderColumnMenu(column, payload, state, setState) {
  const menu = document.createElement("div");
  menu.className = "stateframe-column-menu";

  const title = document.createElement("div");
  title.className = "stateframe-menu-title";
  title.textContent = column.display_name;
  menu.appendChild(title);

  const row = document.createElement("div");
  row.className = "stateframe-menu-row";
  row.append(
    button("Asc", () => setColumnSort(column.id, "asc", state, setState)),
    button("Desc", () => setColumnSort(column.id, "desc", state, setState)),
    button("No sort", () => clearColumnSort(column.id, state, setState)),
  );
  menu.appendChild(row);

  const filter = document.createElement("input");
  filter.className = "stateframe-menu-input";
  filter.dataset.focusKey = `menu-filter-${column.id}`;
  filter.placeholder = "Filter this column";
  filter.value = state.filters[column.id]?.value || "";
  filter.addEventListener("input", (event) => {
    updateFilter(column, { kind: "text", mode: "contains", value: event.target.value }, state, setState);
  });
  menu.appendChild(filter);

  const row2 = document.createElement("div");
  row2.className = "stateframe-menu-row";
  row2.append(
    button("Empty", () => updateFilter(column, { kind: "empty" }, state, setState)),
    button("Not empty", () => updateFilter(column, { kind: "not_empty" }, state, setState)),
    button("Clear filter", () => clearFilter(column.id, state, setState)),
  );
  menu.appendChild(row2);

  const row3 = document.createElement("div");
  row3.className = "stateframe-menu-row";
  row3.append(
    button("Hide", () => {
      if (!state.hiddenColumnIds.includes(column.id)) {
        setState({ hiddenColumnIds: [...state.hiddenColumnIds, column.id] });
      }
    }),
    button("Left", () => moveColumn(column.id, -1, state, setState)),
    button("Right", () => moveColumn(column.id, 1, state, setState)),
  );
  menu.appendChild(row3);

  return menu;
}

function renderInspector(payload, state, column, setState, setUi, ui) {
  if (ui.inspectorMode === "ledger") {
    return renderLedgerInspector(payload, setUi, ui);
  }

  const inspector = document.createElement("aside");
  inspector.className = "stateframe-inspector";

  if (!column) {
    inspector.textContent = "No columns";
    return inspector;
  }

  const header = document.createElement("div");
  header.className = "stateframe-inspector-header";

  const title = document.createElement("div");
  title.className = "stateframe-inspector-title";
  title.textContent = column.display_name;

  header.append(
    title,
    tinyButton("ledger", () => setUi({ inspectorMode: "ledger" })),
    tinyButton("collapse", () => setUi({ showInspector: false })),
  );

  const semantic = document.createElement("div");
  semantic.className = "stateframe-inspector-subtitle";
  semantic.textContent = `${column.semantic_type || "unknown"} / ${column.dtype || "dtype unknown"}`;

  inspector.append(header, semantic);
  inspector.appendChild(renderStats(column));
  inspector.appendChild(renderInspectorFilter(column, state, setState));

  if (column.histogram) {
    inspector.appendChild(section("Spread", renderHistogram(column.histogram)));
  }
  if (column.binary_profile) {
    inspector.appendChild(section("Binary flag", renderBinary(column.binary_profile)));
  }
  if (column.datetime_range) {
    inspector.appendChild(section("Time range", keyValueList(column.datetime_range)));
  }
  if (column.top_values && column.top_values.length) {
    inspector.appendChild(section("Top values", renderTopValues(column.top_values)));
  }
  if (column.issues && column.issues.length) {
    inspector.appendChild(section("Issues", renderBullets(column.issues.map((issue) => issue.title))));
  }
  if (column.insights && column.insights.length) {
    inspector.appendChild(section("Insights", renderBullets(column.insights.map((insight) => insight.message))));
  }
  if (column.recommendations && column.recommendations.length) {
    inspector.appendChild(section("Next lenses", renderRecommendations(column.recommendations)));
  }

  inspector.addEventListener("scroll", () => {
    ui.inspectorScrollTop = inspector.scrollTop;
  });
  requestAnimationFrame(() => {
    inspector.scrollTop = ui.inspectorScrollTop || 0;
  });
  return inspector;
}

function renderLedgerInspector(payload, setUi, ui) {
  const inspector = document.createElement("aside");
  inspector.className = "stateframe-inspector";

  const ledger = payload.ledger || {};
  const entries = ledger.entries || [];
  const states = ledger.states || {};

  const header = document.createElement("div");
  header.className = "stateframe-inspector-header";

  const title = document.createElement("div");
  title.className = "stateframe-inspector-title";
  title.textContent = "Lens ledger";

  header.append(
    title,
    tinyButton("columns", () => setUi({ inspectorMode: "column" })),
    tinyButton("collapse", () => setUi({ showInspector: false })),
  );

  const subtitle = document.createElement("div");
  subtitle.className = "stateframe-inspector-subtitle";
  subtitle.textContent = `${entries.length} entries / ${Object.keys(states).length} dataframe states`;

  inspector.append(header, subtitle);

  if (!entries.length) {
    const empty = document.createElement("div");
    empty.className = "stateframe-empty-state";
    empty.textContent = "No ledger entries yet.";
    inspector.appendChild(empty);
    return inspector;
  }

  const tree = document.createElement("div");
  tree.className = "stateframe-ledger-tree";
  const depths = ledgerDepths(entries);
  for (const entry of entries) {
    const item = document.createElement("div");
    item.className = "stateframe-ledger-entry";
    if (entry.id === ledger.active_entry_id) item.classList.add("is-active");
    item.style.paddingLeft = `${8 + (depths.get(entry.id) || 0) * 14}px`;

    const line = document.createElement("div");
    line.className = "stateframe-ledger-line";
    const kind = document.createElement("span");
    kind.className = "stateframe-ledger-kind";
    kind.textContent = entry.kind;
    const name = document.createElement("span");
    name.className = "stateframe-ledger-name";
    name.textContent = entry.title;
    line.append(kind, name);

    const meta = document.createElement("div");
    meta.className = "stateframe-ledger-meta";
    const state = entry.state_id ? " / state" : "";
    meta.textContent = `${entry.operation}${state}`;

    item.append(line, meta);
    tree.appendChild(item);
  }
  inspector.appendChild(section("History", tree));

  const active = entries.find((entry) => entry.id === ledger.active_entry_id) || entries[entries.length - 1];
  if (active?.options?.length) {
    inspector.appendChild(section("Options From Active Step", renderRecommendations(active.options)));
  }

  inspector.addEventListener("scroll", () => {
    ui.inspectorScrollTop = inspector.scrollTop;
  });
  requestAnimationFrame(() => {
    inspector.scrollTop = ui.inspectorScrollTop || 0;
  });
  return inspector;
}

function renderStats(column) {
  const stats = document.createElement("div");
  stats.className = "stateframe-stats-grid";
  const items = [
    ["Missing", `${formatInt(column.missing_count)} (${formatPercent(column.missing_ratio)})`],
    ["Unique", `${formatInt(column.distinct_count)} (${formatPercent(column.distinct_ratio)})`],
    ["Non-null", formatInt(column.non_null_count)],
    ["Role", column.role || "feature"],
    ["Confidence", formatPercent(column.semantic_confidence)],
  ];
  for (const [label, value] of items) {
    const card = document.createElement("div");
    card.className = "stateframe-stat";
    const statLabel = document.createElement("div");
    statLabel.className = "stateframe-stat-label";
    statLabel.textContent = label;
    const statValue = document.createElement("div");
    statValue.className = "stateframe-stat-value";
    statValue.textContent = value;
    card.append(statLabel, statValue);
    stats.appendChild(card);
  }
  return stats;
}

function renderInspectorFilter(column, state, setState) {
  const wrapper = document.createElement("div");
  wrapper.className = "stateframe-inspector-filter";

  const label = document.createElement("div");
  label.className = "stateframe-section-title";
  label.textContent = "Column filter";
  wrapper.appendChild(label);

  if (isNumericColumn(column)) {
    const row = document.createElement("div");
    row.className = "stateframe-filter-row";
    const min = document.createElement("input");
    min.dataset.focusKey = `inspector-filter-${column.id}-min`;
    min.type = "number";
    min.placeholder = "Min";
    min.value = state.filters[column.id]?.min || "";
    const max = document.createElement("input");
    max.dataset.focusKey = `inspector-filter-${column.id}-max`;
    max.type = "number";
    max.placeholder = "Max";
    max.value = state.filters[column.id]?.max || "";
    const apply = button("Apply", () => {
      updateFilter(column, { kind: "numeric", min: min.value, max: max.value }, state, setState);
    });
    row.append(min, max, apply);
    wrapper.appendChild(row);
  } else if (isDatetimeColumn(column)) {
    const row = document.createElement("div");
    row.className = "stateframe-filter-row";
    const min = document.createElement("input");
    min.dataset.focusKey = `inspector-filter-${column.id}-from`;
    min.type = "text";
    min.placeholder = "From";
    min.value = state.filters[column.id]?.min || "";
    const max = document.createElement("input");
    max.dataset.focusKey = `inspector-filter-${column.id}-to`;
    max.type = "text";
    max.placeholder = "To";
    max.value = state.filters[column.id]?.max || "";
    const apply = button("Apply", () => {
      updateFilter(column, { kind: "datetime", min: min.value, max: max.value }, state, setState);
    });
    row.append(min, max, apply);
    wrapper.appendChild(row);
  } else {
    const input = document.createElement("input");
    input.className = "stateframe-inspector-input";
    input.dataset.focusKey = `inspector-filter-${column.id}`;
    input.type = "search";
    input.placeholder = "Contains";
    input.value = state.filters[column.id]?.value || "";
    input.addEventListener("input", (event) => {
      updateFilter(column, { kind: "text", mode: "contains", value: event.target.value }, state, setState);
    });
    wrapper.appendChild(input);
  }

  const quick = document.createElement("div");
  quick.className = "stateframe-menu-row";
  quick.append(
    button("Empty", () => updateFilter(column, { kind: "empty" }, state, setState)),
    button("Not empty", () => updateFilter(column, { kind: "not_empty" }, state, setState)),
    button("Clear", () => clearFilter(column.id, state, setState)),
  );
  wrapper.appendChild(quick);
  return wrapper;
}

function renderHistogram(histogram) {
  const chart = document.createElement("div");
  chart.className = "stateframe-histogram";
  for (const bin of histogram.bins || []) {
    const bar = document.createElement("div");
    bar.className = "stateframe-histogram-bar";
    const height = histogram.max_count ? Math.max(4, (bin.count / histogram.max_count) * 70) : 4;
    bar.style.height = `${height}px`;
    bar.title = `${formatNumber(bin.lower)} to ${formatNumber(bin.upper)}: ${formatInt(bin.count)}`;
    chart.appendChild(bar);
  }
  return chart;
}

function renderBinary(binary) {
  const wrapper = document.createElement("div");
  wrapper.className = "stateframe-detail-block";
  wrapper.appendChild(keyValueList({
    kind: binary.kind,
    confidence: formatPercent(binary.confidence),
    null_policy: binary.null_policy,
    ambiguous: binary.ambiguous ? "yes" : "no",
  }));
  if (binary.evidence && binary.evidence.length) {
    wrapper.appendChild(renderBullets(binary.evidence));
  }
  return wrapper;
}

function renderTopValues(topValues) {
  const list = document.createElement("div");
  list.className = "stateframe-top-values";
  for (const item of topValues.slice(0, 12)) {
    const row = document.createElement("div");
    row.className = "stateframe-top-value";
    const value = document.createElement("span");
    value.className = "stateframe-top-value-name";
    value.textContent = formatValue(item.value);
    const count = document.createElement("span");
    count.className = "stateframe-top-value-count";
    count.textContent = `${formatInt(item.count)} ${item.ratio !== undefined ? formatPercent(item.ratio) : ""}`;
    row.append(value, count);
    list.appendChild(row);
  }
  return list;
}

function renderRecommendations(recommendations) {
  const list = document.createElement("div");
  list.className = "stateframe-recommendations";
  for (const recommendation of recommendations.slice(0, 6)) {
    const item = document.createElement("div");
    item.className = "stateframe-recommendation";
    const title = document.createElement("div");
    title.className = "stateframe-recommendation-title";
    title.textContent = recommendation.title;
    const code = document.createElement("code");
    code.textContent = recommendation.code || recommendation.lens;
    item.append(title, code);
    list.appendChild(item);
  }
  return list;
}

function ledgerDepths(entries) {
  const byId = new Map(entries.map((entry) => [entry.id, entry]));
  const depths = new Map();
  function depthFor(entry) {
    if (!entry?.parent_id || !byId.has(entry.parent_id)) return 0;
    if (depths.has(entry.id)) return depths.get(entry.id);
    const depth = depthFor(byId.get(entry.parent_id)) + 1;
    depths.set(entry.id, depth);
    return depth;
  }
  for (const entry of entries) {
    depths.set(entry.id, depthFor(entry));
  }
  return depths;
}

function section(title, content) {
  const wrapper = document.createElement("section");
  wrapper.className = "stateframe-section";
  const heading = document.createElement("div");
  heading.className = "stateframe-section-title";
  heading.textContent = title;
  wrapper.append(heading, content);
  return wrapper;
}

function keyValueList(data) {
  const list = document.createElement("dl");
  list.className = "stateframe-kv";
  for (const [key, value] of Object.entries(data || {})) {
    const dt = document.createElement("dt");
    dt.textContent = key.replaceAll("_", " ");
    const dd = document.createElement("dd");
    dd.textContent = formatValue(value);
    list.append(dt, dd);
  }
  return list;
}

function renderBullets(items) {
  const list = document.createElement("ul");
  list.className = "stateframe-bullets";
  for (const item of items.slice(0, 8)) {
    const li = document.createElement("li");
    li.textContent = item;
    list.appendChild(li);
  }
  return list;
}

function computeRows(payload, state) {
  let indices = payload.rows.map((_row, index) => index);
  const visibleColumns = getVisibleColumns(payload, state);

  const global = (state.globalSearch || "").trim().toLowerCase();
  if (global) {
    indices = indices.filter((rowIndex) => {
      const row = payload.rows[rowIndex];
      return visibleColumns.some((column) => {
        const value = row[column.position];
        return cellMatches(value, global);
      });
    });
  }

  const filters = state.filters || {};
  indices = indices.filter((rowIndex) => {
    const row = payload.rows[rowIndex];
    return Object.entries(filters).every(([columnId, filterSpec]) => {
      const column = getColumn(payload, columnId);
      if (!column) return true;
      return matchesFilter(row[column.position], column, filterSpec);
    });
  });

  if (state.sorts.length) {
    indices = [...indices].sort((leftIndex, rightIndex) => {
      const leftRow = payload.rows[leftIndex];
      const rightRow = payload.rows[rightIndex];
      for (const sort of state.sorts) {
        const column = getColumn(payload, sort.id);
        if (!column) continue;
        const comparison = compareValues(leftRow[column.position], rightRow[column.position], column);
        if (comparison !== 0) {
          return sort.direction === "desc" ? -comparison : comparison;
        }
      }
      return leftIndex - rightIndex;
    });
  }

  return {
    indices,
    matches: global ? findMatches(payload, visibleColumns, indices, global) : [],
  };
}

function findMatches(payload, visibleColumns, indices, needle) {
  const matches = [];
  for (let virtualIndex = 0; virtualIndex < indices.length; virtualIndex += 1) {
    const rowIndex = indices[virtualIndex];
    const row = payload.rows[rowIndex];
    for (const column of visibleColumns) {
      if (cellMatches(row[column.position], needle)) {
        matches.push({ rowIndex, virtualIndex, columnId: column.id });
      }
    }
  }
  return matches;
}

function cellMatches(value, needle) {
  return formatValue(value).toLowerCase().includes(needle);
}

function matchesFilter(value, column, filterSpec) {
  if (!filterSpec) return true;
  const kind = filterSpec.kind || "text";
  if (kind === "empty") {
    return value === null || value === "";
  }
  if (kind === "not_empty") {
    return value !== null && value !== "";
  }
  if (kind === "numeric") {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return false;
    if (filterSpec.min !== undefined && filterSpec.min !== "" && numeric < Number(filterSpec.min)) return false;
    if (filterSpec.max !== undefined && filterSpec.max !== "" && numeric > Number(filterSpec.max)) return false;
    return true;
  }
  if (kind === "datetime") {
    const time = Date.parse(value);
    if (!Number.isFinite(time)) return false;
    if (filterSpec.min && time < Date.parse(filterSpec.min)) return false;
    if (filterSpec.max && time > Date.parse(filterSpec.max)) return false;
    return true;
  }
  const needle = String(filterSpec.value || "").toLowerCase();
  if (!needle) return true;
  const haystack = formatValue(value).toLowerCase();
  if (filterSpec.mode === "equals") return haystack === needle;
  if (filterSpec.mode === "starts") return haystack.startsWith(needle);
  return haystack.includes(needle);
}

function compareValues(left, right, column) {
  if (left === null && right === null) return 0;
  if (left === null) return 1;
  if (right === null) return -1;
  if (isNumericColumn(column)) {
    const leftNumber = Number(left);
    const rightNumber = Number(right);
    if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
      return leftNumber - rightNumber;
    }
  }
  if (isDatetimeColumn(column)) {
    const leftDate = Date.parse(left);
    const rightDate = Date.parse(right);
    if (Number.isFinite(leftDate) && Number.isFinite(rightDate)) {
      return leftDate - rightDate;
    }
  }
  return String(left).localeCompare(String(right), undefined, { numeric: true, sensitivity: "base" });
}

function getOrderedColumns(payload, state) {
  const byId = new Map(payload.columns.map((column) => [column.id, column]));
  return state.columnOrder.map((id) => byId.get(id)).filter(Boolean);
}

function getVisibleColumns(payload, state) {
  const hidden = new Set(state.hiddenColumnIds || []);
  return getOrderedColumns(payload, state).filter((column) => !hidden.has(column.id));
}

function getColumn(payload, id) {
  return payload.columns.find((column) => column.id === id) || null;
}

function isNumericColumn(column) {
  return ["numeric", "amount", "numeric-like", "percentage", "proportion", "numeric_discrete"].includes(column.semantic_type);
}

function isDatetimeColumn(column) {
  return ["datetime", "datetime-like"].includes(column.semantic_type);
}

function gridTemplate(columns, state) {
  const parts = [];
  if (state.showIndex) parts.push("74px");
  for (const column of columns) {
    parts.push(`${state.widths[column.id] || initialWidth(column)}px`);
  }
  return parts.join(" ");
}

function gridWidth(columns, state) {
  const columnWidth = columns.reduce((total, column) => total + (state.widths[column.id] || initialWidth(column)), 0);
  return columnWidth + (state.showIndex ? 74 : 0);
}

function initialWidth(column) {
  const nameWidth = String(column.display_name || "").length * 9 + 52;
  if (isNumericColumn(column)) return clamp(nameWidth, 118, 210);
  if (isDatetimeColumn(column)) return clamp(nameWidth, 172, 250);
  if (["text", "json-like"].includes(column.semantic_type)) return clamp(nameWidth, 220, 380);
  return clamp(nameWidth, 136, 270);
}

function nextSortState(columnId, sorts, additive) {
  const existing = sorts.find((sort) => sort.id === columnId);
  const others = additive ? sorts.filter((sort) => sort.id !== columnId) : [];
  if (!existing) return [...others, { id: columnId, direction: "asc" }];
  if (existing.direction === "asc") return [...others, { id: columnId, direction: "desc" }];
  return others;
}

function setColumnSort(columnId, direction, state, setState) {
  const sorts = [{ id: columnId, direction }, ...state.sorts.filter((sort) => sort.id !== columnId)];
  setState({ sorts, selectedColumnId: columnId });
}

function clearColumnSort(columnId, state, setState) {
  setState({ sorts: state.sorts.filter((sort) => sort.id !== columnId), selectedColumnId: columnId });
}

function updateFilter(column, filterSpec, state, setState) {
  const filters = { ...state.filters };
  const emptyText = filterSpec.kind === "text" && !String(filterSpec.value || "").trim();
  const emptyNumeric = filterSpec.kind === "numeric" && !filterSpec.min && !filterSpec.max;
  const emptyDatetime = filterSpec.kind === "datetime" && !filterSpec.min && !filterSpec.max;
  if (emptyText || emptyNumeric || emptyDatetime) {
    delete filters[column.id];
  } else {
    filters[column.id] = filterSpec;
  }
  setState({ filters, selectedColumnId: column.id });
}

function clearFilter(columnId, state, setState) {
  const filters = { ...state.filters };
  delete filters[columnId];
  setState({ filters, selectedColumnId: columnId });
}

function moveColumn(columnId, delta, state, setState) {
  const order = [...state.columnOrder];
  const index = order.indexOf(columnId);
  if (index < 0) return;
  const next = clamp(index + delta, 0, order.length - 1);
  order.splice(index, 1);
  order.splice(next, 0, columnId);
  setState({ columnOrder: order, selectedColumnId: columnId });
}

function reorderColumn(movingId, targetId, state, setState) {
  if (!movingId || movingId === targetId) return;
  const order = state.columnOrder.filter((id) => id !== movingId);
  const targetIndex = order.indexOf(targetId);
  order.splice(targetIndex, 0, movingId);
  setState({ columnOrder: order, selectedColumnId: movingId });
}

function exportCsv(payload, state, computed) {
  const columns = getVisibleColumns(payload, state);
  const header = columns.map((column) => csvEscape(column.display_name)).join(",");
  const body = computed.indices.map((rowIndex) => {
    const row = payload.rows[rowIndex];
    return columns.map((column) => csvEscape(row[column.position])).join(",");
  });
  const blob = new Blob([[header, ...body].join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "stateframe_view.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function csvEscape(value) {
  const text = formatValue(value);
  if (/[",\n]/.test(text)) {
    return `"${text.replaceAll('"', '""')}"`;
  }
  return text;
}

function button(label, onClick) {
  const btn = document.createElement("button");
  btn.className = "stateframe-button";
  btn.type = "button";
  btn.textContent = label;
  btn.addEventListener("click", onClick);
  return btn;
}

function toggleButton(label, active, onClick) {
  const btn = button(label, onClick);
  btn.classList.add("stateframe-toggle-button");
  if (active) btn.classList.add("is-active");
  btn.setAttribute("aria-pressed", active ? "true" : "false");
  return btn;
}

function tinyButton(label, onClick) {
  const btn = document.createElement("button");
  btn.className = "stateframe-tiny-button";
  btn.type = "button";
  btn.textContent = label;
  btn.addEventListener("click", onClick);
  return btn;
}

function describeFilter(filterSpec) {
  if (!filterSpec) return "";
  if (filterSpec.kind === "empty") return "empty";
  if (filterSpec.kind === "not_empty") return "not empty";
  if (filterSpec.kind === "numeric") return `${filterSpec.min || "*"} to ${filterSpec.max || "*"}`;
  if (filterSpec.kind === "datetime") return `${filterSpec.min || "*"} to ${filterSpec.max || "*"}`;
  return filterSpec.value || "";
}

function formatValue(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return formatNumber(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

function formatNumber(value) {
  if (!Number.isFinite(value)) return "";
  const abs = Math.abs(value);
  if (abs >= 1000000 || (abs > 0 && abs < 0.001)) return value.toExponential(3);
  return Number.isInteger(value) ? String(value) : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function formatInt(value) {
  const number = Number(value || 0);
  return number.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return `${(number * 100).toFixed(number < 0.01 && number > 0 ? 2 : 1)}%`;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function positiveModulo(value, divisor) {
  return ((value % divisor) + divisor) % divisor;
}

function cssEscape(value) {
  if (globalThis.CSS?.escape) return globalThis.CSS.escape(value);
  return String(value).replace(/["\\]/g, "\\$&");
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

export default { render };
