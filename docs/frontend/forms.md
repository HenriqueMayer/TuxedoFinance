# Frontend forms, choices and payment appearance

[Frontend index](../frontend.md) · [Interface map](../interface-map.md)

## Transaction amount entry

Only the transaction total opts in with `data-money-input` to
`static/js/money-input.js`. With JavaScript, digits fill cents from the right:
`1234` becomes `12.34` in English or `12,34` in Brazilian Portuguese. Existing
amounts and explicit decimal pastes retain their monetary value. Formatting uses
decimal strings, never floating-point financial arithmetic. The same named
control remains the form's value and history field; native form-data creation
converts valid display text to the canonical decimal expected by Django.
Invalid text stays available for server validation. Without JavaScript, the
original native number field accepts ordinary decimal amounts. Split allocation
amounts and unrelated financial forms retain their current entry behavior.
Enhancement runs before the navigation snapshot records a swapped form, so
formatting alone cannot trigger an unsaved-operation warning. Exact parsing and
editing cases run with `node --test tests/tooling/money-input.test.cjs`; real
keyboard, native POST and visual-choice coverage lives in
`tests/e2e/shared/payment-choice-visuals.spec.js`.

## Shared complete-date dialog

`static/js/date-picker.js` is the single calendar engine for both the application
and catalogue. Every complete-date field configured through
`core.dates.configure_date_fields` opts in with `data-date-picker="true"`.
Month-only consultation retains its dedicated component. The original
preferred-date text input, its name, invalid bound
text and the user's DMY/MDY format remain intact. The existing helper continues
to hold an ISO date, and server parsing still accepts the preferred format or
ISO. Calendar arithmetic uses UTC components without converting stored calendar
dates between time zones.

A click anywhere in an opted-in field, Enter, Space, Alt+ArrowDown or the existing
Select date button opens one native modal `dialog#date-picker`. Tab arrival does
not open it, and ordinary text editing remains available. The trigger intercepts
the native helper only for enhanced fields; without JavaScript or modal-dialog
support, the original preferred-date/native-helper behavior remains available.
The 42-day grid, month/year jumps, roving keyboard focus, missing-day clamping,
min/max bounds, Today and Clear use the same behavior as the catalogue calendar.
Committing a choice updates preferred text and the ISO helper, then emits `input`
and `change`; POST forms still require Save, while consultation retains its
existing live GET behavior. Escape, outside dismissal and
Close preserve the entered value and restore usable owner focus without
scrolling. Hiding, disabling, resetting or replacing the owner closes its dialog.

Initialization is idempotent after full loads, HTMX loads and history recovery.
Unrelated HTMX updates preserve an open owner, while a swap replacing that field
closes its dialog. Closed calendars retain no selected-day grid, and no calendar
state is stored in browser storage. Application labels come from the translated
`partials/form_ui_strings.html`; month/day names follow the document language.
`assets/css/date-picker.css` is compiled with the application stylesheet and
provides both themes, viewport bounds, touch targets and reduced motion. Browser
coverage does not certify assistive-technology interoperability; separate manual
screen-reader checks remain necessary.

## Forms and settlement disclosure

### Keyboard and choice contract

This is mandatory for **all existing, new and changed forms**, including filters,
settings and imports. Use the shared field renderer and test the interaction;
custom pickers must not be copied into individual templates. The implementation
follows the [WAI-ARIA combobox pattern](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/).

| Control | Keyboard behavior |
|---|---|
| All controls | Tab/Shift+Tab move forward/back in document order with visible focus. No positive tabindex or focus jumps when branches appear. |
| Ordinary single-record choice | Type to filter; Down/Up open results and highlight the next/previous option; Enter confirms the highlighted option. |
| Ordinary single-record cancellation | Blur, Tab and Escape close results, restore the committed choice and discard unconfirmed search text; Tab continues in document order. |
| Persistent payment choice (`data-payment-choices`) | Type to filter the visible board; Down/Up move its keyboard cursor and Enter confirms explicitly. Blur and Tab preserve the board and query. Escape clears the query and cursor, preserving the committed record. See [persistent payment choices](#persistent-payment-choices). |
| Search input Enter | Never submits the form, including with zero matches. |
| Short native select | Use the browser's native keys (Space or Alt+Down to open where supported, arrows to navigate and Enter to confirm). |
| Checkbox / multiple record choice | Space toggles a focused checkbox; Tab reaches each visible checkbox. Filtering preserves selected records. |
| Advanced options | Focus the native summary and press Enter or Space; Tab then visits its fields. |
| Save / other buttons | Enter or Space activates the focused button. |

Single-record search uses manual confirmation, including when there is only one
match. Focus remains on the search input. In an ordinary single-record picker,
`aria-activedescendant`, `aria-selected` and the visible active highlight move
together; the payment board separates its committed selection from that cursor
as described below. Arrow navigation stops at the ends. Home/End and text-editing
shortcuts retain native editing behavior. Mouse/touch selection commits the
same record; the explicitly labeled clear button removes the committed selection.

Search instructions and single-choice selection announcements remain available
through `aria-describedby` and live text without repeating paragraphs beneath
every picker. Do not introduce focus-dependent in-flow instructions: removing
their height on blur can move a Save button or radio between pointerdown and
pointerup, cancelling the user's action. Verify direct clicks after committing a
choice as well as keyboard submission.

When a user focuses, filters or opens a searchable choice, scroll only as far as
needed to show the input and results below the sticky header. Keep focus on the
input. Size the results to the available visual viewport, including after a
mobile keyboard or window resize, and keep long lists internally scrollable.
Arrow navigation keeps the active option visible inside that list; once the
picker fits, it must not keep moving the page. Use immediate scrolling so keyboard
input does not race an animation, including with reduced motion enabled.
Initialization, background refreshes and merely revealing a conditional branch
must not scroll the page. This targeted visibility adjustment applies when the
user reaches the picker and does not change the HTMX location-preservation rule.

A fixed, internally scrollable consultation panel may explicitly own a picker
viewport with `data-search-choice-viewport`. The shared picker then clips its
results to the panel, visual viewport and navigation bounds, scrolling the panel
or results instead of the document. Month consultation opts in because document
scrolling deliberately dismisses its popup. Ordinary form pickers retain their
existing page-visibility adjustment. Test the open panel after a live response,
with a short mobile viewport, unchanged page scroll and deliberate outside-scroll
dismissal.

All Django `ModelChoiceField` and `ModelMultipleChoiceField` controls rendered by
`partials/form_field.html` receive `data-search-select` through the `form_control`
template tag. This covers categories, parent categories, banks, accounts, cards,
assets, investment products, programs and invoices. Handwritten record filters
must also carry that attribute and a stable unique ID. Serialize record keys in
option values without localization (for example, `pk|stringformat:'s'`); thousands
separators belong in displayed amounts, never in submitted identifiers. Short
enumeration choices remain native controls: transaction type/payment use native
radio groups; other existing enumerations retain selects. Disabled fields remain
native and disabled.

`static/js/forms.js` progressively enhances these controls, using the original
scoped options and preserving their names, values, metadata and `change` events.
It reads translated text from `partials/form_ui_strings.html`. Initialization is
idempotent on DOMContentLoaded and HTMX load. Domain handlers may update native
values/options; the shared refresh runs after their change handlers. Call
`TuxedoForms.refresh(form)` after changes outside a change event. User text is
inserted with textContent, never interpreted as HTML. No remote search or new
frontend dependency is involved. Entry forms use `novalidate` so hidden native
selects cannot intercept error recovery; Django renders the validation errors.

### Persistent payment choices

Payment instruments opt into the same shared picker with
`data-payment-choices`. Revealing a channel presents its compatible options as a
persistent illustrated board, without moving focus, scrolling or automatically
selecting a record. This opt-in also serves banking editors, linked loyalty
cards, points-purchase funding, invoice selection and redemption/IOF instruments.
Ordinary model pickers retain the close-on-blur behavior in the table above.

The compact search filters the board. Blur and Tab leave its query and results
visible; an unrelated refresh preserves them too. In a single-choice board,
Down/Up move the keyboard cursor and Enter explicitly commits the highlighted
record. Committing by keyboard, mouse or touch clears the filter and restores
the complete compatible board. Escape clears only the filter and cursor, never
the committed record. `aria-selected` identifies the committed option;
`data-active` and `aria-activedescendant` identify its separate keyboard cursor.
The committed native value and selected-record announcement remain intact even
when the current query filters that option out. The explicit Clear selection action
retains its separate meaning: it removes that selection and resets the query.

A multiple-card field remains a labelled group of native checkboxes, rather
than a single-choice listbox. Tab reaches each visible checkbox and Space
toggles it. Filtering, clearing the query and leaving the search preserve
selected records outside the visible results. Clear selection explicitly removes
all selected records; it must not be confused with Escape's query reset.

Channel changes retain PIX eligibility filtering and clear incompatible card
choices. Native option labels and unlocalized identifiers remain the submitted
source of truth; safe server-provided metadata supplies only the owned records'
illustrations. Ownership, compatibility and accounting checks remain on the
server. Complete native controls and POSTs work without JavaScript. The board
never introduces another picker or changes these rules through its artwork;
see [payment presentation](presentation.md#editorial-application-adoption) and
[card appearance](#card-appearance) for the visual treatment and contrast rules.

### Conditional fields and recovery

- New choices that control branches begin empty; conditional checkboxes begin
  unchecked. Preserve submitted values, existing records and validated shortcut
  context. Model/storage defaults need not change to enforce the creation UI.
- Transaction categories wait for income/expense; a credit channel reveals the
  card selector, and a confirmed card reveals installment/bill details. Recurrence
  reveals its end date only after the checkbox is selected.
- Investment values and funding wait for an asset and operation type. Monetary
  yield requires an explicit input-mode choice. Opening balances wait for the
  valuation mode; their product appears when an opening position is supplied.
- Points purchases reveal payment amounts after a funding source is selected.
  Redemption IOF sources appear only for a positive IOF amount. Sandbox CLT and
  transport-voucher details require their respective checkboxes.
- Use `TuxedoForms.setHidden(group, inactive, preserveErrors)` for domain-specific
  branches. Simple dependencies may use `data-form-when="controller-id"` plus
  `data-form-value="checked|unchecked|positive|literal-value"`; these clear their
  inactive controls after a deliberate controller change. `data-inactive-value`
  can specify a domain-required reset value instead of an empty string.
- Every directly toggled group, including parents, must expose its own
  `data-has-errors`. Initial rendering keeps errored branches visible and opens
  advanced sections containing errors. A deliberate switch clears incompatible
  values and dismisses the abandoned branch's old errors; it must not erase
  unrelated errors or unmodified values during initialization.
- Keep dependent fields in normal DOM order and use hidden for inactive groups.
  Revealing a group never steals focus; the next Tab reaches its first control.
- Native controls remain rendered and usable without JavaScript. Do not render
  inactive branches hidden on the server. The server remains authoritative for
  ownership, compatibility and accounting validation.

Form changes require keyboard browser tests for confirmation/cancellation,
conditional transitions, invalid POST recovery, editing and the no-JavaScript
path. Start viewport tests with the picker near the bottom; check the input,
results and active option in desktop and short mobile viewports. Use the isolated
E2E executor; inspect light/dark focus and active-state contrast. The contributor
and agent instructions make this a review requirement,
with regression tests included in the existing CI browser suite.

Forms use the established `form_field.html`, validation summary and forest/cream
inputs with caramel focus. Save/Cancel and destructive confirmations use the
same centered, compact action components across the application.
Checkboxes use `accent-caramel`. Server-side validation remains authoritative.

- PIX/account/debit choices state `Affects account balance immediately`.
- Credit card choices distinguish automatic due-date settlement from the
  card's dated confirmed-payment mode. Recording a confirmed payment updates
  local records for a payment already made at the bank; it never sends money.
- Own transfer forms identify source and destination, show both currencies, and
  explain that the transfer is not income or expense.
- Credit transaction forms show the target invoice/due date when known.
- Loyalty invoice awards show only the related invoice; points purchases show
  only their payment source and amount. Switching kind clears the inactive
  branch.
- Investment deposit forms require `Source account`; withdrawals require
  `Destination account`; yield forms state `Internal yield, no bank movement`.
- Loyalty redemption forms show points, target monetary amount/currency, IOF and
  IOF funding instrument as one reviewable cost block.

Conditional inputs may be rendered in full with server-side validation when a
zero-JS interaction would otherwise hide required accounting context. HTMX may
enhance dependent choices, but the submitted form must work without it.

## Card appearance

Debit and credit cards persist three presentation fields: `color`, optional
`gradient_end` and `gradient_angle`. Existing cards receive Graphite (`#253330`),
no second stop and an angle of 135 degrees. Colors require six-digit hex values;
the angle is bounded to 0–359 by form/model validation and database constraints.
Apply the banking migration before serving code that reads these fields. These
presentation values do not change balances, currencies, billing cycles, card
ownership or recorded invoice settlement modes.

Creation and editing share the `ColorPicker` widget and
`partials/color_picker_field.html`: six optional presets (Black, Blue gray,
Purple, Blue, Orange and Gold) sit beside a native custom-color input. The same
component styles bank marker creation and editing. Presets are shortcuts, not
an allowed-value enumeration; any valid six-digit HEX color remains accepted.
Each shortcut has a named 44px button, visible keyboard focus and a pressed
state synchronized with the native value. `static/js/bank-colors.js` adds those
buttons progressively; without JavaScript, the native color field and its
labelled datalist retain complete submission. Existing record colors and model
defaults are unchanged. Color inputs, including the gradient's second stop,
remain compact 48×44px controls rather than full-width bars.
Malformed bound colors render as ordinary text with their raw value and server
error, because a native color input would silently replace that value with black.
Corrected valid submissions return to the compact native picker.

Both card flows offer an explicit Use a gradient checkbox with a second color
and angle. Turning it off clears its
second stop; older clients posting only the original card fields preserve the
stored appearance. Account selection, duplicate-name checks and the prohibition
on moving cards with existing activity to another account remain authoritative.
Native POSTs, bound validation recovery and ordinary card editing remain usable
without JavaScript.

`static/js/card-appearance.js` progressively updates the local appearance preview
and optional gradient controls without saving a card. With JavaScript, the
angle uses a rotary handle: drag clockwise/counterclockwise to rotate the
gradient directly, with 0 degrees at the top, 90 at the right, 180 at the bottom
and 270 at the left. The single-focus slider supports arrow keys by one degree,
Shift+arrows or Page Up/Down by fifteen degrees, and Home/End for 0/359. Its
degree reading and preview follow the actual field value without animation lag.
The original named numeric input remains the native submission/fallback;
invalid server-bound angles stay visible for correction rather than being
silently clamped by enhancement. Disabling the gradient removes the dial from
the Tab order and ends any pointer drag. Reset, authorized history restoration
and HTMX initialization reuse the same controller.

The transaction sheet
receives appearance metadata only for its owned card choices and presents the
selected card alongside the existing searchable selector. Readable name and
bank/account text use a protected text surface, so arbitrary custom colors and
gradients cannot become the sole background behind essential labels. Decorative
colors identify the card; they do not communicate financial status or replace
the native selected record.
