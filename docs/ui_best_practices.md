# Stateframe UI Best Practices

These notes capture recurring UI decisions for the notebook/web widget so new panes stay consistent as the product grows.

## Dense Work Surfaces

- Any main work surface with side panels should make those panels both collapsible and width adjustable.
- Panel width should live in synced widget state when the choice should survive redraws.
- Use the shared horizontal resizer behavior for left/right panel walls, including keyboard arrow support.
- Keep the primary canvas/data area visible when both side panels are collapsed.
- When a panel is collapsed, leave an obvious expand control in the work surface, not only in a distant toolbar.

## Redraw Safety

- Any text input, textarea, or select that writes to synced widget state during input must have a stable `data-focus-key`.
- Before state changes, capture focus, selection, and scroll. After redraw, restore them without moving the viewport.
- Avoid state writes on every keystroke unless the control has focus restoration or local draft state.

## Navigation And Scroll

- Clicking a branch, leaf, button, or column control should not reset the scroll position of the surrounding pane.
- Search result navigation should center the matched cell or item inside its own scroll container.
- Use `data-scroll-key` on independently scrollable panels.

## Leaves And Artifacts

- Dataframe states open in the viewer.
- Output leaves open in the leaf view.
- Plot leaves should show a static preview when possible, then the full interactive render where supported.
- Visual-builder previews should prioritize the live interactive render. Static images are fallbacks, thumbnails, or saved previews.
- Leaf notes should render markdown and save with the leaf metadata.

## Visual Consistency

- Reuse existing button, input, panel, resizer, status, and empty-state classes before adding new ones.
- Prefer compact icon-style controls in dense lists where repeated text labels waste space.
- Keep operational tools quiet and scannable: restrained borders, clear hierarchy, no decorative layout elements.
