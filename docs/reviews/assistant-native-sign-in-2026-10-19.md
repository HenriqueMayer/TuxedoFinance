# Native ChatGPT sign-in validation — 2026-10-19

## Scope

Owner-authorized authentication-only validation after `a21ba3e`, on the native
loopback installation. No model listing, inference, financial context export,
paid fallback, bank connection or publication belongs to this step.

Before applying `assistant.0002`, stopped the existing server and created a
private SQLite backup outside the checkout, verified with `integrity_check`.
The additive migration succeeded; hashes of all 38 existing nonassistant tables
outside migration/content-type/permission bookkeeping were unchanged.
The environment file was preserved. Authorization was enabled only in the
replacement loopback server's process environment.

Current behavior belongs to the [assistant guide](../apps/assistant.md#openai-authorization-preparation)
and [frontend navigation contract](../frontend/navigation.md#assistant-panel).

## Browser findings and corrections

| Evidence | Correction | Acceptance |
|---|---|---|
| Chromium submitted `Origin: null` from the `no-referrer` settings document and `noreferrer` new-tab form; Django rejected the POST with CSRF403. | Use `same-origin` on the settings document and retain `noopener` on authorization forms. Keep no-referrer on outbound redirects and callbacks. | Actual native form passes normal CSRF checks; null origins remain rejected. No `csrf_exempt` or trusted-null workaround. |
| Chromium blocked the authorization redirect under the global self-only form-action directive. | Override only the settings view's form-action with self and the exact official authorization endpoint, preserving every other directive. | The real browser reached OpenAI's Tuxedo Finance account chooser. Ordinary account/financial/callback pages retain the global policy. |

The real callback reached the native loopback listener, completed code exchange
and identity verification, and staged the account for original-session
confirmation. The official account chooser and consent were handled by the
owner. No credential or callback query was copied into this report.

After explicit owner confirmation, the original authenticated settings session
completed the local link. Read-only metadata checks found exactly one selected
connection, status `ready`, the expected issuer, a real issued client ID,
nonempty verified identity, unexpired credentials and both plan scopes. The
authorization attempt is `complete`. Comparing the active database with the
preflight backup confirmed that all 30 financial-domain tables retained their
rows unchanged. No personal account identifiers are included in this report.

Authorization remains enabled only for the current loopback process; the
environment file and default-disabled configuration were not changed. Linked
account metadata and protected credentials persist locally across restarts.

The credential directory was inspected through file metadata only: directory
mode0700 and regular files0600. Tokens/key contents were not printed, exported
or attached. Provider selection remains `DisconnectedProvider`; authorizing a
ChatGPT account does not enable the composer or a model adapter.

## Regression checks

- All 123 assistant Django tests passed in a disposable installation, including
  21 connection HTTP tests, valid/null Origin behavior and complete CSP-policy
  comparisons. Django checks and migration consistency passed.
- All seven scoped connection browser tests passed on the final correction:
  desktop/phone, both themes, native Portuguese, edited-form departure,
  new-tab CSRF and the exact intercepted CSP target. Other assistant/domain
  browser tests and the full Django suite were not repeated in this slice.
- An earlier failed redirect fixture reached an anonymous OpenAI error page:
  Playwright did not intercept the redirected request as intended. It contained
  only a synthetic fixture parameter, with no account credentials or financial
  records. The final regression uses an intercepted first-request form target
  with no redirect or external assets; the real OAuth backend stays disabled
  in the disposable runner.
- Focused Ruff, documentation references and `git diff --check` passed. No
  stylesheet or translatable interface copy changed.

Screenshots, local logs and operational metadata stay ignored under `.local/`;
the vault and backup remain private installation material. No publication occurred.

## Limits

This validates the native host's authentication path, not Docker's real OAuth
roundtrip, a Plus/Pro quota, model availability, streaming, refresh/revocation
against the real account, or financial-answer quality. Those checks retain
their separate scopes. User consent does not authorize automatic model calls.
The [prior preparation review](assistant-authorization-2026-10-19.md) records
the broader synthetic/container checks and POSIX-platform limitations.
