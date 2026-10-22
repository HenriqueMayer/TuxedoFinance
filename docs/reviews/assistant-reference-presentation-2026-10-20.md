# Assistant reference presentation — 2026-10-20

## Scope and cause

The owner reported internal paths repeated at the end of an otherwise completed
reply. A read-only inspection of that message's ending and verified references
confirmed a final Markdown-link paragraph duplicating the application's source
footer. The safe renderer deliberately kept model links inert by showing their
labels and URLs as text. Instructions v5 requested those same URLs, producing
the visible duplication. No private transcript or financial figures are copied
into this report.

## Correction

- Enhanced rendering omits only a final paragraph composed exclusively of
  Markdown links and separators when every destination and label match that
  message's authorized source footer. The exact ISO month from a single
  authorized month parameter may suffix its label. Inline explanations, code,
  quotations, images, explanatory link labels, unknown destinations and
  differently filtered URLs remain visible.
- Completed streaming replies are rendered again after server references arrive.
  Reopened history uses the same rule. The footer remains the only active source
  navigation; model text cannot create an anchor or network resource.
- Raw stored messages and Markdown copy/download remain intact. The native
  no-JavaScript response retains escaped text and authorized footer links.
- Instructions v6 align attribution with the automatic footer, retaining source
  labels in useful prose and explicit evidence limitations. Versions v1–v5
  remain loadable; financial calculations, tool permissions and confirmation
  rules are unchanged.

Current contracts: [assistant presentation](../apps/assistant.md),
[navigation](../frontend/navigation.md) and
[financial premises](../assistant/financial-premises.md).

## Validation

All automated fixtures use disposable data and synthetic providers. No model,
catalogue, OAuth or banking request was made for this presentation correction.

| Check | Result |
|---|---|
| Assistant backend | All 365 tests passed after the v6 change, with isolated Django checks and no migration drift. Financial and action code remained unchanged. |
| JavaScript units | All 26 passed on the final renderer, including exact destination/label matching, the authorized month suffix, meaningful warning labels, unknown sources, quotes/code and malformed destinations. |
| Browser | All 19 passed in the final isolated run: 10 Markdown/progress/reference cases and 9 copy/export cases. Desktop 1440px and phone 390px, light/dark themes and English/PT-BR were covered. |
| Reference lifecycle | The five new browser cases cover done-before-refresh with GET held, authorized keyboard navigation, reload/HTMX/Back, unchanged raw Markdown export and native escaped-text fallback. |
| Review and static checks | An initial URL-only match could hide warnings inside link labels; the final URL-and-label check preserves them. Read-only review, Ruff F, JavaScript syntax and `git diff --check` passed. Documentation checker: 86 documents, 733 local references, zero unresolved. |

Final screenshots were inspected on desktop and phone in both themes, including
keyboard focus on source links. Native fallback was also inspected. Copy tests
mock clipboard writes so validation does not change the workstation clipboard;
authorization, GET/HEAD, downloads and history use the real isolated app.

Raw synthetic evidence is under ignored
`.local/reviews/assistant-references-2026-10-20/`: `django.log`, initial `browser/`
and final `browser-final/` screenshots. No production data is included.

## Preservation and limits

The installation database was read-only during diagnosis. No saved message,
financial row, environment file or credential vault was edited. No new schema,
dependency, paid API, live inference, commit or publication was introduced.
No financial formula, amount, cutoff or source destination was changed.

The renderer is still a bounded Markdown subset, not a general sanitizer or
permission system. Duplicate suppression needs the existing authorized footer;
it never trusts a model-generated link as evidence. The instruction tests check
versioning and content, not a live model's compliance.
