# Frontend style sources

[`css/tailwind.css`](css/tailwind.css) is the ordered build entry for the
committed [`static/css/app.css`](../static/css/app.css). It imports shared
presentation and workspace rules without changing their cascade. The font
declaration stays in the entry so its delivered relative URL remains stable.

| Responsibility | Sources |
|---|---|
| Shared primitives, layers, help and focus | [`shared/primitives.css`](css/shared/primitives.css) |
| Stable consultation rails | [`shared/consultation-layout.css`](css/shared/consultation-layout.css) |
| Product-wide editorial fields, panels and actions | [`interface.css`](css/interface.css) |
| Authenticated navigation and public homepage | [`workspace-shell.css`](css/workspace-shell.css), [`public-home.css`](css/public-home.css) |
| Entry fields, category allocation and payment artwork | [`transaction-entry.css`](css/transaction-entry.css), [`category-allocation.css`](css/category-allocation.css), [`payment-choices.css`](css/payment-choices.css), [`card-appearance.css`](css/card-appearance.css) |
| Shared date, period and departure controls | [`date-picker.css`](css/date-picker.css), [`period-navigation.css`](css/period-navigation.css), [`departure-confirm.css`](css/departure-confirm.css) |
| Category hierarchy and consultation | [`category-tree.css`](css/workspaces/category-tree.css), [`category-filters.css`](css/workspaces/category-filters.css) |
| Account overview, compact actions and cash positions | [`account-overview.css`](css/workspaces/account-overview.css), [`banking-density.css`](css/workspaces/banking-density.css), [`cash-positions.css`](css/workspaces/cash-positions.css), [`banking-consultation.css`](css/banking-consultation.css) |
| Transaction consultation geometry and selected states | [`transaction-consultation.css`](css/workspaces/transaction-consultation.css), [`transaction-consultation-state.css`](css/workspaces/transaction-consultation-state.css) |
| Investment and planning workspaces | [`finance.css`](css/workspaces/finance.css) |
| Reporting surfaces and chart readability | [`reporting.css`](css/reporting.css) |

Imports are ordered, rather than alphabetical. Layered shared components precede
the later unlayered workspace rules. Transaction consultation states deliberately
remain after the account overview; invalid-field boundaries remain after cash
positions. Keep those positions when moving a rule between files. Source imports
are compiled through PostCSS; the browser loads only the generated stylesheet.

[`tailwind.config.js`](tailwind.config.js) owns the palette, typography and
content sources. Catalogue-only styles remain in
[`docs/design-system.css`](../docs/design-system.css).

Use the [contribution workflow](../CONTRIBUTING.md#frontend-and-translations) for
build commands and generated-asset checks. The
[frontend guide](../docs/frontend.md) owns behavior and accessibility; the
[interface map](../docs/interface-map.md) owns routes, component adoption and
visual exceptions.
