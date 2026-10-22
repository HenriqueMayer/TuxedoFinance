# Assistant authorization preparation — 2026-10-19

## Scope

First connection delivery on `feat/tuxedo-assistant-foundation`, following
`4cb6aef`. This is local authorization preparation, not a connected AI release.
No real account, credentials, model request, financial export or publication
was used for validation. Installation databases, environment files and backups
were not migrated or modified.

The current contract lives in the [assistant guide](../apps/assistant.md#openai-authorization-preparation),
[navigation guide](../frontend/navigation.md#assistant-panel) and
[operations guide](../operations.md#assistant-data-and-integrations).

## Changes and acceptance

| Problem | Decision and resulting behavior | Verification |
|---|---|---|
| Connection preparation had no owner-facing workflow. | Add account settings, native authorization/confirmation/cancel/selection/disconnect POSTs and a separate callback result. Keep real authorization off by default and inference disconnected. | Rendered views, CSRF/ownership/session tests and browser settings access. |
| A loopback callback may not share the original `localhost` login cookie. | Open authorization in a separate tab. The callback stages verified credentials; only the original authenticated session can confirm the account. | Anonymous callback, forged-session, different-session and replay tests; native form targets checked. |
| Tokens must not enter SQLite, HTML, browser storage or logs. | Store PKCE and tokens in an independently encrypted private vault; retain only account metadata and attempt digests in SQLite. Redact Django callback logs and omit queries from Gunicorn access logs. | Ciphertext/permissions/key-recovery tests, DEBUG error recovery and a synthetic callback inspected in container logs. |
| Refresh rotation, interrupted writes and account changes can corrupt a connection. | Serialize connection refresh outside SQLite transactions, atomically replace credentials, retain recoverable staged handoffs and clear unusable credentials. Distinguish same-email registrations by issued client ID. | Concurrent refresh, database-failure, restored-identity, orphan cleanup, cancellation and disconnection regressions. |
| Test runners could inherit live assistant configuration. | Discard inherited assistant settings, force authorization off and keep private storage inside disposable installations. | Poisoned-environment tooling tests and preserved synthetic personal-vault sentinel. |

The additive `assistant.0002` migration creates authorization metadata tables.
An isolated migration check retained the hashes and row counts of 42 existing
synthetic tables (218 rows), added two empty tables and created no vault.
Apply the incremental migration before opening account settings in an existing
installation. This check does not establish a released-image upgrade rehearsal.

## Validation

- All 874 Django tests passed on the final locked dependencies; measured total
  branch coverage was 95%, above the existing 70% CI floor.
- All 42 Python tooling tests and 16 JavaScript unit tests passed.
- All 33 scoped Chromium assistant/Design Lab tests passed. The five connection
  tests were repeated after the final accessible-link change and passed,
  including declined/confirmed departure from an edited financial form.
- Inspected rendered settings at 1440px and 390px in light/dark themes, keyboard
  navigation, final content above mobile navigation, and Portuguese without
  JavaScript. Existing assistant tests cover EN/PT, history/logout, HTMX,
  touch, reduced motion and financial draft continuity.
- Django checks, migration consistency, version consistency, focused Ruff,
  documentation references, `git diff --check`, CSS build and gettext
  recompilation passed. The application version remains `0.10.0`.
- The locked runtime audit initially identified `PYSEC-2026-3552` in the newly
  introduced cryptography 49.0.0. Updated to 50.0.2; the final Python and npm
  audits reported no known vulnerabilities. PyJWT is pinned to 2.15.1.
- Built local image `tuxedo-finance:oauth-lot1-validation-20261019-final`
  (`7b73aa38e9f4`). Disposable fresh/recreated/restored installations passed
  lifecycle smoke checks, additive migration, nonroot execution, dependency
  imports, vault encryption and clean callback/log handling. Owned containers
  and volumes were removed. Fifteen packaged source/asset hashes matched the
  inspected checkout.

Raw logs, screenshots, the synthetic migration result and Docker reports remain
ignored under `.local/test-results/`; they contain no live credentials.

## Limits and next boundary

OAuth/JWT, refresh, revocation and failures were tested with synthetic signed
tokens and injected transports. Actual OpenAI account/program eligibility,
authorization pages, consent, account limits and the real native/Docker callback
roundtrip have not been established. Official protocol references were checked
on 2026-10-19; they do not prove this installation's admission.

The vault requires POSIX permissions and `flock`. Native Windows operations fail
closed; ordinary unconnected application pages remain available. Container
validation used Linux amd64, Docker Engine 26.1.5 and Compose 5.6.0; Engine 28+
is the documented baseline. ARM64, other engines and predecessor-image upgrades
were not exercised. Browser validation was scoped, not the complete repository
browser suite.

Real authorization remains disabled in the installation. The next delivery must
validate an explicitly authorized account without model calls before adding
streaming inference and minimal owned financial context. There is no paid
API-key fallback, automated financial action or bank connection in this change.
