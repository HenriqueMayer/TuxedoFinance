# Release interception regression — 2026-10-22

## Scope

This review covers the controlled assistant-deletion regression and preparation
of version 1.0.0 from `49747c0f8cbbc5b085b39dc5591d49ffbdd8ae53`.
The installation checkout, its data and configuration were preserved. Checks
used a separate source checkout and the disposable browser executor described
in [Contributing](../../CONTRIBUTING.md#browser-tests).

## Reproduction and cause

The [v0.11.0 amd64 release job](https://github.com/HenriqueMayer/TuxedoFinance/actions/runs/39699440886/job/119564804477)
failed while waiting for the deleted conversation ID to become empty. Its trace
shows a successful deletion POST returning 302 in approximately 11 ms, followed
by an unfinished GET to `/assistant/`. The test had not yet released its older
conversation GET. This failure does not show a stale response replacing the
deleted conversation.

The original controlled test reproduced the same failure in its first two
native cases: desktop/light/English and phone/dark/Portuguese. Both deletion
POSTs returned 302; their redirected index GETs remained unfinished.

Both route handlers used `times: 1`. Playwright 1.62.0 removes an expiring
handler before executing it. After the last handler completes, it disables
Chromium request interception. This can race with the redirected GET. The
[upstream investigation](https://github.com/microsoft/playwright/issues/41802)
identifies this `Fetch.disable` race and documents persistent handlers with
explicit first-request flags as a workaround.

The correction keeps interception active through the complete scenario and
releases both gates before waiting for route cleanup. It does not change
application code, dependency versions, assertions or timeouts. The same two
variants then passed 40 consecutive cases using `--repeat-each=20` in 2.7 minutes.
This controlled comparison supports the interception-lifecycle diagnosis.

## Preserved checks and focused validation

The regression still requires an empty conversation before releasing the older
GET, then checks it again after that GET completes. It also requires one browser
POST, a subsequent 404 for the deleted conversation, the original financial draft
and no departure dialog. Repeated route matches continue to the real server, so
a duplicate POST remains observable.

The full local-chat file passed all 24 cases in 1.1 minutes, including native
fallbacks, draft preservation, cancellation, session privacy and panel behavior.
An independent static review found no correctness issue or lost invariant in
the correction. This is not an independent execution of those tests.

Version consistency, documentation links, Django system checks, migration drift
and repository-tool tests passed. The frontend dependency audit reported zero
vulnerabilities. Broader release checks were still in progress when this record
was written. These focused results do not establish complete application CI or
Docker publication.

## Release boundaries

Version metadata and bilingual Docker instructions target 1.0.0. The published
0.11.0 changelog section and locked dependencies remain unchanged. The release
procedure requires application CI on the integrated commit and tag, both Docker
architectures, and the stable publication job. Image tags, manifest digests,
source labels, anonymous pulls and matching installation assets must be verified
before delivery is reported complete. See [Versioning](../versioning.md).

No live provider authorization or inference was used for this investigation.
Raw baseline and corrected traces remain in the task's recovery directory,
outside the active source checkout. The original failure's trace is also in the
[CI artifact](https://github.com/HenriqueMayer/TuxedoFinance/actions/runs/39699440886/artifacts/12394151675).
