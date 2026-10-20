# Assistant actions and response feedback — 2026-10-19

## Scope

Working-tree changes based on `aac5891`, reviewed on 2026-10-19 in
America/Sao_Paulo. This focused delivery reopens chat feedback, Markdown,
user-confirmed local financial actions and Planning tab spacing. Open Finance,
publication and the release hold remain unchanged.

- Waiting for a reply shows Thinking; arriving text changes it to Writing a
  response. Stop, failure, completion and reduced motion retain their own states.
- A dependency-free bounded Markdown renderer supports ordinary financial
  explanations and tables without interpreting HTML, fetching images or trusting
  generated links. Native chat retains escaped Markdown source.
- Tuxedo can prepare income/expense transactions, source categorization, goals
  and category budgets. Each has a local immutable review and separate Confirm
  or Discard action. No model tool or chat text can confirm a financial write.
- Planning, Investments and Planning tools reuse the shared 24px interval between
  section tabs and heading, removing the former 4px workspace override.

The [confirmed action guide](../assistant/actions.md),
[assistant reference](../apps/assistant.md) and
[workspace presentation contract](../frontend/workspaces.md) own current behavior.
The Design Lab demonstrates the same presentation with synthetic data; its
confirmation changes page memory only.

## Preservation and action boundaries

Additive migration `0006_actionproposal` adds review metadata. Preparation does
not save financial rows or synchronize the ledger. Confirmation uses existing
forms and services, repeats ownership/current-state validation and atomically
claims the proposal before writing. Repeated or concurrent confirmation cannot
create a second record. A changed, expired, foreign-session, failed-generation
or discarded proposal cannot execute.

Categorization writes only category and update timestamp, preserving even exact
legacy title/note whitespace. Equivalent normalized parameters share one
proposal identity within a generation. Full review summaries stay local;
preparation returns only identity/action/pending state to the model. Bounded
choice lookups disclose only the metadata needed for an explicitly requested
action. Unchecked page-data consent remains independent.

No payment, transfer, deletion, alert activation, import, bank connection or
unattended write was added. Goals do not implicitly reserve cash. Category
splits, generated-record locks, card cycles, recurrence limits and budget
overlap checks remain owned by their existing application workflows.

## Validation

All browser runs used `npm run test:e2e`, disposable SQLite databases and owned
loopback servers. Synthetic-provider settings blocked external network and real
authorization/inference. The installation was never used for fixtures.

| Check | Evidence |
|---|---|
| Django system/migration checks | `manage.py check` and `makemigrations --check --dry-run` in the documented isolated environment. |
| Python correctness | Final full Django suite: 1,075 passed after the preservation/privacy fixes; repository tooling: 44 passed. Terminal results retained locally. |
| Frontend correctness | `npm run test:unit`: 23 passed. JavaScript syntax checks, Ruff executable-correctness rules, compiled CSS comparison and gettext compilation comparison passed. |
| New chat/action and Planning cases | 13 scoped cases approved: 11 initially, then both phone action cases after correcting the Portuguese test expectation to the existing feminine “Concluída”. |
| Existing streaming and catalogue | 17 cases approved, including native submission, invalid effort, compact context, reduced motion and synthetic review. |
| Local history and window behavior | 22 ordinary disconnected cases passed; all 34 skipped synthetic cases were then executed separately with `--assistant-fixtures` and passed. |
| Documentation | Local link/anchor checker: 82 documents, 718 references, no unresolved links. `git diff --check` passed. |

The new action tests cover all four supported writes, no write before
confirmation, duplicate confirmation, discard, failed generations, native POST
confirmation, unchanged unrelated financial drafts and retained chat draft/focus.
Service tests also cover concurrent confirmation, stale references, ownership,
session changes, rollback, native currency, cards/PIX/recurrence, category splits,
managed sources and budget overlap. A privacy regression keeps existing source
notes out of preparation results while retaining them in the local review.

Rendered evidence was inspected at desktop and phone sizes in light/dark themes,
including Portuguese/English, long rich text, tables, review cards, pending and
completed actions, focused composer, short viewports and Planning headings.
Real keyboard tests preserve Enter/Shift+Enter, Tab, 44px actions, native forms,
settings, history, logout isolation and HTMX draft restoration.

Raw evidence belongs under ignored
`.local/reviews/assistant-refinements-2026-10-19/`, including browser-first,
browser-phone, browser-streaming-lab and browser-local-window captures and the
final isolated Django logs. These local artifacts are not release deliverables.

The four browser batches above cover 86 distinct affected cases; the only
initial failures were the two corrected Portuguese label expectations.

## Native installation update

With no application server running, a private SQLite backup was created outside
the checkout under the owner's `tuxedo-finance-backups` directory and verified
with `PRAGMA integrity_check`. Only `assistant.0006_actionproposal` was pending
in the selected migration plan and was applied. The new review table remains
empty; no financial action was executed on installation data.

A content comparison with the backup confirmed every preexisting row unchanged,
including financial records, conversations, settings and connection metadata.
An initial whole-table equality check correctly detected additions to Django's
metadata tables: one content type and four default permissions for the new
model. Follow-up row comparison confirmed these were the only additions to
existing tables, with no original row removed or modified. SQLite integrity
remained valid. Environment files and the credential vault were not changed.

## Limits

No live provider/model, financial export, bank request or new consent was used
for validation. The bounded namespaced function-calling protocol was tested with
synthetic streams; live model behavior, tool selection and instruction compliance
remain unverified. The renderer intentionally implements a Markdown subset,
not full CommonMark. Browser coverage is focused on affected responsibilities,
not a fresh run of the entire application browser inventory. No commit, merge,
tag, paid API fallback or publication was performed.
