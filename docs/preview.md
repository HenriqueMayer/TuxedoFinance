# Interface preview maintenance

The local automation in `scripts/preview/` maintains the static GitHub Pages
interface tour. It is development tooling and is not included in the published
Pages artifact.

## Layout

| File | Purpose |
|---|---|
| `scripts/preview/capture_preview.sh` | Creates isolated temporary storage, starts Django locally, validates all captures and cleans up. |
| `scripts/preview/seed_preview_data.py` | Populates two disposable, localized profiles with synthetic financial data. |
| `scripts/preview/capture_preview.js` | Signs in to the temporary profiles and captures seven areas in both themes and languages (28 images). |
| `scripts/preview/serve.py` | Owns the loopback capture server and serves the committed static tour for tests. |
| `tests/preview/playwright.config.js` | Serves and validates the static English and Portuguese tours. |

The files that GitHub Pages publishes remain in `preview/`. Preview browser
assertions remain in `tests/preview/`, and `.github/workflows/pages.yml`
publishes only `preview/` after changes reach `main`.

The tour uses the application's editorial language: short factual copy, the
bow-tie wordmark, local Inter typography, subtle ledger dividers
and balanced actions. The font license is included in `preview/assets/OFL.txt`.
The five direct destinations match the application's desktop sidebar and phone
dock; Reports stays under Home's section tabs, and New entry belongs to
Transactions. The preview opens directly on the dashboard, without a large
introduction or video. Home and Transactions expose New entry as a direct action
to a separate view of the actual application form, including its credit-card
miniatures. These are synthetic captures, not an editable financial session.
With JavaScript, native hash
links show one workspace at a time and preserve browser Back/Forward and the
current section when switching languages. Without JavaScript, all six sections
remain readable through the same anchors. Existing section anchors and image
paths remain valid.
Its dark theme matches
the application's `night` tokens in `assets/tailwind.config.js`: background `#101010`,
surface `#1B1B1B`, raised/hover surface `#262626`, and muted text `#B8B8B8`.
Caramel actions and the financial colors in application screenshots retain
their meanings. Keep both language editions and their captions in sync with the
current dashboard and transaction navigation when refreshing captures.
The synthetic profiles also demonstrate a BRL 2,000 account reserve, an excluded
USD account, a monthly cash pot, card appearance and explicit category budgets.
The Accounts capture deliberately opens one synthetic institution's internal
workspace. The Plan capture shows the current monthly availability and category
limits at `/planning/`; simulations remain a secondary tool. The captured budget
limits do not reserve balances or generate financial operations.

Captures use the complete 1440 × 1000 viewport, starting at its left edge, so the
shared sidebar remains available in original images and the lightbox. The tour
thumbnail crops the captured header/sidebar through CSS, avoiding a second
navigation shell inside the interactive preview. Home and New entry also omit
their captured duplicate section/title bars: their crop starts at y=230 and
y=220 respectively, retaining the balance/form panels. The tour supplies the
real headings and New entry action above those images. If the application frame's
dimensions change, update the documented offsets in `preview.css` together with
the captures. Every area has its own light/dark capture; do not invert image
colors or reuse a light capture in a dark shell. All screenshots come from the
checked-out application, including unreleased changes. Local regeneration does
not publish the tour or change the application version.

Both root READMEs link directly to the tour instead of embedding a static
screenshot or demo video. The preview remains the primary action. Earlier
recordings and review frames stay under ignored `.local/` as historical evidence;
do not package them in the repository presentation.
The shared native SVG cover lives in `docs/assets/readme-cover.svg`; its
bow-tie geometry follows the public homepage.
The prominent preview action uses `docs/assets/preview-link.svg`, with a native
link and localized accessible text in each README.
Keep equivalent English/Portuguese content and the published-release versus
current-checkout distinction. The READMEs include a copyable published-image
Docker quick start; detailed configuration, updates and backup procedures belong
to the Docker and operations guides. Retain earlier README anchors as aliases.

## Commands

Repository and quick-start links open a separate tab with `noopener noreferrer`.
This keeps GitHub outside the tour iframe, since GitHub does not allow framing.
Embedding sites must allow `allow-popups allow-popups-to-escape-sandbox` in
addition to the script and origin permissions used by the tour.

For local browsing, open `preview/index.html` or `preview/pt-br/index.html`
directly. Language links include `index.html` so they also work with `file://`
and JavaScript disabled. If an embedded browser blocks local files, serve the
tour from the repository root with:

```bash
python3 -m http.server 4173 --bind 127.0.0.1 --directory preview
```

Then visit <http://127.0.0.1:4173/pt-br/> for Portuguese.

Install the [development prerequisites](../CONTRIBUTING.md#prerequisites),
then run maintenance commands from the repository root. This workflow is
separate from the disposable application smoke tests (`npm run test:e2e`):

```bash
npm ci
npx playwright install chromium
npm run test:preview
npm run preview:capture
```

`npm run preview:capture` refuses to seed the repository workspace, generates
ephemeral credentials, stages every image before replacing versioned captures,
and removes its temporary database even when capture fails. Never weaken those
guards or use real financial records for the public tour.

The capture server binds an automatically allocated loopback port and publishes
its URL only after binding; there is no released-port window in which another
server can be mistaken for the capture application. The shell checks that its
server is alive before and after the readiness request. The browser script
requires that explicit URL instead of defaulting to an existing installation.

Static preview tests choose an available loopback port, refuse to reuse an
existing server and check an execution-specific readiness endpoint. Their
artifacts stay in `.local/test-results/preview/` and the CI HTML report in
`.local/playwright-report/preview/`. Running tests does not regenerate screenshots;
only the explicit `preview:capture` command replaces the staged public images.
Review desktop and phone renders in both languages/themes, including real
keyboard travel between workspaces/actions, history and language context,
lightbox focus restoration, final actions above the phone dock and native
no-JavaScript access. Public copy describes the app; capture, version and
publication caveats belong in this guide rather than an interrupting banner.
