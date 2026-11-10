# Architecture

## Layout

```
backend/    Django project: domain, API, tests
web/        React and TypeScript client
site/       Public page with the demonstration (Astro)
docs/       This documentation
.github/    CI workflows
```

One Docker image holds both: Django serves the API under `/api/` and the
built client for every other path.

## Backend

Django 6 with django-ninja. Each application owns its models and rules.

| Application | Owns |
|---|---|
| `config` | Settings, URL routes, the API mount, currencies, the financial clock |
| `accounts` | The preferences of a user, the session operations |
| `banking` | Banks, accounts, cards, invoices, payments, transfers, movements, loyalty, exchange rates |
| `ledger` | Transactions, categories, the occurrence engine, repeating entries, the ledger synchronization, statement-import models |
| `investments` | Investment products, assets, operations, price observations, the position replay and its valuation |
| `planning` | Spending limits from a month on, goals and their reserved balances, the sheet of the months ahead, the calculators, the month closing |
| `reports` | Reads for Home: the month, what is due, the net worth |

Rules:

- A domain module does not import the web layer.
- Each application has one `api.py` with one router. An operation reads a
  schema, calls the model or service that owns the rule, and returns a
  schema. No financial rule lives in `api.py`.
- Every operation needs the Django session. Cookie authentication checks the
  CSRF token on unsafe methods. Sign in and sign up have no authentication, so
  they call `config.security.require_csrf`.
- A record of another user answers 404 when it is named in the address, and a
  field error when it is named in the request body (`config.ownership`).
- Errors have one shape: `{"detail": ..., "errors": {field: [messages]}}`.
  Messages without a field use the key `__all__`. Keys follow the request
  fields.
- Amounts travel as decimal strings. Calendar dates travel as ISO strings.

## Client

Vite, React 19, TypeScript in strict mode, Tailwind 4.

| Concern | Where |
|---|---|
| API types | Generated from the OpenAPI schema: `npm run api:types` writes `src/api/schema.d.ts` |
| Server data | TanStack Query. Hooks are in `src/data/` |
| Routes | TanStack Router, defined in code in `src/router.tsx` |
| Filters | Search parameters of the route. A change replaces the address and does not move the page |
| Windows | The search parameter `w`. See `src/windows/host.tsx` |
| Messages | Typed objects in `src/i18n/`. English defines the keys |
| Language and theme | Saved in the browser. Currency, date order and Home blocks are saved on the server |

Rules:

- A module does nothing to the page when it is imported.
- The client never calculates money. It shows amounts and reads what the
  owner types (`src/lib/money.ts`). A bar length may compare two amounts.
- A page component gets its filters and a change function as properties. The
  route in `src/router.tsx` connects them to the address.

## Tests

A test exists where a defect would cost money or data. Its cost follows the
size of the change.

| Layer | Proves | Runs |
|---|---|---|
| Domain tests (`backend/*/tests/`) | Financial rules | Each backend change |
| API tests (`test_api.py` and similar) | Each operation: session, ownership, validation, and the balance or invoice after a write | Each backend change |
| Client unit tests (`web/src/**/*.test.ts`) | Pure logic: amounts, dates, paths, error messages | Each client change |
| Journeys (`web/tests/journeys/`) | Complete tasks in a browser against the real backend with a temporary database | Each change of `web/` or `backend/` |

CI has two workflows with path filters: `backend.yml` and `web.yml` (two
parallel jobs). A change that touches only documentation runs neither.

A journey creates its own user, so journeys do not depend on each other.

## Public site

`site/` is an Astro project that builds static pages for GitHub Pages. A
page embeds the client, built in demonstration mode, in an `iframe`.

- **One seam for data.** The client reaches the API through the `fetch`
  option of `web/src/api/client.ts`. The demonstration build replaces it with
  `web/src/demo/fetch.ts`, which answers from a recorded file. No other
  module knows about the demonstration, except the shell (one line of text),
  the router (the address after `#`) and the entry file (it waits for the
  data).
- **Recorded answers.** `backend/reports/demo.py` creates a fictional owner
  through the API and reads every screen through the API. The site serves
  those answers, so the demonstration shows what the real rules calculate.
- **Read-only.** A request that would change a record is refused in the
  browser with a message.

See [site/README.md](../site/README.md).

