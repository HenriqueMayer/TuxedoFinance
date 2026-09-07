# Tuxedo Finance contributor contract

Read `CONTRIBUTING.md` before changing the application. Technical documentation
and code use English; interface strings must have English and Brazilian
Portuguese translations.

## Mandatory form behavior

Every new or changed form must follow the [shared form contract](docs/frontend.md#keyboard-and-choice-contract).

- Use `partials/form_field.html` for ordinary Django fields. It automatically
  enhances model choices through `form_control`; do not implement another picker.
  Handwritten record selectors must use `data-search-select` and a stable ID.
- Preserve native short choices, Tab/Shift+Tab, visible focus, Enter/Space
  activation, and the shared searchable-choice keyboard behavior.
- When a user reaches or opens a searchable choice, keep its input and results
  in the viewport without moving focus. Scroll long results internally; preserve
  page position during initialization and background refreshes.
- Start new conditional choices empty, and conditional checkboxes unchecked.
  Preserve bound POSTs, edited records and explicitly selected shortcut context.
- Reveal dependent controls only after the relevant choice. Keep inactive
  controls out of the Tab order, clear incompatible values after deliberate
  transitions and preserve server errors for recovery, including nested groups.
- Keep native controls and complete submissions working without JavaScript.
  Entry forms use `novalidate` and rendered Django errors. Ownership,
  compatibility and accounting validation remain on the server.
- Add browser coverage using real keyboard events for changed interactions,
  including invalid responses and transitions. Inspect focus/selection in both
  themes. Include the contract in future form reviews.

Run browser tests with `npm run test:e2e`, which owns a disposable database and
loopback server. Never point browser tests at the developer's database or server.
Run applicable Django checks and `git diff --check`; rebuild committed CSS and
translations when their sources change.

## Mandatory help icons

Every new or changed question-mark help icon must follow the
[shared tooltip contract](docs/frontend.md#question-mark-help). Reuse
`partials/help_popover.html`; open on hover or keyboard focus, dismiss on pointer
exit/outside click/Escape, and never pin mouse-clicked help. Preserve touch and
no-JavaScript access. Use the shared readable width and structured copy; test
real interactions, viewport bounds, both themes and HTMX initialization.
