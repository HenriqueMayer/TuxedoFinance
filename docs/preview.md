# Interface preview maintenance

The local automation in `scripts/preview/` maintains the static GitHub Pages
interface tour. It is development tooling and is not included in the published
Pages artifact.

## Layout

| File | Purpose |
|---|---|
| `scripts/preview/capture_preview.sh` | Creates isolated temporary storage, starts Django locally, validates all captures and cleans up. |
| `scripts/preview/seed_preview_data.py` | Populates two disposable, localized profiles with synthetic financial data. |
| `scripts/preview/capture_preview.js` | Signs in to the temporary profiles and captures the 14 versioned screenshots. |
| `scripts/preview/serve.py` | Owns the loopback capture server and serves the committed static tour for tests. |
| `tests/preview/playwright.config.js` | Serves and validates the static English and Portuguese tours. |

The files that GitHub Pages publishes remain in `preview/`. Preview browser
assertions remain in `tests/preview/`, and `.github/workflows/pages.yml`
publishes only `preview/` after changes reach `main`.

The tour uses the application's editorial language: short factual copy, the
Paper Layers bow-tie identity, subtle ledger dividers and balanced actions.
Its six public section anchors and fourteen screenshot paths remain stable.
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
shared sidebar remains visible. Do not reintroduce the old centered crop from
the earlier top-navigation layout. All screenshots come from the checked-out
application, including unreleased changes. Local regeneration does not publish
the tour or change the application version.

Both root READMEs reuse the generated Home images, with a dark-image alternative
for dark-mode readers. Their shared native SVG cover lives in
`docs/assets/readme-cover.svg`; its bow-tie geometry follows the public homepage.
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
keyboard travel between actions and lightbox focus restoration.
