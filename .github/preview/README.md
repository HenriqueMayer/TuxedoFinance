# Interface preview maintenance

This directory contains the local automation used to maintain the static
GitHub Pages interface tour. It is development tooling and is not included in
the published Pages artifact.

## Layout

| File | Purpose |
|---|---|
| `capture_preview.sh` | Creates isolated temporary storage, starts Django locally, validates all captures and cleans up. |
| `seed_preview_data.py` | Populates two disposable, localized profiles with synthetic financial data. |
| `capture_preview.js` | Signs in to the temporary profiles and captures the 12 versioned screenshots. |
| `playwright.config.js` | Serves and validates the static English and Portuguese tours. |

The files that GitHub Pages publishes remain in `preview/`. Preview browser
assertions remain in `tests/preview/`, and `.github/workflows/pages.yml`
publishes only `preview/` after changes reach `main`.

The tour preserves its section layout and light palette. Its dark theme matches
the application's `night` tokens in `tailwind.config.js`: background `#101010`,
surface `#1B1B1B`, raised/hover surface `#262626`, and muted text `#B8B8B8`.
Caramel actions and the financial colors in application screenshots retain
their meanings. Keep both language editions and their captions in sync with the
current dashboard and transaction navigation when refreshing captures.

## Commands

For local browsing, open `preview/index.html` or `preview/pt-br/index.html`
directly. Language links include `index.html` so they also work with `file://`
and JavaScript disabled. If an embedded browser blocks local files, serve the
tour from the repository root with:

```bash
python3 -m http.server 4173 --bind 127.0.0.1 --directory preview
```

Then visit <http://127.0.0.1:4173/pt-br/> for Portuguese.

Install the [development prerequisites](../../CONTRIBUTING.md#prerequisites),
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
