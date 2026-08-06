# CashFlow Documentation

Technical documentation for every part of the CashFlow codebase — what each piece does and why, not just what it is. For product scope, sprint history, and the design-system spec this code implements, see [`ProductRequirementsDocument.md`](../ProductRequirementsDocument.md) (the PRD) at the repo root; for template/setup/Docker operator instructions, see the root [`README.md`](../README.md).

## Where to start

| Doc | Covers |
|---|---|
| [architecture.md](architecture.md) | Stack, `core/settings.py`, URL routing, context processors, middleware, the request/response flow common to every screen. |
| [data-model.md](data-model.md) | The ERD, all four models and their fields, and every business rule (positive amounts, balance formulas, `PROTECT`/`CASCADE`/`SET_NULL` deletion behavior, uniqueness, default-data seeding). |
| [frontend.md](frontend.md) | The design system (colors, typography, component classes), the dev/prod Tailwind strategy, `base.html`, and every reusable partial. |
| [deployment.md](deployment.md) | How the Docker image is built (two-stage `Dockerfile`, Tailwind CLI compile step, WhiteNoise) and how `docker-compose.yml` wires it up. |

## Per-app reference (`apps/`)

One doc per Django app, each covering its models, forms, views, URLs, signals, admin config, and templates in full:

- [apps/core.md](apps/core.md) — project-wide settings glue, the currency registry, and the number-format override; no models/views of its own.
- [apps/pages.md](apps/pages.md) — the public landing page.
- [apps/accounts.md](apps/accounts.md) — sign up, log in, log out (native Django auth).
- [apps/categories.md](apps/categories.md) — categories & subcategories, default-category seeding.
- [apps/payments.md](apps/payments.md) — payment methods, billing cycle, no default-data seeding (FR14).
- [apps/transactions.md](apps/transactions.md) — the core `Transaction` model, form, and filtered/paginated CRUD.
- [apps/dashboard.md](apps/dashboard.md) — the aggregation/projection services, the consolidated stat-card view, and the six zero-JS SVG report charts (slideable time-series navigation, `All time` + month filters on the payment-method and category breakdowns, click-driven per-method drill-downs, and a recurrence donut that defaults to the current month).
- [apps/investments.md](apps/investments.md) — the parallel investment log (per-currency deposits/withdrawals, simulated total in the base currency, manual `ExchangeRate` management).

## How this maps to the PRD

The app-by-app breakdown above follows the same domain split as PRD §8.2 ("App Organization by Domain") and the Sprint task list in PRD §13 — each `apps/*.md` doc corresponds to one or two sprints (e.g. `apps/categories.md` covers Sprint 4, `apps/dashboard.md` covers Sprint 7, `apps/investments.md` is post-PRD). [data-model.md](data-model.md) consolidates PRD §8.3–§8.5 (data structure, enums, business rules) into one place cross-referenced from every app doc that touches those rules, rather than repeating them per app.

## Other material in `docs/`

- [`context/pre_PRD.md`](context/pre_PRD.md) — the original pre-PRD notes that preceded `ProductRequirementsDocument.md`; kept for historical context on how the domain vocabulary and scope were first framed.
- [`svg/`](svg/) — the three source diagrams (`project_information.svg`, `diagram.svg`, `basic_structure.svg`) referenced as the "Initial Visual References" in the PRD.

## Conventions used across these docs

- Every doc cross-links related docs by relative path rather than repeating content — if a rule or component is documented once, other pages link to it instead of restating it.
- Code excerpts are copied verbatim from the source files they describe (not paraphrased pseudocode); if the excerpt and the actual file ever disagree, trust the file and treat the doc as stale.
- "PRD §X" / "FRxx" / "NFRxx" references point at section numbers and requirement IDs in `ProductRequirementsDocument.md`.
