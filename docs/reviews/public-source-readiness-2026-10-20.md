# Public-source review and documentation alignment — 2026-10-20

## Scope and result

Reviewed the current `aac5891` worktree, including its uncommitted assistant
implementation, before changing public documentation. The source scan combined
an independent architecture review, independent baseline audit, focused
assistant and financial-boundary reviews, and repository-wide pattern searches.

The inventory contained 896 tracked or nonignored untracked files. Reviewers
fully inspected 136 distinct files around authentication, ownership, financial
forms/services, OAuth/vault/provider transport, assistant tools and confirmation,
imports/exports, browser rendering, deployment and preview isolation. Search hits
and excerpts were not counted as full-file review. The remaining 760 files did
not receive exhaustive manual inspection.

No substantiated vulnerability or apparent embedded credential/private key was
found in the inspected current source. Example signing values and test identities
were demonstrably placeholders, generated values or synthetic fixtures. Current
text searches also checked private paths, personal email/identifier patterns and
unsafe rendering/execution/query primitives. This is partial static coverage,
not a certification of the repository or an installation.

Git history, ignored installation configuration, databases, credential vaults,
logs/backups, dependency implementation, host/proxy configuration and deployed
artifacts were excluded. No credential was used and no live model or bank request
was made. Canonical scanner artifacts are retained locally by the security
workbench; private artifact paths are not part of this public documentation.

## Controls and remaining limits

- Inspected HTTP and financial boundaries use Django authentication, CSRF and
  owner checks, including related-record validation and signed chart-source tokens.
- Model tools perform bounded owned reads/calculations or prepare proposals.
  A separate session-bound confirmation revalidates immutable parameters and
  current state before canonical financial services write; execution is idempotent.
- OAuth uses state, nonce, PKCE, verified provider identity and original-session
  attachment. Reusable credentials remain in a private encrypted vault, with
  explicit paired-backup requirements.
- Provider endpoints are fixed, with redirect/proxy restrictions and processing
  limits. Markdown creates literal allowed elements; generated URLs/images do
  not become executable or independently authorized references.
- Public hosting still needs operator-managed TLS, access controls and login
  throttling. Current CSP permits inline scripts/styles. Faithful raw CSV and
  explicit spreadsheet-safe CSV retain their documented different purposes.
  These constraints were not presented as newly discovered vulnerabilities.

A future exhaustive audit should cover the remaining files and historical
secret exposure. Actual runtime permissions and externally deployed release
configuration require separate evidence. No claim is made about every dependency,
model, provider account or real Docker authorization flow.

## Corrections

Current guides had stale statements that financial execution was unimplemented
or financial evidence was restricted to a per-message page opt-in. Updated the
security, architecture, data model, product requirements, operations, navigation,
interface and assistant guides, plus environment-example comments, to describe
the actual bounded toolkit and six separately confirmed changes. The optional
legacy initial-page snapshot is distinct from general owned consultation; the
current composer has no page-data checkbox. Historical dated reviews remain
unchanged.

Both READMEs retain their concise layout, prominent preview and Docker quick
start. Their short unreleased-assistant note explains necessary remote context
and links to the owning guide. Settings/history disclosure copy now makes that
data flow explicit in English and Brazilian Portuguese. No provider gate was
enabled, paid fallback added or application capability expanded.

Regenerated all 28 preview captures from disposable synthetic profiles, across
seven workspaces, two languages and both themes. Capture ran with live gates off,
staged images before replacement, and verified that the installation database
fingerprint stayed unchanged. The tour remains static: it shows current charts,
New entry and the shell launcher, without connected chat or real financial data.
No version, tag, image or website was published.

## Validation

| Check | Current result |
|---|---|
| npm audit, all severities | Zero known advisories in the locked frontend tool tree. |
| pip-audit, strict locked runtime export | Zero known advisories in 11 applicable packages on this platform. Platform-excluded dependencies were not audited here. |
| Isolated Django system/migration checks | Passed; no missing migrations. |
| Complete isolated Django suite | 1,169 tests passed. |
| Repository tooling | 44 tests passed. |
| JavaScript helpers/Markdown | 26 tests passed. |
| Static preview browser suite | 17 tests passed, including both languages/themes, desktop/phone, keyboard/history and native fallback. |
| Focused application browser suites | 18 connection/history-privacy cases and 9 Markdown-copy cases passed. History disclosure was checked with real keyboard events in English/Portuguese on desktop/phone and both themes. |
| Documentation and version | 87 documents, 751 local references, zero unresolved; version remains 0.10.0. |
| Assets, translations and source hygiene | Rebuilt CSS matches the committed asset; gettext format/compile checks, Ruff executable-correctness checks and `git diff --check` passed. |

Preview screenshots were visually inspected on desktop and phone in both themes,
including full-size application captures. Settings and History disclosures were
also visually inspected at 1440px and 390px in both themes. The focused browser
regression keeps the disclosure inside the viewport, opens it with Enter and
checks Escape/focus restoration. Clipboard permission was simulated; native
downloads and session/owner authorization checks used the actual application.
Application evidence stays under ignored
`.local/reviews/public-readiness-2026-10-20/`; preview-browser frames stay under
`.local/test-results/preview/`.

Tests used temporary databases and empty environment files. Ordinary runs kept
live gates disabled; explicit synthetic assistant fixtures block real external
transports. No developer
database/server was used for browser tests. The complete application browser
inventory and Docker release lifecycle were not rerun as part of this focused
documentation change. Their release gates and owner acceptance remain in force.
