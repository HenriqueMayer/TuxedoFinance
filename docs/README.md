# Tuxedo Finance Documentation

Technical and product documentation for the current `0.11.0` release candidate.
Merge and Docker publication were authorized on 2026-10-21; release validation
is underway. Technical guides are maintained in English;
the root README is available in [English](../README.md) and
[Português (Brasil)](../README.pt-BR.md).

[Docker installation and operations](docker.md) covers local images, published
releases, persistent volumes and isolated restore rehearsals.

## Where to start

| Doc | Covers |
|---|---|
| [Contributing](../CONTRIBUTING.md) | Canonical developer setup, checks, translations, browser isolation, and documentation conventions. |
| [Interface preview](https://henriquemayer.github.io/TuxedoFinance/) | Bilingual static tour of the application using synthetic financial data. |
| [demo-data.md](demo-data.md) | Explicit creation of separate English and Portuguese demo accounts, date options and a presentation walkthrough. |
| [Preview maintenance](preview.md) | Interactive product presentation, fictional workspace/chat examples, capture isolation and static verification. |
| [product-requirements.md](product-requirements.md) | Approved scope, requirements, acceptance criteria and release compatibility. |
| [branch-testing.md](branch-testing.md) | Owner walkthrough using an isolated disposable copy; computer/phone acceptance and native fallbacks. |
| [roadmap.md](roadmap.md) | Paused interfaces and future studies; no implied availability or scheduled release. |
| [Personal Open Finance study](reviews/open-finance-personal-study-2026-10-18.md) | Dated PF coverage, eligibility, cadence/cost limitations and reconciliation design for Nubank, Inter and Mercado Pago; no enabled bank connection. |
| [Intraday Open Finance alternatives](reviews/open-finance-intraday-study-2026-10-19.md) | Follow-up retaining the 6–8-hour requirement, personal REST/MCP candidates and outstanding provider/resource/local-delivery evidence. |
| [Meu Pluggy bill pilot](open-finance-pilot.md) | Operator-only free personal Inter bill probe, offline preparation, hidden credential setup, daily observation reuse and preserved ledger/import gates. |
| [Tuxedo financial premises](assistant/financial-premises.md) | Assistant identity, original personal-finance reasoning rules, inspected plugin methodology and future news/source boundaries; browsing is not enabled. |
| [Confirmed assistant actions](assistant/actions.md) | Local proposal tools, minimal choices, immutable review, explicit confirmation and preserved financial validation. |
| [Assistant consultations](assistant/consultation.md) | Default owned financial reads, canonical monthly CLT simulation and separation from persistent changes. |
| [architecture.md](architecture.md) | Domain boundaries, posting workflows and sources of truth. |
| [data-model.md](data-model.md) | Models, relationships, accounting rules, FX and migration compatibility. |
| [frontend.md](frontend.md) | Entry index for the responsibility-specific frontend contracts: runtime, presentation, forms, catalogue, navigation, charts, consultation and workspace compositions. Earlier section URLs remain available. |
| [interface-map.md](interface-map.md) | Application routes, screen/form/filter/action families, shared components, financial presentation exceptions and paused-feature boundaries for consistent design adoption. |
| [design-system.html](design-system.html) | Visual catalogue with the approved tokens, Paper Layers homepage, one workspace shell and compact editorial component specimens; application adoption is tracked in the interface map. |
| [operations.md](operations.md) | Native source/dependency updates, required migrations and owner-managed SQLite backup, restore, retention and rehearsal procedures. |
| [versioning.md](versioning.md) | Semantic versioning policy, automated consistency checks and release workflow. |
| [coverage-baseline.md](coverage-baseline.md) | Dated measurements, 70% combined line/branch floor, and report artifacts. |
| [Review and validation archive](reviews/README.md) | Dated investigations, delivery evidence, measured baselines and superseded interface iterations with current pointers. |

## Current checkout and feature status

The [PRD delivery-status table](product-requirements.md#current-delivery-status)
distinguishes implemented interfaces, paused workflows and optional gated
connections. The six primary destinations are Home, Transactions, Accounts,
Investments, Plan and Analytics. Their current sections and actions belong in
the [interface map](interface-map.md), with shared title/summary geometry in the
[compact workspace density contract](frontend/catalogue.md#compact-workspace-density).

| Boundary | Current reference |
|---|---|
| Local financial workspaces | Owning app guides below; release 0.11.0 is authorized, with exact-revision checks and remaining manual acceptance recorded separately. |
| Paused statement operations and net-worth interface | [Roadmap](roadmap.md) and [code-level review gates](../core/features.py); retained calculations and owned posted-import provenance do not reopen these screens. |
| Optional assistant | [Assistant guide](apps/assistant.md) and [six confirmed local actions](assistant/actions.md); ChatGPT authorization/inference independently default off, with no paid API-key fallback or Internet/news tool. |
| Paused real Open Finance pilot | [Operator guide](open-finance-pilot.md) and [roadmap decision](roadmap.md#personal-open-finance-study); read-only command preparation does not connect the application or write its ledger. |

## Per-app reference

- [apps/core.md](apps/core.md) — project settings, currency registry and formatting.
- [apps/pages.md](apps/pages.md) — public landing page.
- [apps/accounts.md](apps/accounts.md) — native Django authentication and presentation preferences.
- [apps/categories.md](apps/categories.md) — income/expense categories.
- [apps/banking.md](apps/banking.md) — banks, accounts, movements, PIX, cards,
  native invoice credits, automatic/confirmed payments, loyalty and historical
  FX; Accounts, Invoices, Loyalty and Exchange rates have explicit sections.
- [apps/transactions.md](apps/transactions.md) — categorized economic events, progressive list
  filters and settlement behavior.
- [apps/dashboard.md](apps/dashboard.md) — cash, cash-flow, liabilities,
  investments and net-worth read models; the net-worth interface is paused.
- [apps/analytics.md](apps/analytics.md) — the shared financial/investment analysis
  workspace and compatible chart routes, reusing existing financial services.
- [apps/investments.md](apps/investments.md) — separate position ledger using
  banks/accounts for provider and cash endpoints, with asset lifecycle and
  archived-position visibility rules, weighted cost and local dated quotes.
  My investments, History, Prices and Setup expose the existing flows; an
  independent curated emoji is a cosmetic product/asset-position preference.
- [apps/planning.md](apps/planning.md) — category budgets, goals backed by
  existing cash, reservations and deterministic local review signals. This month,
  Goals, Simulations and Alerts keep operational plans separate from scenarios.
- [apps/ingestion.md](apps/ingestion.md) — paused local CSV/OFX operations,
  retained underlying services and available owned read-only posted history.
- [apps/sandbox.md](apps/sandbox.md) — private planning drafts, salary/budget
  scenarios, commitment snapshots and contribution/yield simulations.
- [apps/assistant.md](apps/assistant.md) — local conversations, signed owned
  context, gated OpenAI account settings/vault, account-specific model selection,
  streaming, cancellation, safe Markdown and private history/export. Targeted
  owned consultations and canonical monthly simulations are available to the
  connected assistant; six local changes require separate reviewed confirmation.
  Authorization and inference default off, with no paid API-key fallback or
  bank connection. Live-provider observations and their limits belong in the
  [dated reviews](reviews/README.md), not a guarantee for another installation.

## Repository layout

The repository follows Django conventions, with frontend tooling shared by the
application and static preview:

| Path | Responsibility |
|---|---|
| Django app directories | Domain code and migrations, with focused Python tests in each app's `tests/` package. Views/forms with distinct responsibilities use packages with explicit public exports. |
| `assets/` | Tailwind configuration and CSS source input; compiled rather than served directly. |
| `static/` | Versioned assets served by Django, including compiled CSS, JavaScript and brand files. |
| `tests/` | Explicit Playwright configurations, application specs grouped by domain, preview browser tests and repository-tool/JavaScript unit tests; Django tests stay in their apps. |
| `preview/` | Self-contained bilingual static tour published by GitHub Pages. |
| `.github/` | Workflows and repository rules; local preview tooling belongs to `scripts/preview/`. |
| `scripts/` | Small repository-wide maintenance and validation commands, including isolated preview capture in `scripts/preview/`. |
| `docs/` | Product, architecture, data, operations and frontend documentation. |
| `docs/frontend/` | Canonical interaction and presentation guides, reached through `docs/frontend.md`; app guides retain financial rules and deliberate domain exceptions. |
| `.local/` (ignored) | New disposable test runtime, diagnostics, browser reports, coverage and lint caches. Never installation data. |

Root entries retain Django's launcher, dependency manifests/lockfiles,
Docker/Compose and project policies. Tailwind configuration is explicitly loaded
from `assets/tailwind.config.js`; the disposable browser runner explicitly loads
`tests/playwright.config.js`. Preview tests use their own configuration under
`tests/preview/`. The application and preview share the same locked frontend
toolchain. Existing root artifacts, environments, databases and backups are
preserved when new tool outputs move to `.local/`.

## Canonical references

Keep each rule with its owner instead of copying the same instructions into
every guide:

| Question | Source of truth |
|---|---|
| How do I install this version? | The matching release's root README and [operations](operations.md)/[Docker guide](docker.md). |
| How do I contribute or validate a change? | [Contributing](../CONTRIBUTING.md); [AGENTS.md](../AGENTS.md) adds the agent-facing entry contract. |
| How should a control look and behave? | [Visual catalogue](design-system.html), [frontend contracts](frontend.md) and [route/component map](interface-map.md). |
| Which financial rules and service boundaries apply? | [Architecture](architecture.md), [data model](data-model.md) and the owning app guide. |
| Is an interface available or paused? | [Roadmap](roadmap.md), the owning app guide and its code-level feature gate. |
| What was measured or approved in an earlier iteration? | The [dated archive](reviews/README.md); its test counts and screenshots do not certify the present checkout. |

When changing a workflow, update its owning guide and link the shared contract.
Keep historical reports dated and clearly labelled, with pointers to the current
guide. Do not turn local logs, copied credentials, database contents or transient
preview paths into installation instructions.

## Documentation status

These documents describe version `0.11.0`. The owner authorized
merge and Docker publication on 2026-10-21; automated release checks and any
remaining manual acceptance retain their own recorded status. This is not a
claim of v1 acceptance or general eligibility for optional providers. Supported
released installations use the committed incremental migrations and preserve
existing records. The historical clean reset applied only to pre-release legacy
schemas; it is not an instruction to reset a released installation. See
[Docker updates](docker.md#update) before upgrading.

The repository does not include a runtime demo database, shared account or fixed
credential. Normal new accounts receive only the approved default categories.
The optional [`insert_demo` command](demo-data.md) creates a new, separate account
with synthetic financial records only when explicitly run; it is not part of
setup, migrations or signup. The developer-only preview capture command creates
disposable synthetic records in a guarded temporary database, deletes that
database after capture, and commits only screenshots.

Dependency maintenance and local database operations are documented in
[operations.md](operations.md). The database owner is responsible for choosing
backup storage, permissions, encryption and retention, and for rehearsing a
restore before relying on a backup.

The root `db.sqlite3`, `.env` and default `assistant-private` vault are local
runtime files/directories and are ignored by Git.
A clean clone creates its database with `manage.py migrate`; each installation
owner is responsible for protecting and backing up these files. A database-only
backup cannot restore prepared account credentials; follow the
[assistant recovery boundary](operations.md#assistant-data-and-integrations).
