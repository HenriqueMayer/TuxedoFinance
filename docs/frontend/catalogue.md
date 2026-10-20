# Design Lab catalogue

[Frontend index](../frontend.md) · [Interface map](../interface-map.md)

<a id="catalogue-visual-experiment"></a>

## Canonical design catalogue

The [visual catalogue](../design-system.html#public-homepage) contains the approved
public homepage, workspace frame and entry sheet alongside component specimens.
It uses adjacent `design-system.css`, `design-system.js`,
`design-system-layers.js` and the compatibility wrapper
`design-system-calendar.js`; the application does not load these catalogue
files. The calendar wrapper delegates to `static/js/date-picker.js`; the Paper
Layers wrapper delegates to `static/js/paper-layers.js`, also used by the public
homepage. Their catalogue IDs and styles stay independent. Inter and the semantic
palette remain unchanged. Award
references and adaptation notes are
linked inside the catalogue; their historical recognition is not a claim about
the projects' current versions. The static HTML references these assets with
their first 12 SHA-256 digits as a query version; refresh those values when the
assets change to avoid stale review sessions.

Paper Layers is the sole homepage illustration. Five complete local SVG planes
rotate smoothly from a large, centered horizontal bow tie into a vertical
workspace structure: left paper, ledger rules, knot, contour rings and right
paper correspond to Home, Transactions, Accounts, Investments and Plan. Hovering
the painted bow tie reveals the five workspace descriptions and native preview
links; empty illustration space does not activate a hover preview. A stable,
invisible folded silhouette keeps rotation from losing the entering pointer.
The index retains its layout space while closed, but is invisible, inert and
excluded from accessibility navigation. Pointer travel from the drawing to its
links keeps it open. Leaving the combined region closes a mouse-only preview;
deliberate activation or focus inside the index keeps it open. This homepage
hover disclosure does not change the primary application's deliberate navigation
contract.

With JavaScript, the SVG itself becomes a focusable, labelled `role="button"`
control. Click, touch, Enter and Space toggle the map; there is no separate
textual toggle. Its `aria-expanded` reflects actual map visibility,
`aria-pressed` reflects deliberate pinning and `aria-controls` identifies the
index. Escape returns focus from an index link to the SVG before closing the map. Size and motion
preference resets preserve visible keyboard focus without scrolling. Offscreen
navigation to a chosen workspace leaves focus alone so it cannot pull the page
back to the artwork. Deliberate closure cannot immediately reopen under a
stationary pointer while the drawing folds.

The desktop composition moves the drawing beside the stationary index; compact
layouts keep it centered above the links. Link hover/focus highlights the matching
plane and connector, with visible keyboard focus taking precedence over a parked
mouse. A short index fade and bounded pointer parallax do not move link text or
hit targets. Native preview links reveal their destination before normal anchor
navigation, preserving URLs, history and modified-click behavior. Connector
endpoints are cached with a ResizeObserver. One bounded `requestAnimationFrame`
loop updates SVG transforms and paths, stopping when settled, offscreen or on
window deactivation. Reduced motion keeps a static diagram and instant map
revelation through hover or SVG activation, without animation frames. Without
JavaScript the complete drawing and a native five-link workspace index remain
available. Copy describes features and actions directly; the accent under
“clear” remains decorative.

The validated [Workspace example](../design-system.html#navigation) is the only
catalogue shell. The former `#shell` destination remains an alias of
`#navigation`; the obsolete shell and mobile overlay specimen are removed.
Five native links choose contained Home, Transactions, Accounts, Investments and
Plan examples with JavaScript and retain their anchor destinations without it.
The account options use a deliberate native `details.lab-account-menu`
disclosure. The toolbar calls this section Workspace and the shared component
examples Patterns; section numbering runs from 00 / Homepage through 13 / Design
decisions. These catalogue labels do not rename application workspaces.
During native Back/Forward, the catalogue reveals the selected view on
`popstate`, before the browser restores its persisted position; `hashchange`
also handles ordinary fragment navigation. This follows the browser's
[history event order](https://developer.mozilla.org/en-US/docs/Web/API/Window/popstate_event#when_popstate_is_sent)
and avoids restoring against a hidden example. The catalogue does not force a
scroll position or replace native history restoration.

The catalogue represents components through their meaningful states, variants
and local interactions. A quieter presentation must retain domain information,
institution identity, financial warnings and usable controls rather than reduce
each workspace to generic cards. The Accounts example uses native
`details.bank-overview-card.lab-bank-overview` disclosures to reveal each bank's
accounts and cash totals. The existing `--bank-color` edge and `.bank-marker`
accompany a textual bank name; `.bank-bookmark` identifies the bank on the
separate invoice example. These markers convey institution identity, not payment
status, and never replace readable labels. Synthetic cash balances and card debt
remain distinct. Opening a bank disclosure shows local sample detail; it does
not navigate, settle an invoice or imply a backend write. Application bank
overview links retain their existing navigation.

Catalogue CTAs center their label/icon group, use a 12px radius and retain a 44px
minimum target. Brief color, border and click feedback may move only the arrow by
up to 2px. Hover/focus never changes a button's shape, dimensions or surrounding
layout. Workspace navigation adds color/opacity feedback, a 1px icon response and
a short content fade only in the enhanced example. Reduced motion disables these
transitions and spatial responses while retaining visible focus and selected states.

The catalogue entry sheet, `#lab-transaction-form`, has a maximum width of 960px
and no instructional sidebar. Its text/date/select fields and choice targets
share a 44px minimum height for both pointer types. Description, Amount, Date
and Category form a responsive reading grid. Other catalogue specimens, including
login, monthly overrides and daily consultation, retain 40px fields for fine
pointers and 44px for coarse pointers. The login example remains read-only and
fictitious; these presentation choices do not change application forms.

Type (`#lab-entry-type`) and Payment method (`#lab-entry-payment`) use native
radio inputs in labelled fieldsets, styled as segmented choices without an
initial selection. A quiet shared track holds stable 44px targets; the selected
surface, stronger text and short underline distinguish selection without
resizing a segment. Only these short-choice groups hide the native circular
indicator visually. Their inputs remain focusable, with a visible outline on
the containing segment, rather than using `display: none`. Tab/Shift+Tab, Space
and arrow keys retain native radio behavior in both themes. Colored card tiles
and appearance presets retain their own native checked indicators and colors.
The payment values match the transaction model: `ACCOUNT`, `PIX`, `DEBIT_CARD`
and `CREDIT_CARD`.
Income offers only Account/PIX. Account and PIX reveal the shared searchable
account selector; PIX excludes accounts without PIX enabled. Debit reveals its
own card choices, while Credit reveals the local credit-card tiles. Names,
bank/account context and a native checked indicator identify each card; color
never replaces those labels. Credit purchases are described as invoice activity,
not an immediate account debit.

`design-system-calendar.js` initializes the shared calendar engine for
`input[type="date"][data-lab-calendar]` in this catalogue. It serves
the entry Date (`#lab-entry-date`) and the card editor's optional Manual
settlement from (`#lab-card-manual`). Each field keeps its native type, name,
form association and ISO `YYYY-MM-DD` value. Without JavaScript or native modal
dialog support, the original date input remains usable. The `.lab-date-field`
calendar icon is decorative and shown only after enhancement. A click anywhere
in the field, Enter, Space or Alt+ArrowDown opens the calendar; ordinary focus
or Tab arrival does not open it.

One native modal `dialog#lab-calendar`, labelled Choose date, is reused by the
two fields. Its native Month and Year controls accompany a 42-day grid running
Monday through Sunday. One enabled day participates in the Tab sequence; arrow
keys move by day/week, Home/End reach the current week's boundaries, PageUp/Down
change month and Shift+PageUp/Down change year. Month/year changes clamp missing
days, including leap days, and respect the owning input's `min`/`max` limits.
Enter, Space or a day click commits the ISO value and emits bubbling `input`
and `change` events. Today and Clear are explicit actions. Close, Escape and
outside dismissal leave the value unchanged and restore focus without scrolling;
reset closes the calendar before the owning form restores its native defaults.
Hiding or disabling an owner closes its popup without moving focus back to an
inactive field. Selecting a date never submits either form.

The compact calendar fits the viewport, follows both catalogue themes and keeps
its keyboard and selected states with reduced motion. Its interaction reference
is the [WAI-ARIA date-picker dialog pattern](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/examples/datepicker-dialog/);
the [native date-input contract](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/input/date)
remains the value and fallback boundary. Browser regression coverage is not
assistive-technology certification; screen-reader interoperability still needs
separate manual validation.

Categories, accounts and the card editor's bank/account fields continue to reuse
`static/js/forms.js` and the [shared searchable-choice contract](forms.md#keyboard-and-choice-contract).
The user explicitly authorized record selection through native radio tiles for
the catalogue's small debit/credit card examples. This is a local visual exception;
it does not change the application-wide record-picker contract or `AGENTS.md`.
Conditional choices begin empty. Deliberate type, payment or bank changes clear
incompatible values and remove inactive controls from the Tab order without
discarding compatible input. Invalid entry submission focuses the first invalid
control and reveals it below the sticky catalogue header, including shared search
choices. Existing search confirmation, cancellation and viewport behavior remain
unchanged.

The native `details#lab-card-editor` contains a local credit-card editor. Its
controls explicitly use `form="lab-card-form"`, which identifies an independent
GET form beside the entry form; opening or submitting the editor cannot submit
its fields as a transaction. The sequence is Bank (`#lab-card-bank`), an account
filtered to that bank (`#lab-card-account`), then an editable Nickname
(`#lab-card-name`). New previews offer Graphite, Plum, Copper and Forest color
presets. Graphite is the appearance default. The billing-cycle disclosure keeps
required Closing day and Due
day empty, constrained to 1–31; Card type defaults to Physical and the manual
settlement start date is optional. These controls represent the real credit-card
fields; the nickname corresponds to its existing `name` field.

Editing a local card additionally exposes a native base-color input
(`#lab-card-color`) and an optional gradient with a second color (`#lab-card-end`)
and direction (`#lab-card-angle`). The preview protects text contrast when custom
colors or gradients would make labels unreadable. Catalogue colors and gradients
are local preview data; the application's persisted card appearance is described
under [card appearance](forms.md#card-appearance). Creating or
updating a preview changes only the current document's card data and never selects
a card on the user's behalf. Enhanced entry/card previews use no database,
browser storage or network requests. Without JavaScript their independent forms
submit read-only GETs to this catalogue; no financial record or card is saved.
Real Django validation, authorization, accounting and POST recovery remain
authoritative. The application adoption above preserves its shared record
selectors rather than promoting the catalogue's local card-radio exception.

The same editorial frame extends to data, components, layout, motion, icons and
workspace patterns: consistent two-part headings, fine rules, quiet specimens and
sentence-case action labels. These specimen styles preserve the approved
type/palette examples and financial meaning in labels and amounts. Semantic-color,
outlook and planning tables use labelled, keyboard-focusable inner horizontal
scrolling regions instead of widening the page. Print styling fits the tables to
the printed page instead of retaining their screen minimum widths or clipped
scroll containers.

Component previews isolate their stacking contexts so their navigation cannot
paint over the catalogue header. Internal anchor targets also leave room for
that header. Review desktop/mobile, both themes, keyboard/touch, invalid recovery,
reduced motion and native fallback with
`npm run test:e2e -- tests/e2e/catalogue`.
The application adopts the common presentation through shared components;
catalogue examples remain synthetic and never write application data. See the
interface map for the retained framework and paused-feature boundaries.

The assistant specimen reuses `static/js/assistant-markdown.js` for the bounded
display subset used by the application. It never renders model HTML or creates
actionable model-supplied links; verified synthetic source links stay separate.
Its Thinking and Writing phases are labelled synthetic progress, with the same
Stop/recovery and stationary composer behavior. The optional transaction-review
scenario shows native amount, date, category and payment instrument before
Confirm preview or Discard preview. These controls change only page-memory demo
state and make no HTTP write, provider request or financial posting. The native
reading fallback describes the same review boundary.
