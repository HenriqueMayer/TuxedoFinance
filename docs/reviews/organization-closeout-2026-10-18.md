# Organization closeout — 2026-10-18

This follow-up closes the two concrete CI/documentation findings from the final
review of the four organization lots. It starts from `f2be654`; the earlier
[frontend delivery](frontend-organization-2026-10-18.md),
[Python delivery](python-organization-2026-10-18.md) and
[tooling/browser delivery](repository-organization-2026-10-18.md) retain their
original validation scope.

## Corrections

CI now installs the pinned npm dependencies before running Python repository
tooling tests. The real Playwright configuration test depends on Node and
`node_modules/@playwright/test`; the previous order skipped that check in a clean
checkout. No check, dependency lock, audit or application job was removed.
The configuration test was also executed directly locally and passed without
being skipped. A local verification does not establish that remote CI ran.

The [Forms contract](../frontend/forms.md#keyboard-and-choice-contract) now
distinguishes ordinary single-record cancellation from the
[persistent payment board](../frontend/forms.md#persistent-payment-choices).
Ordinary pickers discard unconfirmed search on blur/Tab/Escape. Payment boards
retain the query and visible results on blur/Tab; Escape clears the query/cursor
and preserves the committed record. The guide also distinguishes the committed
`aria-selected` state from the keyboard cursor and retains native multiple-card
checkbox behavior. Presentation owns artwork and links to Forms for behavior.
The existing JavaScript and rendered interface are unchanged.

## Validation method

The complete application browser inventory runs through `npm run test:e2e` in
three disjoint Playwright shards, each with one worker, a separate disposable
database and an owned loopback server. Each shard has its own JSON report and
artifact directory under `.local/test-results/ci-form-contract/`. Combining the
reports must account for every unique test exactly once, including the existing
paused-import skips. The static tour uses its separate `npm run test:preview`
entry point.

Python/tooling checks use the documented temporary installation environment or
standard-library fixtures; none points at the installation database. Existing
runtime sources and test declarations were recorded before execution, and
installation paths were recorded through metadata without reading personal
financial records.

## Results

The full inventory contains **475 unique application browser cases**. The three
initial reports reconcile exactly with that inventory, with no omissions or
duplicates:

| Initial application run | Passed | Existing skips | Failed | Duration |
|---|---:|---:|---:|---:|
| Shard 1 | 155 | 4 | 1 | 20.2 min |
| Shard 2 | 168 | 2 | 1 | 17.4 min |
| Shard 3 | 144 | 0 | 0 | 12.1 min |
| Total | 467 | 6 | 2 | Concurrent shards |

The six skips remain the four paused statement-interface cases and the two
paused planning-import cases. No skip was added. Shard 2 produced its complete
JSON report but its runner returned 143; the origin of that signal was not
established. Its recorded browser failure is included above.

The two failures were `report month arrows stay independent (light)`
(`dashboard/report-month-filters.spec.js`) and
`monetary yield previews a final balance and stores only the calculated yield`
(`shared/design-system.spec.js`). The first timed out while a composition panel
still showed Loading composition; both reported a browser-context teardown
timeout. Their original screenshots, traces and reports remain in the ignored
artifact directory.

Trace inspection showed that the report's third composition request remained
pending beyond the five-second assertion window; the server subsequently
recorded HTTP 200. The preceding composition responses were correct. In the
yield case, all functional assertions and the empty-page-error check completed;
only closing the browser context timed out. Neither trace establishes the cause
of the delay or a relationship with the runner's signal exit.
The report trace also contains a wall-clock discontinuity of about 23 minutes
while its monotonic timestamp advances about two seconds; its causal connection
to the later request timeout was not established.

Both cases passed **three isolated repetitions each: 6/6 in 57.4 seconds**.
Both affected files then passed **27/27 in 1.6 minutes**, preserving their normal
test sequence. These checks used new disposable installations, one worker and
the original assertions/timeouts, with no application or test changes. All 469
enabled cases have a passing result across the complete run and these focused
rechecks. The initial complete run was not clean; the cause of its two timing
failures remains unconfirmed and warrants a separate repeatability investigation.

Other current checks passed:

| Check | Result |
|---|---|
| Python repository tooling | 40 passed |
| Real Playwright configuration test, explicitly selected | Passed, not skipped |
| JavaScript amount/allocation helpers | 16 passed |
| Static preview browser suite | 6 passed |
| Django system checks and missing migrations | Passed in a temporary installation |
| Python undefined-name lint | Passed |
| Project version and locked Python dependencies | Passed |
| Documentation links and anchors | 56 documents, 539 local references, none unresolved |
| Whitespace validation | `git diff --check` passed |

All 659 recorded application, runtime, asset and test-source hashes remained
unchanged. Installation paths retained their recorded identities, and the
browser runners disposed of their temporary installations. No dependency,
database, environment file or backup was moved or deleted. Raw validation
artifacts remain ignored under `.local/test-results/ci-form-contract/`.

## Boundaries

This follow-up does not change application functionality, financial rules,
models, migrations, assets, translations, dependency versions or personal data.
It does not implement the separately proposed coverage-policy or runner-log
improvements. Real Docker execution, physical phones, other browser engines and
remote CI/publication are outside this local validation. The full Django suite
was not repeated for these CI/Markdown-only changes; its prior 723-case result
remains dated evidence in the frontend delivery.
