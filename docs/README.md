# Tuxedo Finance Documentation

Technical and product documentation for the current code, including unreleased
changes listed in the changelog. Technical guides are maintained in English;
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
| [Preview maintenance](../.github/preview/README.md) | Capture isolation, synthetic data generation, static tests and publication layout. |
| [product-requirements.md](product-requirements.md) | Approved scope, requirements, acceptance criteria and release compatibility. |
| [branch-testing.md](branch-testing.md) | Owner walkthrough using an isolated disposable copy; computer/phone acceptance and native fallbacks. |
| [roadmap.md](roadmap.md) | Paused interfaces and future studies; no implied availability or scheduled release. |
| [architecture.md](architecture.md) | Domain boundaries, posting workflows and sources of truth. |
| [data-model.md](data-model.md) | Models, relationships, accounting rules, FX and migration compatibility. |
| [frontend.md](frontend.md) | Server-rendered design system, viewport/focus preservation, mandatory keyboard/searchable-choice form contract, progressive disclosure and banking UI structure. |
| [interface-map.md](interface-map.md) | Application routes, screen/form/filter/action families, shared components, financial presentation exceptions and paused-feature boundaries for consistent design adoption. |
| [design-system.html](design-system.html) | Visual catalogue with the approved tokens, Paper Layers homepage, one workspace shell and compact editorial component specimens; application adoption is tracked in the interface map. |
| [operations.md](operations.md) | Native source/dependency updates, required migrations and owner-managed SQLite backup, restore, retention and rehearsal procedures. |
| [versioning.md](versioning.md) | Semantic versioning policy, automated consistency checks and release workflow. |
| [coverage-baseline.md](coverage-baseline.md) | Dated measurements, 70% combined line/branch floor, and report artifacts. |
| [Review and validation archive](reviews/README.md) | Dated investigations, delivery evidence, measured baselines and superseded interface iterations with current pointers. |

## Per-app reference

- [apps/core.md](apps/core.md) — project settings, currency registry and formatting.
- [apps/pages.md](apps/pages.md) — public landing page.
- [apps/accounts.md](apps/accounts.md) — native Django authentication and presentation preferences.
- [apps/categories.md](apps/categories.md) — income/expense categories.
- [apps/banking.md](apps/banking.md) — banks, accounts, movements, PIX, cards,
  invoices, loyalty and historical FX.
- [apps/transactions.md](apps/transactions.md) — categorized economic events, progressive list
  filters and settlement behavior.
- [apps/dashboard.md](apps/dashboard.md) — cash, cash-flow, liabilities,
  investments and net-worth read models; the net-worth interface is paused.
- [apps/investments.md](apps/investments.md) — separate position ledger using
  banks/accounts for provider and cash endpoints, with asset lifecycle and
  archived-position visibility rules, weighted cost and local dated quotes.
- [apps/planning.md](apps/planning.md) — category budgets, goals backed by
  existing cash, reservations and deterministic local review signals.
- [apps/ingestion.md](apps/ingestion.md) — paused local CSV/OFX operations,
  retained underlying services and available owned read-only posted history.
- [apps/sandbox.md](apps/sandbox.md) — private planning drafts, salary/budget
  scenarios, commitment snapshots and contribution/yield simulations.

## Repository layout

The repository follows Django conventions, with frontend tooling shared by the
application and static preview:

| Path | Responsibility |
|---|---|
| Django app directories | Domain code, migrations and focused unit tests kept beside each app. |
| `assets/` | Tailwind source input; files here are compiled rather than served directly. |
| `static/` | Versioned assets served by Django, including compiled CSS, JavaScript and brand files. |
| `tests/` | Application and preview browser tests plus standard-library repository-tool tests; Django tests stay in their apps. |
| `preview/` | Self-contained bilingual static tour published by GitHub Pages. |
| `.github/preview/` | Isolated tooling that generates and tests the public preview. |
| `scripts/` | Small repository-wide maintenance and validation commands. |
| `docs/` | Product, architecture, data, operations and frontend documentation. |

Root configuration files remain at the repository root because Django, `uv`,
npm, Tailwind, Playwright and CI discover or share them there. The application
and preview use the same locked frontend toolchain.

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

These documents describe `0.10.0` and the changes under `Unreleased`. Supported
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

The root `db.sqlite3` and `.env` are local runtime files and are ignored by Git.
A clean clone creates its database with `manage.py migrate`; each installation
owner is responsible for protecting and backing up these files.
