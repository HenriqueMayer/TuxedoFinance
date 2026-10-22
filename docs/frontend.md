<a id="frontend-design-system--templates"></a>

# Frontend contracts

The application uses server-rendered Django templates, precompiled Tailwind CSS
and progressive JavaScript enhancement. Native controls, owned server responses
and financial validation remain authoritative. This index directs changes to
the guide that owns each responsibility; the [interface map](interface-map.md)
records routes and shared components, and the [Design Lab](design-system.html)
provides the visual reference.

| Working on | Canonical guide |
|---|---|
| Build, delivered assets, HTMX, private history and translations | [Runtime](frontend/runtime.md) |
| Editorial language, tokens, layout, responsive surfaces and shared components | [Presentation](frontend/presentation.md) |
| Fields, choices, conditional recovery, dates, amounts and card appearance | [Forms](frontend/forms.md) |
| Synthetic visual specimens and their local interactions | [Catalogue](frontend/catalogue.md) |
| Navigation, viewport, menus, help, return context and departure | [Navigation](frontend/navigation.md) |
| Assistant utility panel, focus and workspace continuity | [Navigation — assistant panel](frontend/navigation.md#assistant-panel); [assistant data/provider boundary](apps/assistant.md) |
| Dashboard/report chart scopes, SVG layers, selections and source composition | [Charts](frontend/charts.md) |
| Dynamic GET filters, consultation bars and named months | [Consultation](frontend/consultation.md) |
| Banking, investment and planning screen compositions | [Workspaces](frontend/workspaces.md) |

Setup and executable checks remain in [Contributing](../CONTRIBUTING.md).
App guides own financial meaning and deliberate domain exceptions. Keep
validation results with the exact revision's pull request or CI run, and local
diagnostics in ignored output directories.
Keep detailed interaction rules in their owning guide instead of copying them
into app documentation or agent instructions.

## Existing section links

The section links below retain earlier URLs. Follow their canonical guide for
the complete current contract.

### Private history

See [Private history](frontend/runtime.md#private-history).

### Editorial application adoption

See [Editorial application adoption](frontend/presentation.md#editorial-application-adoption).

### Transaction amount entry

See [Transaction amount entry](frontend/forms.md#transaction-amount-entry).

### Shared complete-date dialog

See [Shared complete-date dialog](frontend/forms.md#shared-complete-date-dialog).

<a id="catalogue-visual-experiment"></a>

### Canonical design catalogue

See [Canonical design catalogue](frontend/catalogue.md#canonical-design-catalogue).

### Preserve the user's location

See [Preserve the user's location](frontend/navigation.md#preserve-the-users-location).

### Visual language

See [Visual language](frontend/presentation.md#visual-language).

### Dark foundation tokens

See [Dark foundation tokens](frontend/presentation.md#dark-foundation-tokens).

### Root layout and navigation

See [Root layout and navigation](frontend/navigation.md#root-layout-and-navigation).

### Template tree

See [Template tree](frontend/presentation.md#template-tree).

### Banking information architecture

See [Banking information architecture](frontend/workspaces.md#banking-information-architecture).

### Forms and settlement disclosure

See [Forms and settlement disclosure](frontend/forms.md#forms-and-settlement-disclosure).

### Keyboard and choice contract

See [Keyboard and choice contract](frontend/forms.md#keyboard-and-choice-contract).

### Conditional fields and recovery

See [Conditional fields and recovery](frontend/forms.md#conditional-fields-and-recovery).

### Multicurrency display

See [Multicurrency display](frontend/presentation.md#multicurrency-display).

### Translation convention

See [Translation convention](frontend/runtime.md#translation-convention).

### Dashboard

See [Dashboard](frontend/charts.md#dashboard).

### Reports and charts

See [Reports and charts](frontend/charts.md#reports-and-charts).

### Question-mark help

See [Question-mark help](frontend/navigation.md#question-mark-help).

### Responsiveness and accessibility

See [Responsiveness and accessibility](frontend/presentation.md#responsiveness-and-accessibility).

### Automated browser checks

See [Automated browser checks](frontend/runtime.md#automated-browser-checks).

### Planning workspaces and shared presentation

See [Planning workspaces and shared presentation](frontend/workspaces.md#planning-workspaces-and-shared-presentation).

### Compact row-action menus

See [Compact row-action menus](frontend/navigation.md#compact-row-action-menus).

### Shared workspace components

See [Shared workspace components](frontend/presentation.md#shared-workspace-components).

### Previous-screen continuity and balance ranges

See [Previous-screen continuity and balance ranges](frontend/navigation.md#previous-screen-continuity-and-balance-ranges).

### Card appearance

See [Card appearance](frontend/forms.md#card-appearance).

### Planning parameter controls

See [Planning parameter controls](frontend/workspaces.md#planning-parameter-controls).

### Live consultation filters

See [Live consultation filters](frontend/consultation.md#live-consultation-filters).

### Compact consultation bars and month names

See [Compact consultation bars and month names](frontend/consultation.md#compact-consultation-bars-and-month-names).
