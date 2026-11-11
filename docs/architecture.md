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
| `reports` | Reads: the Home blocks, the month, the net worth, the analysis of a period, the origin of a month, the analysis of one Wallet item. Also the export of the demonstration data |

Rules:

- A domain module does not import the web layer.
- The operations of an application are in its `api.py`. `banking` and
  `ledger` have a second file for a second subject (`loyalty_api.py`,
  `import_api.py`). An operation reads a schema, calls the model or service
  that owns the rule, and returns a schema. No financial rule lives in an API
  file.
- Every operation needs the Django session, except four: the health read, the
  session read, sign in and sign up. Cookie authentication checks the CSRF
  token on unsafe methods. Sign in and sign up change state without a
  session, so they call `config.security.require_csrf`.
- A record of another user answers 404 when it is named in the address, and a
  field error when it is named in the request body (`config.ownership`).
- Errors have one shape: `{"detail": ..., "errors": {field: [messages]}}`.
  Messages without a field use the key `__all__`. Keys follow the request
  fields.
- Amounts travel as decimal strings. Calendar dates travel as ISO strings.

The routers are mounted in `backend/config/api.py`. `/api/openapi.json` has
every operation with its schemas.

| Mount | Subject |
|---|---|
| `/api/session` | The session, sign in, sign up, sign out, preferences |
| `/api/banking` | Accounts, credit and debit cards, invoices and their payments, transfers, exchange rates, the Wallet read, the instruments of an entry |
| `/api/loyalty` | Points programs and their entries |
| `/api/ledger` | Transactions, the monthly schedule of a repeating entry, categories with their CSV export and import |
| `/api/imports` | Statement import: upload, mapping, review, confirmation, undo |
| `/api/investments` | Positions and their operations |
| `/api/plan` | The month plan, the limit and budgets, goals, the forecast, the sheet and saved sheets, the calculators, the month closing |
| `/api/reports` | `home`, `month`, `net-worth`, `analysis`, `analysis/month`, `items/{investment,account,card}/{id}` |
| `/api/health` | Says that the server answers. The container health check reads it |

## Client

Vite, React 19, TypeScript in strict mode, Tailwind 4.

| Concern | Where |
|---|---|
| API types | Generated from the OpenAPI schema: `npm run api:types` writes `src/api/schema.d.ts` |
| Server data | TanStack Query. Hooks are in `src/data/` |
| Routes | TanStack Router, defined in code in `src/router.tsx` |
| Filters | Search parameters of the route. A change replaces the address and does not move the page |
| Windows | The search parameter `w`, and `w2` for one window above it. `wm` is the month of the month window and `wp` the period of the analysis. See `src/windows/host.tsx` |
| Messages | Typed objects in `src/i18n/`. English defines the keys |
| Language and theme | Saved in the browser. Currency, date order, number format and Home blocks are saved on the server |

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
| Client unit tests (`web/src/**/*.test.ts`) | Pure logic: amounts and their typing, dates, periods, paths, error messages | Each client change |
| Journeys (`web/tests/journeys/`) | Complete tasks in a browser against the real backend with a temporary database | Each change of `web/` or `backend/` |

CI has four workflows: `backend.yml`, `web.yml` (two parallel jobs),
`docker.yml` and `pages.yml`. A pull request runs the ones whose paths it
touches; a pull request that touches only documentation runs none. A push to
`main` always runs the backend and the client workflows.

A journey creates its own user, so journeys do not depend on each other. The
journeys of the session and of the shell use one shared user, and leave its
preferences as they found them.

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

