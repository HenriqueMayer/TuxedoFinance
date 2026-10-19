# Assistant overlay and compact context — 2026-10-18

This record covers the assistant interface refinement on
`feat/tuxedo-assistant-foundation`, based on `ccf7602`. It follows the
[foundation review](assistant-foundation-2026-10-18.md); that earlier report
retains its original scope. Current behavior belongs to the
[assistant guide](../apps/assistant.md),
[navigation contract](../frontend/navigation.md#assistant-panel) and
[interface map](../interface-map.md#assistant-utility).

## Changes

- The desktop assistant is a fixed overlay. Opening, closing or navigating with
  it open does not reserve workspace width or redistribute financial filters.
  The phone presentation remains an opaque modal sheet with focus containment,
  accessible closing and focus return.
- Context shows the current workspace/period and its authorized origin link.
  The financial inventory, technical timestamps and repeated metrics were
  removed from the interface. Structured context, ownership checks, canonical
  values and evidence warnings remain unchanged. Current page location does
  not limit the scope of future authorized financial query tools.
- Cat artwork moves by at most 1.5px vertically and 2 degrees over four seconds;
  its orbit moves by seven degrees over twelve seconds, with two opposite stars.
  Controls and focus targets stay fixed. Reduced-motion preference disables
  the animation in both the application and Design Lab.
- Short-phone inspection found that long history titles could compress their
  flex rows and overlap dates. Rows now retain their content height inside the
  independently scrolling history list.
- Independent review found that following Context to the form already open
  could reload and reset that form. It now closes the panel without a GET;
  draft regressions cover exact URLs, omitted navigation origins and empty
  filters in both languages, themes and desktop/phone presentations.

The disconnected-provider state and disabled production composer remain. No
financial calculation, schema, provider connection or financial write changed.

## Verification

Checks used disposable data and the npm-owned browser server. The installation
database, environment file, backups and personal running server were not used.

| Check | Observed result |
|---|---|
| Assistant Django suite | 36 passed, including owner isolation, CSRF, private history, context precision, unavailable provider and compact-context rendering. |
| Django system check and migration drift | Passed; no model/migration changes detected. |
| Application assistant browser scenarios | All 22 passed again after protecting current-context links from form reloads, including four new desktop filter-geometry cases and an artwork-motion/reduced-motion case. |
| Design Lab assistant scenarios | All six passed after correcting a test selector to the actual daily-flow specimen. |
| Final history/layout rerun | All eight passed: both 320px phone themes with title/date containment assertions and all six Lab cases after the history fix. |
| JavaScript unit suite | All 16 passed. |
| Generated assets and static checks | CSS rebuilt; Portuguese catalog regenerated and compiled with format checking; JavaScript syntax, Ruff F checks, documentation links and diff whitespace passed. |

Application browser coverage included English/Brazilian Portuguese, light/dark,
desktop widths 1280/1920px, phone widths 390/320px, keyboard, touch, native
fallback, financial drafts, HTMX and private history. Desktop assertions compare
workspace and individual filter bounds before opening, while open and after
closing. Motion tests seek animation frames directly and verify stationary
targets rather than relying on timed sleeps.

Rendered desktop, phone and short-phone screenshots were inspected in both
themes. The Lab was also inspected at desktop and phone sizes. Raw synthetic
screenshots and logs remain ignored under:

- `.local/test-results/assistant-overlay-2026-10-18/`
- `.local/test-results/assistant-overlay-browser/`
- `.local/test-results/assistant-overlay-lab-browser/`
- `.local/test-results/assistant-overlay-final-browser/`
- `.local/test-results/assistant-overlay-drafts-browser/`

Relevant commands were the isolated `manage.py test assistant`, `manage.py check`
and `manage.py makemigrations --check --dry-run`, plus `npm run test:unit`,
targeted `npm run test:e2e -- tests/e2e/assistant
tests/e2e/catalogue/assistant.spec.js`, `npm run build:css`, translation tools,
`uv run python scripts/check_docs.py` and `git diff --check`.

The initial combined browser run had four Lab failures caused by a selector
pointing to a different specimen; the application cases passed. Correcting the
selector resolved all four, and the final Lab rerun passed. No known failure
from these runs remains unresolved.

The final documentation check resolved all 606 local references across 66
documents. A fresh CSS build and Portuguese catalog compilation matched the
committed generated files; Lab asset fingerprints also matched their sources.

After the requested timing refinement, cat/orbit cycles changed from 8/18 to
6/14 seconds, retaining the same amplitudes and easing. CSS was rebuilt and
three focused application/Lab browser scenarios passed, checking real animation
timings, stationary targets, desktop/touch behavior and reduced motion. These
follow-up artifacts are under `.local/test-results/assistant-motion-faster-browser/`;
the broader counts above precede this timing-only refinement.

A subsequent owner adjustment set production timing to 3/9 seconds. Following
the request to reduce each by one second, that iteration used application/Lab
2/8-second cycles and a second identical star rotated 180 degrees about the
orbit center. Three focused browser scenarios passed, including rendered
opposite-star positions, updated durations and reduced motion. Desktop light
and phone dark screenshots were inspected. Artifacts remain under
`.local/test-results/assistant-opposite-stars-browser/`.

On 2026-10-19, the cat was reduced from 36px to 28px through a 32px iteration in
application and Lab marks, retaining the 48px orbit, 60px launcher, stars and
animation timing.
CSS was rebuilt; the same three focused browser scenarios passed, with
desktop light and phone dark screenshots inspected. Evidence remains under
`.local/test-results/assistant-smaller-mark-browser/`. The final 28px adjustment
passed two focused application/Lab browser scenarios, with desktop light and
phone dark screenshots inspected under `.local/test-results/assistant-mark-28-browser/`.

After the owner clarified that the requested reduction concerned speed, the
28px size was retained and cycles slowed from 2/8 to 4/12 seconds. Two focused
application/Lab browser scenarios passed, verifying animation timings, stationary
targets, opposite stars and reduced motion. CSS was rebuilt and Lab fingerprints
verified. Evidence remains under `.local/test-results/assistant-slower-motion-browser/`.

## Limits

The full Django, whole browser, preview and Docker suites were not repeated for
this presentation-only change. Coverage percentage was not recomputed. Earlier
foundation totals are historical evidence, not results of this revision.

No installation migrations, live model requests, bank connections, service
purchases, release or publication were performed.
