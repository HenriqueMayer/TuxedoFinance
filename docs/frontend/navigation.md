# Frontend navigation, history and overlays

[Frontend index](../frontend.md) · [Interface map](../interface-map.md)

## Root layout and navigation

`templates/base.html` continues to own the page shell, theme setup, public or
authenticated navbar, messages, content block and footer. The authenticated
navigation becomes:

```text
Home | Transactions | Accounts | Investments | Plan | Analytics
```

`Accounts` remains active for nested bank, account, card, invoice, movement and
loyalty routes. `core.workspace_navigation` supplies the same six destinations
and active states to a persistent desktop sidebar at `lg` (1024px)
and a fixed bottom navigation below that breakpoint. Primary links navigate
directly, without hover submenus. Analytics owns financial and investment charts; Home retains operational
indicators and records. Workspace section tabs keep categories, invoices,
loyalty, exchange rates and investment setup discoverable. The Accounts rail reveals a
focused link completely when its four tabs exceed the available width; focus
and native horizontal scrolling remain intact. Accounts uses four
explicit sections: Accounts, Invoices, Loyalty and Exchange rates. Its section
rail scrolls horizontally on small screens, preserving full labels, at least
44px targets, visible keyboard focus and the selected section in nested editors. Paused net-worth and
statement-import interfaces stay out of navigation.

The Tuxedo Finance brand in the desktop sidebar and mobile toolbar opens the
financial dashboard (`/dashboard/`), matching Home/Início in the workspace
navigation. The product cover (`/`) is a public entry page and the destination
after POST logout; an authenticated GET/HEAD to `/` redirects to the dashboard.
The public navbar brand continues to open that cover. Brand links use the
shared native/HTMX navigation and unsaved-edit protection.

The body reserves room for the sidebar and bottom bar, including the mobile
safe area. Searchable-choice viewport calculations also account for the bar.
The bottom bar is the sole compact-label typography exception: its six
labels use 10–11px, never below 10px, with tighter spacing on narrow screens.
Compact labels use Entries and Invest in English and Investir in Portuguese;
accessible names retain the full workspace identity.
Mobile active labels keep medium weight so complete labels fit at 320px;
foreground color and the caramel background identify the selected destination.
Every destination retains a touch target of at least 44 × 44px and visible
keyboard focus. Check complete labels in both languages, including the active
medium-weight state at 320px.

The mobile account-options dialog contains settings, language, theme, project
documentation and logout. It slides in, locks page scrolling, makes background
content inert, contains keyboard focus, closes on Escape and restores focus to
its trigger. Native account options remain available without JavaScript.

`partials/language_selector.html` appears in account options on desktop and the
mobile menu, with an explicit native fallback when JavaScript is disabled. It
posts the current path and `en` or `pt-br` to Django's
`/i18n/setlang/` endpoint (named route `set_language`); JavaScript submits on
change and the `noscript` Apply button preserves the server-rendered fallback.
The choice is stored for one
year in Django's language cookie, not local storage or the user model, and URLs
have no locale prefix. The light/dark choice remains in local storage so both
preferences survive later visits in the same browser.

HTMX 2.0.10 is vendored at `static/js/vendor/htmx.min.js`; the application does
not contact a JavaScript CDN at runtime. CI verifies the vendored file against
the upstream release checksum before running browser smoke tests.

Django's content-security-policy middleware restricts script sources, forms,
images and connections to this installation. Inline scripts and styles remain
allowed because translated progressive-enhancement copy and server-calculated
chart geometry are rendered directly by Django templates. Inter is a vendored
Latin variable font with its SIL Open Font License in `static/fonts/`; font,
script and style requests stay on this installation. Language selection uses a delegated local
listener instead of an inline event handler and retains its `noscript` submit.

## Assistant panel

The authenticated assistant is a utility alongside the six direct workspace
destinations. Its native `/assistant/` link remains usable without JavaScript.
The enhanced panel belongs outside `main` so its actions cannot submit or
capture a financial draft. Whole-body HTMX navigation reconstructs the panel;
an owner-checked server request reloads its selected conversation instead of
replaying a preserved DOM transcript.

At desktop widths the panel is a fixed, nonmodal overlay above the workspace.
Opening or closing it must not reserve a column, change body/main padding or
resize filters, charts or forms. The page keeps its original geometry and remains
usable beside the overlay. Narrow screens retain the modal, focus-contained sheet.
The compact titlebar groups the unchanged Tuxedo mark and identity with
stationary, labelled Minimize and Close controls. Keep the controls adjacent,
with a fine separator and restrained hover/focus feedback rather than individual
heavy outlines. Local history remains accessible text without a repeated visible
subtitle. History, the current-page link, New conversation and Delete share one
compact toolbar beneath the titlebar, with deliberate action disclosures.
Context is a location cue: show the current workspace/period as an authorized
link and retain its accessible label without a separate visible label or row.
Do not repeat balances, technical timestamps or a financial evidence inventory.
Structured evidence remains in the backend context contract. User messages align
to the right in a restrained paper-colored bubble; assistant text reads naturally
on the left, with references beside that answer. Keep role labels available to
assistive technology without repeating a visible assistant heading before every
answer. Use compact, readable chat typography and restrained message spacing.
Show verified source links once in the answer's footer. Enhanced rendering can
omit only a final reference-only paragraph whose destinations and source labels
all match that footer; retain explanatory labels, other prose and inert unverified links. Raw message storage,
Markdown copy/download and the native escaped-text fallback stay intact.
Keep the transcript as the independently scrolling area, above a persistent
composer. History/actions and the composer must not disappear while reading an
older message. Long replies wrap without widening the panel.
Activating the context link for the document already open minimizes the panel
without a GET or form reset, including when the signed scope omits a navigation
origin (`next`). Other source destinations retain normal departure protection.

The cat and its orbit use smooth 4-second and 12-second CSS transform cycles
inside the fixed mark, with two stars on opposite sides of the orbit. Keep the
cat at 28px inside the 48px orbit and retain the 60px launcher target.
Never animate the button's target, focus ring or surrounding layout. Honor
`prefers-reduced-motion` for both the launcher and header artwork, including the
Design Lab specimen; keep provider availability and its recovery state explicit.

Opening, minimizing, restoring and closing are deliberate keyboard, pointer or
touch actions. Minimize hides the panel behind a named restore tab and retains
the current draft, model, effort and active reply in the current document. Its
adjacent Close control remains available without restoring the panel. It
does not cancel a generation. The tab reflects a pending/completed reply without
moving its target; restoring first performs an authenticated GET and restores
temporary text only when both user and Django session still match; temporary
model/effort also require the same linked account. A changed
account keeps its freshly authorized saved settings. Never store
an unsent chat draft in browser storage. Close discards that temporary composer
state, cancels the active reply and returns the ordinary launcher; it does not
delete saved conversation history or the last explicitly saved model/effort.
Those preferences live in the local owned account record, are revalidated on
load. Owned tool reads remain independent of the visible page or any legacy
initial-snapshot parameter. Preserve the workspace's scroll, selected
filters and unsent financial form values. Minimize returns focus to the restore
tab, Close to the launcher. The narrow-screen presentation keeps
its heading, window controls, conversation actions, composer and cancellation state inside
the viewport and above fixed navigation/safe areas. Visible focus, Escape and
Tab/Shift+Tab behavior must match the panel's declared modal behavior; background
content must not remain keyboard-active behind a modal surface. When the visual
viewport is shorter than 400px, trim secondary header text and keyboard hints
and cap the editor at 44px, while keeping Context, model/effort controls and
Send/Stop reachable. Honor the visual viewport rather than only height media
queries, because opening a software keyboard does not resize every browser
layout viewport. The native chat page can scroll vertically and retains a
minimum usable conversation height and clearance above fixed navigation.

Context follows an explicitly authorized local origin, not HTML scraped from the
current page. Only its allowlisted route/query is signed for the current Django
user; ownership is checked again by the server. Do not include unsent financial
form fields in a context update. Page navigation, filter changes and a restored
private document must not retain another user's context or transcript.
Closing, replacing or departing clears transcript/context HTML before a new
authorized fetch; only the selected conversation UUID remains in user-scoped
memory. Minimized HTML stays inaccessible in its hidden panel and cannot be
revealed before the restoration GET reauthorizes the user and session. A
different or expired session discards the temporary state and hidden transcript.
An interrupted or cancelled request must not reveal an earlier hidden transcript.
Custom assistant fetches respect asset-recovery headers before inserting HTML;
recovery offers a validated native GET through the ordinary unsaved-edit guard,
without replaying a POST or automatically discarding a financial draft.

Account connection settings use native POST/redirect forms outside HTMX. The
ChatGPT sign-in control opens a separate tab, preserving the authenticated
settings tab for final confirmation. It is disabled until authorization is deliberately enabled;
an authorized account still requires the separate inference gate. The
settings link in the panel retains normal departure protection for edited
financial forms. Callback pages contain no account or authorization code and
require confirmation in the original authenticated settings session.

The settings document uses `Referrer-Policy: same-origin` and authorization
forms retain `noopener` without `noreferrer`: Chromium otherwise submits an
opaque `Origin: null`, which Django correctly rejects. Its view-specific CSP
allows form redirects only to self and the exact official authorization endpoint;
other pages retain the application's self-only form policy. Outbound redirects
and callback pages retain `no-referrer`. Never exempt these POSTs from CSRF or
trust a null origin to make the flow work.

With either gate off, keep unavailable status explicit and Send disabled; never
render a fake streamed reply. When eligible, the model picker starts empty until
an explicit selection is saved for that local user and linked account; later
loads restore only catalogue-valid saved model/effort choices. The
assistant reads owned saved information through tools by default, independent of the page. No per-request data checkbox is shown and current-page drafts are never scraped. Show safe Markdown, selected model,
pending/terminal state, verified local references and a deliberate Stop action.
The message editor starts at one line and grows to a bounded height; extra lines
scroll internally. Keep Model and Reasoning effort in a deliberate Chat settings
gear disclosure below it, with a single-line model/effort caption and the
available Send/Stop controls. Long selection names truncate visually without
losing their full accessible text or widening the chat. Its upward surface stays
inside the panel and scrolls internally on short viewports. Keep native labelled
selects and 44px targets;
opening settings must neither resize the transcript nor move the message draft.
Only the selected account catalogue determines compatible effort levels.
Model default omits the override, and no effort is inferred from a model name.
Changing a model retains compatible effort or announces a reset to Model default.
Server validation rejects incompatible submitted pairs; reopen settings around
invalid fields for recovery, including the native form without JavaScript.
Settings opens only through click, touch or keyboard activation. Dismiss it on
outside click or Tab-away; Escape closes settings and returns focus to its gear
before a subsequent Escape minimizes chat. Keep only one chat action disclosure open.
Keep only the toolbar's lower transcript boundary and center the empty state.
The compact page badge keeps a 44px outer link target. Let the compact composer
frame provide its own border and theme-aware focus ring, without another divider
above it or an extra enclosing box. Minimized controls use the same quiet window
chrome; avoid framing an already framed restore tab again.
Send and Stop use stationary, labelled icon buttons
with at least 44px targets and visible focus; a smaller visual face must not
shrink those targets. Keep model, effort, consent and the message editor at least 44px
tall. Keep the privacy explanation inside History. The enhanced composer reveals
its short keyboard hint while focused, retaining the hint's reserved space so
focus does not move the composer or transcript; native fallback keeps it visible.
Enter submits through the same validated form; Shift+Enter inserts a line.
Composition/IME confirmation must not send a message. Preserve the draft on
validation failures and retain an ordinary native Send button without JavaScript.
Closing/replacing the panel or departing cancels its active stream and clears
hidden text before an authorized reload. Minimizing keeps the stream alive only
in the same current document; restoring never replays its POST. Never replay a POST on history restore.
Native submission waits for the bounded result and redirects to owned local
history without JavaScript. Preserve readable errors, empty model lists,
partial-output status and keyboard/mobile access above fixed navigation. The
[assistant guide](../apps/assistant.md) owns storage, routes, context and the
gated authorization/provider/action boundaries. Browser validation must cover
desktop/phone, both themes, real keyboard focus, HTMX navigation, account/logout
boundaries and the native page.

## Preserve the user's location

Every new or changed interaction that updates the current page must preserve the
user's viewport and interaction context. This includes type/category cards,
filters, sorting, pagination, refreshes, and inline edits or validation feedback.
Do not send the user to the page heading or scroll to the top after an update.
Treat navigation to another page and explicit links to a named section as
navigation, rather than as an in-place update.

- Reuse `static/js/navigation.js`: a successful HTMX body swap whose final URL
  has the same origin and pathname restores the scroll coordinates captured
  immediately before the swap. Query-string changes do not start a new page.
  The handler overrides inherited `show:window:top` with `show:none` and restores
  the surviving focused control with `focus({preventScroll: true})`.
- Give controls stable, unique IDs so keyboard focus can survive replacement.
  Do not add an unconditional `h1.focus()`, `scrollTo(0, 0)`, full-page reload or
  `show:top` to an update flow. Reuse the existing island restoration for partial
  updates; explicit section-navigation links may retain their named destination.
- Preserve URL/history and server-rendered GET/POST fallbacks. Native navigation
  without JavaScript remains usable; use meaningful section anchors where
  appropriate rather than relying on scripts for access to results.
- If filtering shortens the document, the browser may clamp the saved offset to
  the new maximum scroll position. This is the only automatic position adjustment
  expected for an ordinary update; do not jump to the heading as a fallback.
- Browser acceptance must begin at a nonzero scroll position, trigger the real
  interaction, wait for the swap to settle, and check scroll position and keyboard
  focus. Cover desktop/mobile and both populated and empty results. Also confirm
  that deliberate navigation to another page still opens that destination normally.

## Compact row-action menus

Ellipsis controls use `details.secondary-actions.compact-menu`. Opening requires
click, touch or keyboard activation; hovering or focusing a closed trigger alone
must not open it. Once opened, crossing neighboring rows or moving through a gap
toward an action must not open another row menu or close the chosen one. Use the
same native `details` name within a row-menu group so only one can be open,
including without JavaScript. The shared navigation runtime preserves summary
toggle, outside-click, Tab-away and Escape dismissal, with focus returning to the
trigger on Escape.

Regression checks must move the real pointer across adjacent row triggers after
opening one menu, then verify that its action still targets the original record.
Cover click toggling, switching rows, keyboard, touch, HTMX and the native
fallback. Changes to primary navigation or question-mark help must not silently
change this activation-only contract.

Card action links use their heading as `aria-labelledby` and supporting copy as
`aria-describedby`, keeping a short action name and an accessible explanation.

Record new UI/UX and domain-presentation decisions in their owning guide and use
focused code comments for interaction rules whose purpose is not obvious. Add
cross-cutting rules to `AGENTS.md` so future changes preserve them.

## Question-mark help

This contract is mandatory for every new or changed **?** help icon. Reuse
`partials/help_popover.html`, `static/js/help-popovers.js` and the `.help-*`
components in `assets/css/shared/primitives.css`, imported by the Tailwind entry.
Analytics and Sandbox share this behavior;
do not add independent click-to-pin tooltips or use a native title as the only help.

| Interaction | Required behavior |
|---|---|
| Mouse hover | Open only over the question-mark trigger. Close immediately when the pointer leaves that trigger, including travel into the explanation. Moving between the trigger’s SVG children does not close it. |
| Mouse click | Never pin help. Clicking outside dismisses it immediately. Only one help box may be open. |
| Keyboard | Tab focus opens help; Enter/Space can reopen it. Escape dismisses without moving focus; Tab away closes it. Pointer clicks must not leave a focus-driven tooltip stuck open. |
| Touch | Tap toggles help. Another tap, an outside tap or another help icon dismisses the previous box. |
| Navigation | HTMX swaps close help only when replacing its owning region; unrelated background previews retain it. History saves close floating help. Replacement controls initialize once. No duplicate fallback controls or event handlers. |
| No JavaScript | A native details/summary fallback exposes the same explanation by keyboard or touch. |

Help is rendered above cards/charts in a floating container attached to the body,
with a preferred width of **352 px**, a **12 px** viewport gutter and an **8 px**
gap from the icon. Its width must never inherit the icon or label width. Reposition
above the icon when needed, constrain height in short viewports, and allow internal
scrolling. Reposition on resize/scroll without moving the page or stealing focus.
Without JavaScript, the native disclosure opens a bounded panel at the bottom
of the viewport so labels near either edge cannot push its explanation offscreen.

Use 14 px text, 24 px line height, normal capitalization, left alignment and 16 px
padding. Give the explanation a short title and separated paragraphs; put formulas
in their own lightly shaded block. Keep paragraphs short and fully translated.
Use the shared light/dark surfaces, borders and visible focus. Do not put links,
form fields or other interactive controls inside a tooltip.

Pass a stable, unique `help_id`, a translated `help_label`, and either plain
`help_text` or a repository-owned `help_template`. The latter may use
`.help-paragraph` and `.help-formula` spans for structured copy. Template paths
must be authored literals, never user input. Both the tooltip and no-JavaScript
fallback render the same content; ordinary text remains escaped. The trigger's
accessible name explains its subject, and `aria-describedby` references the
`role="tooltip"` content.

```django
{% include 'partials/help_popover.html' with help_id='budget-help' help_label=budget_label help_text=budget_help %}
```

Review changes with actual pointer, keyboard and touch tests: enter/leave the
icon and content, outside click, click then leave, Escape/Tab, a second icon,
HTMX/history and the no-JavaScript fallback. Inspect English/Portuguese copy in
both themes at desktop and mobile widths; assert box width/viewport bounds so
an extremely narrow column cannot pass as readable help.

## Previous-screen continuity and balance ranges

Browser Back/Forward restores workspace context from tab-local sessionStorage,
scoped to the authenticated user and interface identity. Capture each visited
workspace before navigation, including query parameters, unsent named fields,
repeated simulation rows, disclosures, focus and scroll. History traversal
restores into freshly rendered forms without replaying submissions or emitting
input/change events. Do not render a separate Resume previous screen control.
Do not add redundant page-level Back to links: shared navigation and section
tabs identify destinations, and browser Back/Forward handles history. Keep form
Cancel actions and date-reset controls such as Back to today; these serve their
own explicit actions rather than duplicating page navigation.
When HTMX replaces the page body, update the active workspace at `afterSwap`:
the next link can be activated before `afterSettle`. Apply the saved fields on
`historyRestore` even when the browser's URL already matches the tracked URL;
the tab-local form snapshot may contain unsent values from the previous visit.
Financial HTML is never restored from HTMX's DOM cache; the
[private-history contract](runtime.md#private-history) requires an authorized GET first.
Do not recapture the form baseline at `afterSettle`: users can edit the new
page during the settle delay, and those edits still require a departure warning.
Passwords, uploaded files, hidden fields/CSRF tokens and account settings are
excluded. Keep only the current and immediately previous URL snapshots, and discard
them when the user or interface identity changes. Native browser Back and HTMX history must
both work; navigation without JavaScript retains the browser's own history.

Confirm departure when a POST form has been edited or a simulation result is
visible. GET filters and chart selections are read-only view state: preserve them
for Back/Forward without treating them as unsaved operations. This applies to
clicked navigation, history traversal and native refresh/tab-close warnings.
For internal links and same-document history traversal, use the shared translated native
`dialog` with the application's visual tokens. Keep editing receives initial
focus; Tab stays in the dialog and Escape or backdrop activation cancels and
returns focus. Leave page continues the original authorized GET/HTMX navigation.
Modified/new-tab clicks keep their normal behavior. An anchor on the current
path/query is not a departure; a link to another screen with a record fragment
still uses the dialog and preserves that fragment on approval. Refresh, tab
close, cross-document history and external browser-owned navigation use
`beforeunload`; that warning's appearance
and wording belong to the browser. Canceling either direction of history
traversal leaves the current
page and its unsaved state intact. An explicit form submission does not prompt.
Successful and invalid POSTs are handled by the server; do not preserve a
submitted form as an unsent history snapshot. The restored inputs remain unsaved
and simulations must be recalculated after restoring edited inputs. This is navigation recovery, not financial undo or a
saved draft.

## Period navigation

Period controls use `period-navigation`: previous/next keep fixed slots around
the caption, including disabled bounds. Reset actions occupy a permanent second
row. Do not place reset beside the rail in a content-sized flex group: revealing
it must never move the previous arrow into the old next-arrow position. The same
rule applies to dashboard, report and investment chart periods and catalogue
examples. Preserve each control's original date scope and query parameters.
