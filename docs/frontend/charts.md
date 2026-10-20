# Frontend charts and financial presentation

[Frontend index](../frontend.md) · [Interface map](../interface-map.md)

## Dashboard

Home separates planning availability from selected-month performance:

- available planning funds, with their account, cash-pot and reserved components;
- income, expenses, investments, and withdrawals as separate performance metrics;
- current-month values through today with the remaining plan shown underneath;
- complete values for past months and explicitly planned values for future months.

Home keeps operational account and invoice previews. Its Analytics shortcut
retains the selected month. Analytics owns the category breakdown, projected
closing balance and financial/investment charts; their calculations stay separate
from Home's live availability.

Current Balance in Analytics remains distinct from the projected month-end close. Credit-card
purchases belong to the statement month but affect cash only when the invoice is
settled. Own transfers may appear in activity but are visually neutral and
absent from income/expense charts. Projected figures are labeled and never
presented as posted cash. The top-six category breakdown in Analytics follows the
same month-to-date, completed-month, or planned-month context as the metrics. Live bank
accounts and outstanding invoices are limited to five rows each. Accounts link
directly to their bank row without the shell's generic scroll-to-top override.
Outstanding invoices include overdue obligations, independently of the selected
performance month; All invoices explicitly opens the complete card overview.
Invoice rows link to their source detail and show the remaining amount in
confirmed mode. When `feature_available('imports')` is enabled, a separate owned,
staged-import queue highlights decisions waiting for review without counting
them as posted cash. Imports are paused by default, so the queue is hidden in
the default configuration.

## Reports and charts

The Reports summary uses three metrics: live bank cash, the identified anchor
month's inflows minus outflows, and bank-balance change across the full chart
window. Monthly result excludes the opening balance and includes recorded
investment deposits/withdrawals separately from consumer income/expense. The
window-wide change keeps its existing calculation and missing-rate warning.
`stat_card.html` accepts a period `caption` and shared question-mark help through
`help_id` plus `help_text` or a trusted `help_template`. The full-window explanation follows HTMX changes
to the displayed dates. Reports no longer show a best-month summary card.

Balance evolution and Monthly cash flow reuse `_report_window_navigation.html`.
Both expose Back to today when `charts_offset != 0`; keep that action below the
arrows and period label so the arrow row does not move when it appears. Reset to
`charts_offset=0`, retain unrelated query filters, and preserve scroll and a
visible keyboard focus target through HTMX replacement. Native links must also
work without JavaScript.

Income and expenses by account or card and How much is on installments each
have an independent monthly cursor. Both start at the current month and use
previous/next month arrows to navigate past and future months. Do not replace
these controls with month dropdowns or a shared multi-month window. Keep native
links, stable control IDs, scroll and keyboard focus across HTMX updates. Each
Current month or Last 12 months action changes only its own chart; Last 12 months
retains the current calendar month and the previous eleven months. Its legacy
`ALL` query value is preserved, but must not be labelled as the full ledger.
In this twelve-month mode the arrows
resume monthly navigation from the current month. Totals and composition details
must always resolve to the same scope. Invalid or obsolete account/card months
recover to the current month, while invalid installment months recover to Last
12 months. Test month boundaries, past/future navigation, Last 12 months and current-month
return, invalid query recovery, focus and scroll preservation, no-JavaScript
links, and both themes.

## SVG chart presentation

Charts remain inline server-rendered SVG/CSS with native `<title>` fallbacks,
theme-aware tooltip pills on mouse hover and keyboard focus, responsive
overflow containers and accessible text summaries. Reports and Investments use
the same interaction contract. Income uses the green pair, expense uses the red pair, and
investment has its own ochre pair. The recurrence donut uses purple
installments, orange fixed recurrences and neutral one-off purchases; its zero
line is neutral. HTMX swaps only the report island while preserving focus and
viewport; plain links/forms remain equivalent.

SVG paint order is part of that contract. Every interactive chart renders all
data marks and axis labels in a base `data-chart-layer="*-marks"` layer, then
renders transparent hit targets, hover/focus highlights and tooltip pills in a
final `data-chart-layer="*-interactions"` layer. Tooltips must never be nested
only beside their original mark in series order: later SVG elements would paint
over them. Tooltip content remains `pointer-events-none`, while its transparent
hit target retains the native `<title>` and keyboard focus. Chart marks select
values without navigating; period controls retain their native links or forms.

Every chart states its reporting currency and actual versus projected period.
The selected per-user base currency, snapshot status where supported, and
explicit missing-FX totals are shown. Current valuation charts display their
valuation date/source.

Credit purchase and invoice payment series must use distinct labels. No chart
may aggregate both as expenses. Investment yield is shown in investment
performance, not bank income.

## Chart selection and composition

Charts use direct manipulation without manual range selectors. Drag either way
on time series, or select endpoints with Enter/Space. Shift-click and Shift with
Enter/Space toggle individual bars or slices. Instrument bars have no click
navigation. The donut puts its selected sum in the center and restores the full
total on outside click or Escape. Other charts retain the selection summary.
Selection never writes financial records. Without JavaScript the original chart
values and period navigation remain available.

Press Ctrl while hovering or focusing a mark to open its composition in a
viewport-bounded, scrollable panel, then release Ctrl before scrolling. Releasing
the key or moving the pointer between the chart and panel leaves it open. The
panel contains wheel/keyboard scrolling, including at its scroll boundaries.
The prominent Close composition button, another Ctrl press, Escape, any click
outside the panel (including chart controls), wheel/scroll outside the panel,
another chart selection or a replacement of its owning chart dismisses it.
The closing Ctrl press stays suppressed until key release, preventing a
hovered mark from reopening the panel immediately. Opening a different composition
closes the previous panel. Keyboard opening focuses the panel without scrolling
the page. A queued native-focus scroll does not dismiss a panel opened after
the position changed; subsequent outside scrolling still dismisses it. A new
hover takes precedence over focus retained by a previous chart;
moving keyboard focus resets that pointer context. Tab reaches the close button,
row disclosures and operation links; leaving the panel dismisses it. Close,
Escape and a second Ctrl return panel focus to its mark. An unrelated HTMX update leaves it open.
On touch, tap selects and holding a mark opens its composition until dismissed.
This interaction belongs to chart composition, independently of question-mark
help and ordinary SVG value tooltips. A shared read-only authenticated endpoint accepts
signed, user-bound chart scopes; all queries are scoped to the current user.
Category paths preserve parent and subcategory names. Transaction charts use the
same competence window and series as the chart, while bank balances show their
account composition and investments show products/assets. Details for all-period
charts use their full twelve-month scope. Decimal amounts become integer cents;
SVG coordinates never supply financial values.

Composition rows use a quiet arrow and a real same-tab hyperlink when exactly
one source contributes. When several sources contribute, the native row
`details` discloses their dated operation links and scoped amounts through
click/touch or Enter/Space, without opening on hover. A recurring transaction
appears once with its summed contribution across the selected months. Bank
balances link to the account in bank details; opening investment positions link
to the asset configuration; investment operations and ordinary transactions
link to their existing editors. Generated IOF links to the source redemption,
preserving its transaction edit lock. Links retain native modified-click behavior
and shared browser Back/Forward. Opening an editor does not submit a financial
change. Close the panel before navigation, remove cached panel copies on HTMX
history restoration, and retain the report's period and scroll context.
In Analytics Finances and Investments, the shared source-link renderer adds an explicit `next`
containing the current query and stable owning-chart anchor. Only server-reversed
consultation origins and same-origin HTTP(S) targets participate; existing
destination validation and ownership checks still apply. Save/Cancel use that
context, while modified clicks and browser Back/Forward remain native.
Source links with record fragments also disable the inherited boosted-body
scroll-to-top so the account row is actually revealed, including in Reserves.
All links come from owned records in the same signed scope as the displayed
amount; missing FX values never become an operation link. Fractional FX cents
are allocated by remainder across displayed source amounts so they reconcile
with the existing aggregate total.
