# Local assistant foundation — 2026-10-18

This dated record covers the first assistant delivery on
`feat/tuxedo-assistant-foundation`, starting from `fa37928`. The prior v1
candidate branch remains at that commit. The developer version remains `0.10.0`; it is not a
release or authorization to publish. Current contracts live in the
[assistant guide](../apps/assistant.md), [navigation guide](../frontend/navigation.md#assistant-panel)
and [interface map](../interface-map.md#assistant-utility).

## Delivered behavior

- A branded floating utility opens a usable desktop dock or a narrow-screen
  sheet. The native assistant page provides local history and explicit
  creation/deletion without JavaScript.
- Conversations/messages are local and owner-scoped. The production composer
  is disabled; direct message submission returns 503 without saving a message.
- Context is signed, expiring, bounded and read-only. Its modest current
  coverage and omissions are disclosed in the owning guide; no financial
  projection, conversion or mutation is triggered by collecting it.
- Provider streaming/cancellation/error interfaces, non-executable proposals
  and English v1 instructions are prepared. Eleven synthetic evaluation cases
  supply questions and rubrics; they are not scored model evaluations.
- The Design Lab demonstrates synthetic conversations, references, loading,
  cancellation, failure and disconnection without external requests.
- The separate [Open Finance study](open-finance-personal-study-2026-10-18.md)
  records why personal PF eligibility and a 6–8-hour cadence remain unresolved.

## Verification

All application checks used an empty environment file and disposable data.
Browser tests used the npm-owned loopback server/database. No installation
database, `.env`, backup or running personal server was used for validation.

| Check | Observed result |
|---|---|
| Full Django suite with branch coverage | 787 tests passed; combined coverage rounded to 95%, above the existing 70% floor. |
| Focused assistant backend | 36 tests passed after the final presentation changes, including ownership, CSRF, no-store, scope expiry, context precision/no writes and offline contracts. |
| Django system check and migration drift | Passed; no uncommitted model/migration discrepancy. |
| Synthetic upgrade | Applying the new assistant migration preserved the exact existing user/financial rows across 34 tables. |
| Repository tooling | 40 Python tooling tests passed; version remains consistent. |
| JavaScript unit suite | 16 tests passed. |
| Application assistant browser scenarios | 17 passed across English/Portuguese, light/dark and 1440/390/320px, including native fallback, touch and departure-dialog integration. |
| Design Lab assistant scenarios | Six passed in the final combined 23-case run, including 320px touch/reduced motion and native fallback. |
| Whole catalogue regression pass | All 47 catalogue cases passed after the reduced-motion correction. |
| Static public preview | 17 tests passed. |
| Container packaging | Built `tuxedo-finance:assistant-validation`; isolated migration, native assistant pages/local creation and bundled instruction/provider smoke passed with network disabled and no mounted data. |
| Full application browser suite | Completed: 498 passed, six skipped by existing guards, two catalogue reduced-motion failures; both failures were corrected and passed in the whole 47-case catalogue rerun. |
| Additional short-phone history/context scenarios | Passed in both themes at 320 × 480, with long/untrusted history labels, expanded context, scrolling, visible close and focus return. |
| CSS, translations, executable-correctness lint and diff whitespace | CSS rebuilt; Portuguese catalog compiled with format checks; Ruff F checks and diff check passed. |

The browser scenarios exercise unchanged financial drafts while using local
chat actions, existing departure confirmation, HTMX navigation, Back/Forward,
account switching, cancelled reads and request failures. Reopening a panel
cannot expose a hidden old transcript while fresh authorization is pending.
Asset-version recovery offers a native GET instead of inserting mixed-version
markup or automatically reloading an edited financial form.
The mobile sheet leaves native top-layer dialogs available; its focus trap yields
while a departure confirmation is open. Same-document Back keeps the edited
transaction intact after cancelling that confirmation. A native touch context
also verifies conversation continuity and launcher clearance above mobile navigation.

Display dates and money use the application's formatting conventions, with the
capture timezone visible. The snapshot retains its ISO timestamps, financial
cutoff and canonical numeric strings; presentation does not change the evidence.
Machine owner/page identifiers remain unlocalized; a regression covers owner IDs
above 999 in English and Brazilian Portuguese with number grouping enabled.

The full run collected 506 cases before four additional assistant edge scenarios
were added. Its two failures came from transitions on the Lab assistant's shared
actions, outside the older section-scoped reduced-motion reset. The reset now
covers the entire assistant specimen. The 47-case catalogue rerun passed, and
the final assistant/Lab run passed all 23 cases. After the final identifier
formatting adjustment, all 17 application assistant cases passed again. The
unaffected full inventory was not repeated; no failure remains unresolved by
these focused checks. Existing skipped guards were not removed or bypassed.

Commands used the documented isolated Django environment and npm entry points:
`coverage run --branch manage.py test`, `manage.py test assistant`,
`npm run test:e2e`, targeted assistant/catalogue invocations of that same runner,
`npm run test:preview`, `npm run test:unit` and `uv run python scripts/check_docs.py`.
The final documentation check resolved 601 local references across 65 documents.
The 787-case coverage measurement preceded the final date/money/identifier
presentation refinements. The focused 36-test backend and 17-case application
browser runs cover those final changes; coverage percentage was not recomputed.

Rendered application screenshots at desktop/phone sizes in both themes were
inspected. A whole-sheet opacity animation initially showed the underlying
financial form through the text; the narrow sheet is now opaque from its first
frame. The Design Lab's desktop, phone and short-touch screenshots were also
inspected. Raw synthetic logs/screenshots remain under ignored
`.local/test-results/assistant-app-2026-10-18/` and the assistant Lab/backend
evidence directories, not in the public repository.

An independent static review checked ownership, signed context, escaping,
private history, cancellation and modal focus. Three concrete custom-fetch
recovery/privacy issues were fixed and covered by browser regressions. Static
review is additional evidence, not proof of every future provider behavior.

## Limits and next boundary

The initial migration creates assistant tables only. It was not applied to the
personal installation. There are no provider credentials, live model calls,
bank connections, paid services, unattended jobs or financial action execution.
No release, tag or publication was performed.

The Docker allowlist now includes the new app. This host has Engine 26.1.5;
the checks above establish packaging/basic runtime behavior, not the full
supported Engine 28+ lifecycle, backup/restore or container browser matrix.

Connecting ChatGPT and validating actual model answers remain separate work.
Recheck provider eligibility, OAuth/local-Docker callback behavior, protected
credential storage, limits and current streaming requirements first. Open
Finance implementation remains behind its documented feasibility decision;
the paused statement-import interface stays paused.
