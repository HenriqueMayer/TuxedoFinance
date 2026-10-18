# Full browser validation and v1 readiness — 2026-10-18

This review targets `bc58cb73983dfc47ce584d13d6ad48b47967232f` on
`feat/personal-finance-evolution`. It executes the complete browser inventory
and checks remaining release work. It does not change application behavior,
financial records, the application version or release state.

## Method and scope

`npm run test:e2e -- --list --reporter=json` recorded **482 application cases**
in 79 spec files, including six existing skips for paused features. Three
disjoint `--shard=N/3` executions use the unchanged Playwright configuration,
one worker per shard and separate disposable databases, loopback servers,
JSON reports, logs and artifact directories. No assertion, timeout, retry or
skip is changed during this review. The separate `npm run test:preview`
executes the complete static-tour inventory.

The authoritative initial inventory and report reconciliation are retained
under ignored `.local/test-results/v1-readiness-bc58cb7-yqnp2stk/`. Every
application identity must occur exactly once across the three initial reports;
later focused repeats are reported separately. A baseline records hashes of
all 768 tracked files and metadata for the installation's `.env` and database,
without reading their contents. Test executors never use those installation
paths or the developer's server.

Browser coverage uses Chromium with desktop/phone viewport, theme, language,
keyboard, touch and native-fallback scenarios declared by each test. It does
not establish Firefox, WebKit or physical-device compatibility. The
[previous recurrence review](recurrence-public-readiness-2026-10-18.md)
retains its narrower validation scope; this execution is separate evidence.

## Complete browser results

The complete initial application run finished with **475 passed, one failed
and six existing skips**. All 482 inventory identities occur exactly once in
the three reports, with no missing, extra or duplicate cases, automatic
retries or reporter-level errors. The six skips exactly match the initial
inventory. The complete static preview suite passed **17/17**.

| Execution | Passed | Failed | Existing skips | Duration |
|---|---:|---:|---:|---:|
| Application shard 1/3 | 160 | 1 | 4 | 17m 04s |
| Application shard 2/3 | 164 | 0 | 2 | 14m 26s |
| Application shard 3/3 | 151 | 0 | 0 | 11m 35s |
| Static preview | 17 | 0 | 0 | 43s |
| Separate unchanged Accounts recheck, repeated three times | 3 | 0 | 0 | 33s |

The initial application suite therefore returned a failure; separate focused
repeats must not replace that result. Its only failed case is the light/1280
Accounts workspace test described below.

The deliberately skipped cases belong to paused statement operations:

- `ingestion/ingestion.spec.js`: statement review keyboard transitions,
  validation and undo in light and dark themes; native CSV mapping/full
  review submission; touch help. Four cases, all existing feature gates.
- `planning/planning-import-workspaces.spec.js`: compact paginated import,
  strong-ID bulk skip and mapping reuse in light and dark themes. Two cases,
  both existing feature gates.

Individual identities, results and errors are retained in `reconciliation.json`
beside the original inventory, three JSON reports, server logs and failure
artifacts. The suite includes the declared desktop and phone scenarios;
individual tests do not necessarily cover every viewport/theme combination.

## Financial calendar: correct before v1

The application has conflicting definitions of the financial day. Django is
configured for UTC and settlement/reporting uses `timezone.localdate()`.
Invoice properties and confirmed-payment validation use the host's
`date.today()`. The affected rules are in
[Banking models](../../banking/models.py),
[settlement refresh](../../banking/settlements.py) and
[cash calculations](../../banking/services.py), with the calendar configured in
[settings](../../core/settings.py).

A disposable proof fixes one instant: **2026-10-19 00:30 UTC**, which is
**2026-10-18 21:30 in São Paulo**. On a UTC host, a validated BRL 100 credit
purchase creates its ordinary manual invoice. `save_invoice_payment` validates
and saves its full October 19 payment, including the real debit movement.
Reopening the same valid records under a São Paulo host clock at the identical
instant gives these results through ordinary synchronization and authenticated
invoice GETs (plus Home and Reports GETs in the São Paulo phase):

| Observation | UTC host | São Paulo host |
|---|---:|---:|
| Stored invoice status | Paid | Paid |
| Invoice summary: confirmed payment | BRL 100 | BRL 0 |
| Invoice summary: remaining | BRL 0 | BRL 100 |
| Bank balance | BRL 900 | BRL 900 |
| Validation of the same existing payment | Accepted | Rejected as a future date |

The São Paulo invoice HTML simultaneously displays Paid, zero confirmed and
BRL 100 remaining, while its history retains the saved payment. Home and
Reports GETs in that phase also return BRL 900. The
[invoice view](../../banking/views/invoices.py) synchronizes before rendering
the conflicting [summary fields](../../templates/banking/invoice_detail.html).
No invalid direct-ORM payment is needed for this reproduction. Both phases
patch only the Django instant and Banking's host-date clock; all financial
services, validation, middleware and templates remain unchanged. This models
opening UTC-created data on a native São Paulo installation, not changing a
browser timezone.

Before v1, select one financial-calendar policy, apply it consistently to
properties, validation, synchronization and presentation, and add evening/day
boundary regressions. This does not require rewriting stored payment dates or
introducing per-user timezone infrastructure. The desired policy is distinct
from the proven inconsistency. Exact evidence and the isolated script are
`time-boundary-supported-workflow.json` and
`time-boundary-supported-workflow.py` in this run's ignored evidence directory.
The temporary installation was disposed of.

## Browser geometry: stabilize the regression before v1

The initial light/1280 Accounts workspace case measured Minimize at
**43.99998474121094 px**, failing its strict `height >= 44` assertion in
[the workspace regression](../../tests/e2e/banking/banking-inline-workspace.spec.js).
The delivered [Banking CSS](../../assets/css/banking-consultation.css) specifies
`min-height: 44px`; its parent panel animates a vertical translation for 180ms,
without scale. The trace places the bounding-box measurement about 89ms after
the panel first appears. The observed difference is exactly 1/65536 px.

This supports transformed-coordinate rounding as the cause; it does not
establish an undersized CSS target. The original trace does not record raw
computed style and border-quad endpoints, so that causal detail remains an
inference.

After all initial shards completed, the exact failed case was repeated three
times with the unchanged test, configuration and assertions. All three passed
in 33 seconds, without retries, including the later edit, minimize, keyboard
and history assertions. This demonstrates intermittent behavior rather than
reproducing a consistently undersized control; it does not by itself prove
the rendering cause. Prefer a settled geometry measurement while preserving
the approved 44px target. Do not enlarge the application control just to
satisfy numerical noise, skip the test or silently turn the initial failure
into a pass.

Evidence is `geometry-repeat-3-corrected.json` and its matching logs/artifacts.
An earlier focused command matched zero tests and exited before execution;
that selection error is retained separately in `geometry-repeat-3.*` and is
not counted as a test result. Only its CLI selection was corrected.

## Upgrade and container evidence: required for the v1 candidate

The [Docker workflow](../../.github/workflows/docker.yml) rehearses upgrades
from v0.3.0, v0.4.0, v0.9.0 and v0.9.1. Current stable v0.10.0 needs to be added
when preparing v1. There are subsequent Banking, Transactions, Investments,
Planning and Ingestion migrations; fresh-install browser tests do not prove
preservation of older installation data.

Run `v0.10.0 → candidate` on disposable data with financial snapshots,
recreation, backup, restore and recovery using the previous image plus its
pre-upgrade backup. The existing
[smoke runner](../../scripts/docker_smoke.py) supports this. Candidate images
must pass native amd64 and arm64 validation before publication. The current
host runs Docker Engine **26.1.5**, below the documented **28+** baseline;
container writes/builds were not run on this unsupported host.

Read-only GitHub verification confirms that
[v0.10.0](https://github.com/HenriqueMayer/TuxedoFinance/releases/tag/v0.10.0)
is published with its installation assets and its
[Docker release workflow](https://github.com/HenriqueMayer/TuxedoFinance/actions/runs/37887042555)
passed both architectures and publication. That evidence targets `8a25ae4c`,
not this candidate. No workflow run was returned for candidate `bc58cb7`.
Current-candidate CI/container evidence is therefore pending, not a failed
remote run. No push, pull request or workflow dispatch was performed.

## Release preparation and scope

Version metadata remains consistently **0.10.0**, with this branch's work under
Unreleased. A future v1 preparation must update the canonical version, lockfile,
README badges, dated changelog and installation references under the
[release workflow](../versioning.md). Do not reuse the v0.10.0 release identity
for these changes. Owner acceptance remains unchecked in the
[requirements](../product-requirements.md#12-acceptance-criteria); final
acceptance and publication are separate from this test execution.

Paused statement operations and the net-worth interface are deliberate scope
decisions, not missing v1 requirements. Bank connections, external feeds,
cloud hosting, internal investment adjustments and further analytics should
not be added to the release gate without a separate product decision.

## Other checks and preservation

The following additional checks passed during this review:

- Locked dependency consistency and canonical version consistency: 0.10.0.
- Django system checks and `makemigrations --check --dry-run`, against an
  isolated temporary data directory: no issues or pending model migrations.
- The configured executable-correctness Ruff rules and all **16 JavaScript
  unit tests**.
- Rebuilt CSS and compiled Brazilian Portuguese translations compare byte for
  byte with the committed assets; vendored HTMX matches its pinned checksum.
- npm audit: zero reported advisories. Strict Python runtime audit: six
  dependencies checked, zero reported advisories and zero skipped packages.
  These are dependency-database results, not proof of absence of every
  vulnerability.
- Documentation references and `git diff --check`.

The full Django suite was not rerun in this browser-focused review. The
earlier **745 Django tests** and configured coverage result belong to the
[recurrence delivery](recurrence-public-readiness-2026-10-18.md), not this run.

Source hashing confirms that tracked application code, tests, assets,
dependency manifests and release metadata retain their baseline contents. Of
the 768 tracked files, only the review index changed; this review is a new
documentation file. HEAD
remains `bc58cb7`, and no new commit was made. The installation's `.env` and
`db.sqlite3` retain their device/inode, size and modification timestamp; their
contents were not opened. The three initial test servers stopped, all three
owned ports refused connections and their temporary databases were removed.
Both focused-run servers also stopped and disposed of their temporary data;
the runtime directory contains no remaining test installations.
Evidence remains under the ignored run directory. No installation data,
backups or user server was modified, and nothing was published.
