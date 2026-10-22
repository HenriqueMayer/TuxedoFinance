# Interface preview maintenance

The bilingual product presentation in `preview/` introduces the application,
its six workspaces and the optional Tuxedo assistant. It combines the existing
forest/caramel ledger bow tie, local Inter typography and editorial copy with
responsive HTML/SVG examples. The product demonstration does not depend on
scaled screenshots. The font license is included in `preview/assets/OFL.txt`;
the assistant mark is the application's existing brand asset.

## Presentation and interaction

`preview/index.html` and `preview/pt-br/index.html` contain equivalent English
and Brazilian Portuguese content. Keep both files synchronized. They share
`assets/preview.css` and `assets/preview.js`, with no new runtime dependencies
or remote assets. The page remains usable when opened as a local HTML file.

The opening introduces the application, followed by an interactive workspace
example, guided assistant conversations, a three-step explanation and repository
and installation links. The demonstration is an illustrative presentation of
supported behavior, not a second financial application or an authenticated
session. It uses a fixed fictional October 2026 example; it never reads the
installation's data or saves financial records.

The six workspace destinations match the application: Home, Transactions,
Accounts, Investments, Plan and Analytics. New entry belongs to Transactions;
investment analysis belongs to Analytics. Native links select one of eight
illustrative views with JavaScript. Search filters only the four example
transactions, preserving the typed query and focus. Enhanced links within the
demo update the workspace and URL without moving the document: capture the
current scroll position, prevent native fragment scrolling and restore the
position after the content/focus update. Reopening the selected workspace does
not add a history entry or move the page. Back/Forward, current-page semantics
and destination focus for keyboard activation remain available. Direct workspace
links and links from outside the demo still reveal the application. Landing
sections keep the selected demo workspace.
Language links preserve known fragments; the theme follows a saved choice or
the system preference. Only that theme preference uses browser storage.

Preserve the existing workspace fragments, including `#reports` as an alias
for Analytics, `#dashboard-preview` for Home and `#top` for the introduction.
Without JavaScript, all eight workspaces and all three prepared conversations
remain readable. Enhancement-only search, chat selectors, confirmation and
theme controls stay hidden when their behavior is unavailable. Links and the
native language editions remain usable.

The assistant offers three explicitly scripted examples: expense explanation,
a spending scenario and review of a proposed category budget. The separate
**Simulate confirmation** action changes only the example's visible state.
It makes no request and persists no proposal. Switching examples resets that
state. Explain that responses are prepared and data fictional; never imply
that the public page runs inference. The application's separate optional
account and inference gates remain described in the
[assistant guide](apps/assistant.md). Financial ownership, confirmations and
calculations remain with the application services.

The fixture distinguishes monthly income/expenses, current cash, existing
reserves and dated investment values. Preserve those meanings: a category
budget does not reserve cash; a scenario does not update records; dated
investment gains are not bank income. Keep totals consistent across the
workspace and chat examples. The SVG cash chart includes its data in its
accessible label. Do not add unverified business results, live quotes,
automatic bank integration or payments to the presentation.

Repository and quick-start links open separately with `noopener noreferrer`.
The Portuguese installation action links to the Portuguese README. Embedding
sites must allow `allow-popups allow-popups-to-escape-sandbox` alongside script
and origin permissions. The public page makes no automatic external request.

## Files and publication

| File | Purpose |
|---|---|
| `preview/index.html`, `preview/pt-br/index.html` | Equivalent native product presentations and fictional examples. |
| `preview/assets/preview.css`, `preview/assets/preview.js` | Shared responsive styling and progressive interaction. |
| `tests/preview/preview.spec.js` | Presentation, keyboard, native fallback, local-only interaction and viewport regressions. |
| `tests/preview/playwright.config.js` | Owns the disposable static-test server. |
| `scripts/preview/serve.py` | Loopback static server and guarded capture server. |
| `scripts/preview/capture_preview.sh` | Creates isolated storage, captures the real application and cleans up. |
| `scripts/preview/seed_preview_data.py` | Creates disposable localized profiles with synthetic financial data. |
| `scripts/preview/capture_preview.js` | Captures eight real application views in two themes/languages. |

`.github/workflows/pages.yml` publishes only `preview/` after authorized changes
reach `main`. Editing or locally serving the presentation does not publish it.
Both READMEs retain their prominent preview links and established cover artwork.

Existing `preview/images/` files and their URLs remain available as separate
real-application evidence and compatible external references. They do not drive
the new interactive examples. Screenshot capture tooling retains its own
isolation guards and is not part of the published runtime. Never use personal
records, credentials, local conversations or an authenticated financial session
as public preview content.

## Commands and verification

Open either `index.html` directly, or serve only the public directory:

```bash
python3 -m http.server 4173 --bind 127.0.0.1 --directory preview
```

Visit <http://127.0.0.1:4173/pt-br/> for Portuguese. After installing the
[development prerequisites](../CONTRIBUTING.md#prerequisites), run:

```bash
npm run test:preview
uv run python scripts/check_docs.py
git diff --check
```

The static suite owns an available loopback port, refuses an existing server
and checks an execution-specific readiness endpoint. It never opens an
application database. Artifacts stay in `.local/test-results/preview/`; the CI
report stays in `.local/playwright-report/preview/`. Inspect desktop and phone
renders in both themes/languages, every workspace, search/no-result recovery,
keyboard navigation, history, chat scenarios and confirmation. Verify native
file access without JavaScript. Screenshot creation alone is not visual review.

Real application screenshot regeneration remains a separate explicit command:

```bash
npm run preview:capture
```

Keep `ASSISTANT_OPENAI_AUTH_ENABLED` and
`ASSISTANT_OPENAI_INFERENCE_ENABLED` off. The capture wrapper refuses workspace
seeding, uses ephemeral credentials, stages every image before replacement and
removes its temporary database on failure or success. Its loopback endpoint is
published only after the owned socket is bound. Never weaken these guards.
Local capture does not authorize publication or change the application version.
