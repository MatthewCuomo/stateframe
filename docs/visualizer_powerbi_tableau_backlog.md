# Visualizer Control Backlog

This backlog tracks the gap between the current stateframe visualizer and the kind of direct, exploratory visual-building flow users expect from tools like Power BI and Tableau.

## Implemented In This Pass

- Field wells: make visual roles visible as assignable drop targets instead of only select controls.
- Draggable columns: let users drag column cards into compatible visual roles.
- Shared assignment behavior: use the same assignment rules for dropdowns, quick buttons, and drag/drop.
- Compatibility gating: disable quick assignment actions when a column does not fit the target role.
- Channel rollups: add Color and Facet top-N controls so overloaded legends or facet grids can be grouped or filtered without changing the X axis.
- Field-well quick actions: expose clear, rollup, legend, and sampling actions directly where the field is assigned.

## Near-Term Product Improvements

- Visual templates: preformatted recipes for common analytical views such as trend, profile, distribution, ranked bar, hierarchy, matrix, and combo views.
- Marks channels: add explicit role slots for color, size, label, detail, tooltip, facet row, and facet column where the visual supports them.
- Active encoding chips: show assigned fields as chips with replace, clear, duplicate, and reorder actions.
- Smart recommendations: score visual types and role mappings based on data type, cardinality, missingness, and selected analytical intent.
- Role-aware shelf layout: group fields by required encodings, optional encodings, marks, filters, and style controls.
- Cross-filtering: allow a selected mark in one visual to filter or highlight another visual.
- Drill paths: support click-through from aggregate marks into child categories, underlying rows, or value profiles.
- Dashboard canvas: compose multiple visuals, tables, and summary cards into a reusable analysis view.
- Saved visual states: persist named visual recipes as branch artifacts that can be compared, reused, and promoted.
- Calculated fields: add UI for bins, date parts, ratios, percent of total, rolling metrics, and conditional groupings.
- Parameter controls: expose user-adjustable thresholds, top N limits, measure selectors, and reference lines.
- Visual themes: reusable presets for axes, labels, color palettes, gridlines, legends, and density.
- Performance controls: show row counts, sampling mode, aggregation level, and render cost before expensive visuals run. Basic sampling controls are now available in the field well, but pre-render cost estimates are still needed.
- Query summary: display a compact trace of filters, grouping, aggregation, sampling, and visual encoding decisions.
- Keyboard flow: add command palette actions for assign field, clear shelf, switch visual, save view, and open value overview.

## Deeper Analysis Gaps To Keep Testing

- High-cardinality categories need search, reusable bucketing, and smarter automatic "other" recommendations.
- Numeric fields need richer filter controls: range sliders, quantile brackets, null handling, outlier clipping, and relative comparisons.
- Date fields need calendar-aware bucketing, missing-period handling, fiscal periods, and rolling windows.
- Hierarchical fields need reusable drill-down paths and breadcrumb state.
- Multi-visual work needs linked selection, brush filtering, and shared filter context.
- Exported or saved views should preserve field aliases, filters, visual options, and derived column definitions.
