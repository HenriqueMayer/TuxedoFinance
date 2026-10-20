# Frontend workspace compositions

[Frontend index](../frontend.md) · [Interface map](../interface-map.md)

## Banking information architecture

`/banking/` starts with the all-bank availability summary and a grid of bank
links. Each bank shows its name, color marker and account/card counts. There is
no overview search. Bank, cash-pot and set-aside totals remain exposed beside
the consolidated available amount. Open an institution to reveal its accounts,
cards, monetary cash positions and loyalty in one full-width internal workspace
in place of the grid. Its window header contains the current bank and a visible
Minimize action with text and icon; long bank indexes never push the selected
accounts down the page. Minimize restores the overview, its location and the
originating bank's focus. Choose another bank from that overview.
The existing bank URLs, native links and browser history remain authoritative,
with a complete page fallback.
The whole-workspace HTMX swap establishes a fresh navigation baseline; inner
POST/result updates must not clear an edited form's departure protection.

Each account card keeps its name, currency and New transaction action together.
Balance, set-aside funds and availability form a labelled amount grid without
actions embedded in it. The planning participation control remains separate.
Credit-card invoice/purchase shortcuts and administrative options belong to that
account; Account details discloses its opening balance and debit cards. An
account ellipsis retains editing/reserving, transfer, card creation and deletion.
Monetary cash pots reuse compact account surfaces in a responsive grid. Each
shows the asset name, product, currency, balance and available amount; its
participation POST is separate from the figures. The redemption instruction
appears once per group. Set balance aside is an action, avoiding the ambiguous
Portuguese state label previously used on included positions.

Reserves is a separate native disclosure. Recent activity discloses redemptions,
related invoices and ledger movements; a bound redemption error opens it. Explicit record
fragments reveal their containing native disclosures after full or boosted
page navigation; unrelated background updates do not reopen them.

Banking templates mark their owning content with `.banking-workspace`. Compact
panel/row padding and 16/24px section titles retain the ledger's density, while
page titles follow the catalogue's shared 28/35px mobile and 32/40px desktop
scale. Ordinary fields, global navigation and actions use the common components.

Actions and menu items retain a minimum height of 44px for all pointer types;
row ellipsis triggers also retain a 44px width and 8px corners. Header option
summaries use the same balanced 12px action geometry. Native color fields use
the common 44px height, and gradient checkboxes keep their label beside the
control. Preserve visible keyboard focus, deliberate menu activation, native
links and complete no-JavaScript submission.

Invoices opens a paginated grid of owned cards, including cards without invoices.
A card opens `/banking/credit-cards/<id>/invoices/`, where dated invoice rows,
filters and payment/source links remain available. Month/status criteria on the
overview show only matching cards; search/bank criteria also find empty cards.
Counts include only the owner's invoices. The card page's Clear resets criteria
while keeping the selected card and validated return context. The former
`/banking/invoices/?card=<id>` address redirects to the owned card page, retaining
other criteria. Both routes use native links and GET fallbacks.

Pin the invoice form's action to its rendered path. An omitted action would
follow `location` during Back and let a card-history form intercept an overview
history entry. Distinct paths and fixed actions keep the shared live-filter and
whole-page history responsibilities separate without another navigation runtime.

Planning fragments reuse the same account/card presentation and owner-filtered
prefetches. Contextual shortcuts retain the explicit validated page origin after
POST updates instead of adopting the planning endpoint as their return target.

Opening balance is clearly labeled as the ledger starting point, not an income
transaction. Personal records remain editable; audit-grade reversal controls
are not part of the current product.

## Planning workspaces and shared presentation

The primary navigation is **Home / Transactions / Accounts / Investments / Plan**.
Home contains Dashboard and Reports. Transactions contains the ledger and
Categories. Planned Net worth and Imports have no tabs, review badges or account
menu entries; their roadmap lives in documentation. Old operation URLs still
stop at server gates; owned confirmed import provenance remains read-only.
Accounts includes Invoices and Exchange rates. Investments opens a simple list
of holdings with Update beside each row; history, analyses and full configuration
remain secondary. Plan opens the monthly cash outlook and budgets, with three
sections: This month, Goals and Tools. Signals and simulations live in Tools.
The shared section navigation retains its 24px space before the page header;
workspace density overrides must not compress that separation.
Existing domain URLs retain ownership and safe contextual return behavior;
`/planning/budgets/?month=…` redirects to the same month at `/planning/`.
Account settings and language live in account options. Primary links navigate
directly in both sidebar and bottom navigation. Option buttons, including
Export CSV, account options, project links and row actions, open only by click,
touch or keyboard activation. Hovering them never reveals their options.

## Investment workspace continuity

The investment entry screen is My investments. Add investment is a guided,
atomic institution/product/asset registration with explicit purpose and valuation
mode. It accepts a zero opening without creating cash or financial evidence;
nonzero openings require a date. Update opens a contextual choice of contribution,
withdrawal, yield or local price, retaining server financial validation. Full
configuration and analyses remain in a deliberate More menu; simulations are
reachable through Plan → Tools. See the investment guide for the zero-position
configuration rule and the distinction between acquisition cost and market price.
Asset configuration separates active assets from a native Archived assets
disclosure. Archive/Restore use deliberate, CSRF-protected POSTs. Same-page
boosted responses reuse the common viewport/focus restoration, with one stable
availability-button ID per asset; the archived disclosure opens after archiving.
Native submissions land on the changed asset through a section anchor. Delete
uses the existing confirmation and remains unavailable for protected holdings
or history; a blocked deletion page offers Archive as an alternative. New
operation choices exclude archived assets, while historical editors keep their
own archived selection and explain how to restore it for new operations.
Portfolio and Remunerated cash hide archived position rows and empty product/bank
groups after calculating totals over all holdings. A short notice explains why
archived balances remain in totals; an all-archived section has an active-position
empty state rather than first-operation guidance. Existing Operations navigation
keeps history accessible, and restoring an asset makes its positions visible.
The History
page owns operation search, purpose/type/record filters and pagination. The holdings
list and each position detail provide scoped history. Charts under More → Analyses filters historical positions and flows by Overall, Portfolio or
Remunerated cash; scope and independent month windows survive GET/HTMX updates.
The charts destination remains accessible through the secondary More menu. Old movement-filter
URLs redirect to the new page. Chart navigation and operation pagination keep
separate HTMX regions. Operation forms return to an explicit originating
position or filtered history after Save/Cancel, using `core.navigation` and the
`contextual_url` template tag. The default remains the operation history when
no safe origin is supplied. Return paths are encoded explicitly, persisted in
a hidden `next` field through invalid POSTs, and validated as local paths;
they do not relax user ownership.

## Planning parameter controls

Planning month fields retain native keyboard entry and open the native picker
from the entire field when `showPicker` is available. Monthly-plan arrows submit
unsent form values along with the new month; localized month text identifies the
selection. The forecast submit button remains as the no-JavaScript fallback and
is hidden after enhancement, since changing the month already refreshes it.
Additional expenses explicitly choose BRL or a percentage of gross salary.

Yield simulation puts the rate period before the rate value and updates its label
and help name together. Currency labels follow the currency selector. Duration
shortcuts activate only on click, touch or keyboard, preserve focus, and use the
same month field/override retention as manual entry. Live results never replace
parameter fields. See the [planning guide](../apps/sandbox.md) for calculation rules.
