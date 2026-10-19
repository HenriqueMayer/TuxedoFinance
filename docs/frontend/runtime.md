# Frontend runtime, assets and translations

[Frontend index](../frontend.md) · [Interface map](../interface-map.md)

The current design-system release preserves the server-rendered Django
Template Language and precompiled Tailwind CSS visual system. There is no SPA, JavaScript
framework or client-side chart library. Shared JavaScript progressively enhances
navigation/history, record choices, dates, live filters, payment appearance,
category allocation, chart inspection and the homepage illustration. Native
controls and server-rendered responses remain the source of truth.
User-submitted mutations use CSRF-protected POSTs, and filters have
plain GET fallbacks. Some page reads synchronize derived ledger records before
rendering; see [request-time synchronization](../architecture.md#request-time-synchronization).
The [assistant context collector](../apps/assistant.md#structured-financial-context)
is deliberately read-only and does not perform that synchronization. Its utility
panel is outside `main`; whole-body HTMX navigation reconstructs it and refetches
owned conversation data. The native assistant route remains the no-JavaScript
path. No model SDK, provider request or external script
is enabled by this local foundation.

Use the [interface map](../interface-map.md) for routes and component ownership.
This guide owns interaction protocols; app guides describe their financial
meaning and exceptions. Dated audit outcomes belong in [reviews](../reviews/README.md).

## Asset build and versioning

Tailwind CSS is generated ahead of time into `static/css/app.css`, so full-page
navigation never waits for browser-side class discovery or CSS compilation. The
generated file is versioned with the application and does not require Node/npm
at runtime. Frontend tooling is pinned in `package.json`/`package-lock.json` for
development and CI. Follow the [frontend build workflow](../../CONTRIBUTING.md#frontend-and-translations)
after changing Tailwind classes or tokens.

The [style-source index](../../assets/README.md) identifies the shared and
workspace CSS owners. `assets/css/tailwind.css` remains the ordered build entry;
the browser receives the same compiled stylesheet rather than separate source
imports. Preserve cascade order when changing an import or responsibility.

The one-off build uses pinned Tailwind 4 and PostCSS through
`scripts/build_css.mjs`, avoiding the CLI file-watcher dependency chain and its
unpatched braces advisory (GHSA-vfj7-8cjw-p6xm). `npm audit --audit-level=high`
remains mandatory. The existing JavaScript theme configuration remains explicit;
compatibility tokens preserve Inter, the neutral palette, small shadows/radii,
placeholder contrast and forced-colors keyboard outlines. The responsive section
title keeps its previous line height. CSS is built for current browsers supporting
cascade layers and modern color functions (Chrome 111+, Safari 16.4+, Firefox 128+).
Run `npm run build:css -- /absolute/output.css` to check a temporary build without
changing the committed asset. The build does not watch files or run in production.

Load CSS and JavaScript with `{% asset 'css/app.css' %}` (from the `assets`
template library). Its content digest versions the bytes served by source
finders in development and by WhiteNoise's collected tree in production.
`base.html` carries the document's asset revision. The runtime sends that revision
on HTMX requests, including requests that suppress HTMX's own headers. When a
GET would combine old assets with new markup, middleware requests one full
navigation to the intended URL. Legacy tabs also recover on their next GET.
POSTs and invalid form responses are never replayed or discarded by this guard.

## Progressive navigation

Same-origin links inherit `hx-boost` from the page shell. HTMX keeps the current
document visible while it requests the next server-rendered page, then replaces
the body and updates browser history. Native links remain the fallback whenever
JavaScript is unavailable. Mutating forms, uploads, locale changes, logout and
download links explicitly opt out of boosting, so POST, CSRF, validation and
file responses keep their ordinary Django behavior. GET filter forms may use
HTMX when they target a documented page or island update. Body swaps for the
same pathname preserve viewport and focus; navigation to another pathname moves
focus to the new `h1`. Report and investment chart islands keep their existing
focus and scroll restoration. The
investment movement island updates filters independently while preserving scroll
and focus. Explicit pagination links return to the beginning of the movement
section instead of the top of the page; plain GET links and the section anchor
provide the no-JavaScript fallback.

## Private history

The shell disables HTMX DOM snapshots with `hx-history="false"` and requests
full HTML on history restoration (`historyRestoreAsHxRequest=false`). An HTML
snapshot indexed only by URL can reveal the previous account after logout and
another login in the same tab. The runtime discards the legacy HTMX session
cache at initialization and before history traversal. Cache-miss requests carry
the document's asset revision, and login/asset redirects finish with native GETs
so the URL, document head and form targets remain coherent.

Authenticated HTML also uses `Cache-Control: private, no-store, no-cache`.
The browser's separate BFCache can restore a frozen document without loading
scripts again: on a persisted page hide, the document is hidden; on a persisted
page show, a native replacement GET reauthorizes it. A GET is deliberate because
reloading a frozen POST validation response could resubmit that operation.

Back/Forward therefore reauthorizes through the server. The small form/location
snapshots owned by `previous-workspace.js` remain scoped to user, date format,
language and asset revision and apply over freshly authorized content. They do
not replay POSTs. The native persisted-return path restores them only after that
fresh GET and a matching identity. The contract does not promise remote
revocation of content already displayed or of an old offline document.

Browsers can also restore live form values onto fresh HTML, independently of
both caches. Editable private POST forms use `autocomplete="off"` to prevent
that native draft restoration, including without JavaScript. History recovery
resets controls to the authorized HTML defaults before applying a matching
workspace snapshot; bound server errors and values remain the defaults.
Without JavaScript, Back/autofill no longer recovers private unsent drafts;
ordinary submissions and server-rendered validation recovery still work.
Login/signup retain their explicit authentication autocomplete behavior.

## Translation convention

All new fixed interface copy must be marked at its source: `gettext_lazy` for
deferred Python declarations, `gettext` for runtime Python messages,
`{% translate %}` (the modern spelling of `{% trans %}`) for short template
strings and `{% blocktranslate %}` for longer copy or interpolated values.
Update and compile the `pt_BR` gettext catalog after changing marked strings.
The nine system-provided category names are translated once during account
creation and then stored as user-owned data. Other category/subcategory names
and all user-entered titles, notes, institutions and financial data are not
translation keys and render verbatim.

HTMX report and investment chart islands need no separate locale mechanism.
Their requests retain the language cookie, pass through `LocaleMiddleware` and
render translated fragments in the active request language.

## Automated browser checks

`tests/e2e/shared/design-system.spec.js` checks translated landing copy, local HTMX,
CSV downloads, responsive navigation, dashboard month states, conditional loyalty
fields, monetary-yield forms, salary-sandbox calculations and help, and report
navigation. These checks cover
browser behavior that template assertions cannot prove.

Run `npm run test:e2e` for an isolated application and temporary database. CI
uses the same executor and retains configured browser failure artifacts. See
[CONTRIBUTING.md](../../CONTRIBUTING.md#browser-tests) for setup, argument forwarding,
logs, and the advanced manually managed path.

`tests/preview/preview.spec.js` validates the static GitHub Pages tour in both
languages, including the committed image dimensions, theme persistence,
accessible screenshot dialog and mobile layout. Run `npm run test:preview` for
that isolated site. `npm run preview:capture` regenerates its screenshots using
only disposable synthetic records in a guarded temporary database. The capture
and test configuration is documented in
[preview maintenance](../preview.md).
