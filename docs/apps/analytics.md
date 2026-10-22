# Analytics workspace

Analytics is a primary workspace with Finances at `/analytics/` and Investments
at `/analytics/investments/`. Its orchestration reuses the existing dashboard
and investment read models; it owns no new financial ledger or calculations.

## Financial analysis

Finances gathers categorized expenses, account-balance evolution, monthly cash
flow, fixed/installment/one-off composition, activity by account or card and the
six-month outlook. Home retains live availability, monthly indicators, accounts,
outstanding invoices and financial entry actions. Its analytical shortcut keeps
the selected month.

Category expenses retain the selected month and current-date cutoff. Each
existing report chart keeps its independent period, filter, reset and
composition contract. The six-month table distinguishes statement-month
activity from bank cash by payment date. A route change does not reinterpret
purchases, card credits, paid invoices or split-category amounts.

The monthly category/outlook block and the report charts are separate HTMX
islands. Each period link owns one query parameter: `month`, `charts_offset`,
`instrument_month` or `installment_month`. The scoped
`static/js/analytics-navigation.js` helper rebases that cursor against the
committed browser location, preserving unrelated filters. Its workspace-local
queue retains rapid independent choices and resolves a live control after a
prior response replaces an island; leaving the workspace discards pending
intentions. Attribute updates preserve untouched help and composition panels.
Native GET links and modified clicks retain complete destinations.

Monthly arrows keep stable control IDs on their unavailable limit placeholders,
so an island refresh can restore keyboard focus without adding a Tab stop. When
the focused month reset disappears, focus moves discreetly to the month caption.
That fallback applies only to the focused reset request: background refreshes
and deliberate focus changes elsewhere retain their active control.

See the [dashboard financial rules](dashboard.md#reports) for source attribution,
FX dates, realized/projected boundaries and cash-flow formulas.

## Investment analysis

Investment analysis contains current valuation and evidence warnings, historical
position evolution, deposits/withdrawals/internal yields and the existing
performance detail table. Purpose scope and both chart windows remain
independent. Missing prices, FX and opening dates remain explicit rather than
being converted into zero values or invented returns.

See the [investment chart contract](investments.md#charts) for dated prices,
remaining acquisition cost and financial scope.

## Compatibility and privacy

The former `/dashboard/reports/` and `/investments/charts/` entries redirect to
their canonical analytical destinations with query and fragment context.
Source composition continues through the signed, user-owned
`/dashboard/chart-details/` endpoint. Source editor Save/Cancel retains the
originating analytical filters and chart anchor.

The assistant recognizes both Analytics pages and their validated period/scope
filters. Navigation and route changes grant no additional provider access or
financial write permission. Private history, authorized Back/Forward GETs,
native filtering and unsaved financial-form protection follow the shared
[frontend navigation contract](../frontend/navigation.md).
