# Financial calendar correction and Accounts test stability — 2026-10-18

This delivery follows the [pre-fix v1 review](v1-readiness-2026-10-18.md),
which measured `bc58cb7`. It corrects its financial-calendar inconsistency and
intermittent Accounts geometry assertion. It does not change the application
timezone, schema, stored dates, settlement modes, visual design or release
version. Upgrade/container validation and final v1 acceptance remain separate.

## Financial behavior

`CardInvoice.is_overdue`, confirmed totals and `InvoicePayment.clean` now use
the same `timezone.localdate()` as synchronization and default balance/report
reads. The demo payment guard uses it too, preventing a simulated host date
from admitting a confirmation that the application considers future-dated.
The configured calendar remains UTC; the implementation also honors an
explicit Django timezone override consistently. It introduces no per-user
timezone setting or new date abstraction.

Confirmed totals capture one cutoff per property evaluation and work with
ordinary and prefetched payment relations. Explicit `as_of`/`through_date`
arguments remain unchanged. Payments and linked movements keep their actual
calendar dates, amounts and identities. Existing affected payment fixtures use
the application date rather than the host date.

The owning contracts are [Operations](../operations.md#financial-calendar)
and [Banking](../apps/banking.md#optional-manual-settlement). No migration,
redating, balance adjustment or installation synchronization is required by
this code correction.

## Accounts regression

The Accounts browser test waits through runner-side `expect.poll` until the
entry panel has no active animation, then measures its target. The original
strict width and height requirements of at least 44px remain intact. No fixed
sleep, custom timeout, numerical tolerance, new skip, automatic retry or CSS
enlargement was added. The application's approved entry animation is unchanged.

The four theme/viewport variants passed three repetitions each: **12/12**,
without retries, in 128 seconds. Separate full inline-workspace and account-task
flows cover the surrounding native history, keyboard, payment errors and
contextual actions: **14/14 passed**, in 89 seconds. Together these are 26
executions of 14 unique cases, with no failures, skips, automatic retries,
flaky results or reporter errors. The repeated cases are not additional unique
coverage. Captured Minimize bars were inspected at 1280px and 390px in both
themes; their design and visible keyboard focus remain intact.

## Boundary regressions

Seven Banking tests fix the instant at October 19, 2026, 00:30 UTC and provide
a disagreeing host-date decoy. They cover the inclusive due day, accepting the
application's current date, rejecting its future date, live/prefetched payment
totals, partial/paid/overpaid amounts and explicit historical balance and
invoice cutoffs. Active São Paulo overrides and the default UTC calendar are
both exercised. The full-payment case uses ordinary services and authenticated
invoice, Home and Reports GETs: Paid, BRL 100 confirmed, zero remaining and BRL
900 cash agree. Existing payment validation still succeeds and stored payment
and movement snapshots remain unchanged.

All seven tests passed. In a separate disposable process, substituting only the
three old model methods from `bc58cb7` made every regression reject the old
behavior, including Paid with zero confirmed. The real demo seeder has its own
boundary regression: it creates the demo successfully without confirming the
next-day payment. Its nine-test module passed; replacing only its old guard in
another disposable process produced the expected future-payment validation
error. These counterfactuals do not modify shared files or the installation.

## Final validation

- Complete Django suite: **753 passed**, in 134.479 seconds. Branch-aware
  coverage met the configured floor at **95%**; this repository configuration
  includes test and migration modules and is not a runtime-only percentage.
- Repository-tool suite: **40 passed**.
- Affected existing payment/context modules: **23 passed**. The seven Banking
  boundary cases and nine demo-module tests also passed in focused runs before
  inclusion in the complete Django suite.
- Browser validation: **14 unique cases passed**, plus 12 repeated executions
  of the four Accounts geometry variants, as detailed above.
- Django system checks, absence of pending model migrations, locked dependency
  and version consistency, configured Ruff rules, documentation references and
  whitespace checks passed.

One earlier full Django attempt ended with SIGTERM (exit 143) before its final
summary. It is retained as `full-interrupted.log` and excluded from successful
suite counts. Its 40-tool-test predecessor had completed successfully. The
complete follow-up run and coverage report both exited zero, recorded in
`full-completed.log` and `full-completed.json`. The interrupted owned temporary
directory was removed; the follow-up runner also cleaned up its temporary data.

## Isolation and evidence

All browser executions use `npm run test:e2e`, with their own loopback server,
temporary database and signing key. Django and tooling executions use isolated
temporary settings. Raw logs, JSON reports, counterfactual runners, screenshots
and traces remain under ignored
`.local/test-results/financial-calendar-fix-zjeykpkt/`.

The installation's `.env` and `db.sqlite3` retain their original device/inode,
size and modification timestamp; their contents were not read. Settings,
dependency manifests, compiled stylesheet and translations compare byte for
byte with the starting hashes. Both browser servers stopped, their ports
refused connections and no owned temporary Python/browser installations remain.
No installation database, backup or user server was used for validation.

The earlier complete browser result remains historical evidence: 475 passed,
six paused-feature skips and one geometry failure, followed by three unchanged
focused passes. This delivery reports its new scoped browser runs separately;
it does not relabel the earlier failing execution as successful. Chromium's
declared desktop/phone emulation does not certify other engines or physical
devices. No publication, push, tag or release is part of this delivery.
