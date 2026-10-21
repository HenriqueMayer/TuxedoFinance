# Shared compact workspace density — 2026-10-21

## Scope

Use the compact Home/Accounts presentation consistently across Home,
Transactions, Accounts, Investments, Plan and Analytics, including investment
analysis. Preserve the existing financial data, calculations, local ownership
and navigation. Current rules belong to the
[compact workspace contract](../frontend/catalogue.md#compact-workspace-density),
[interface map](../interface-map.md) and [style index](../../assets/README.md).

## Delivered presentation

The authenticated main element opts into a single shared scale. Page titles
are 24px with 30px lines, section headings 18px with 24px lines, and overview
groups have 16px spacing. Opening summaries and metric panels have 16px padding.
Primary summary amounts use 24px type, their currency prefix uses regular 14px
type, labels use 14px and dated evidence uses 12px. Existing compact overrides
that competed with that scale were removed. Public/authentication compositions
retain their own rules; authenticated editor headings share the title scale.

Home and Accounts now use exactly the same availability presentation.
Investments retains its dated value, warnings and disclosure. Planning groups
the month with its label and places secondary values side by side on desktop.
Its calculation disclosure remains native. Analytics retains distinct financial
and investment destinations; no total or new metric was invented for a page
without an opening monetary summary.

Panels remain content-sized. Missing-rate/history notices, long labels and
expanded explanations retain space. Field geometry, complete-form padding,
chart canvases, financial expressions, input names, stable IDs, HTMX/OOB hooks
and native submissions were retained. No model, migration or financial service
was changed in this batch.

The Design Lab demonstrates the shared roles. All 32 public preview captures
were regenerated with disposable synthetic profiles. The Home thumbnail crop
was corrected from y=230 to y=150 because the compact balance panel starts at
157; a regression check keeps its label and complete amount inside the crop.
The complete images and lightbox remain uncropped. The entry crop remains y=220.

## Validation

- 61 isolated Django tests passed, covering account/workspace presentation,
  language responses, monthly planning, analytical routes and monthly financial
  performance. The automatic Django check found no issues.
- 36 focused browser cases passed across the shared compact specification,
  banking editorial controls, Home, Analytics navigation/legacy destinations,
  investment registration/updates and planning summaries/goals. They include
  native fallback, real keyboard input, invalid forms and contextual navigation.
- After making the currency prefix consistent, all nine shared compact cases
  passed again: EN/PT-BR in both themes at desktop and 320px, native phone
  navigation and four Design Lab configurations. Synthetic BRL 1,200.50 remains
  the same in Home, Accounts and Plan; the investment position remains BRL
  300.25 and its reservation remains BRL 100.00. Disclosures grow naturally.
- Desktop and phone screenshots were visually inspected in both themes.
  The inspected states include all six destinations, the common opening
  summaries, date/period controls, native disclosures and the cropped public
  Home preview. Long labels and translated controls remain readable.
- All 21 static-preview cases passed after the final captures and crop update,
  including source-panel visibility, native navigation and keyboard/lightbox
  recovery.
- 26 dependency-free JavaScript tests passed. CSS was rebuilt and compared
  byte-for-byte. Changed test syntax, documentation links and diff checks passed.

## Boundaries and evidence

This is scoped layout verification, not a fresh full-application Django/browser
suite, financial certification or publication approval. Test and capture
runtimes used disposable databases and loopback servers with real providers
disabled. The existing installation was not imported, migrated or connected.
No commit, push, release or publication was performed.

The pre-task working files, current screenshots and logs remain under
`.local/workspace-density-2026-10-21/`. Earlier unrelated changes are preserved.
