# Testing

The suite is built entirely on Django's own `django.test.TestCase` (SQLite, transactional rollback between tests) — no third-party test libraries (`pytest`, `factory_boy`, etc.) are used anywhere in the project, per the "no over-engineering" house rule. Tests were deliberately deferred until Sprint 9, after every feature sprint had already landed; the per-app counts below are the one place this doc tallies them.

## Running the suite

```bash
uv run python manage.py test
```

Runs all `tests.py` files across every app. Django's test runner creates a throwaway test database for the run and always force-sets `DEBUG=False` regardless of the environment — this is exactly why `core/settings.py` selects the static-file storage backend from a module-level `DEBUG` snapshot rather than `django.conf.settings.DEBUG`; see [architecture.md § Static files](architecture.md#static-files).

To run a single app's tests:

```bash
uv run python manage.py test transactions
```

## Coverage by app

| App | Tests | File |
|---|---|---|
| `core` | 21 | `core/tests.py` |
| `accounts` | 6 | `accounts/tests.py` |
| `categories` | 24 | `categories/tests.py` |
| `payments` | 24 | `payments/tests.py` |
| `transactions` | 85 | `transactions/tests.py` |
| `dashboard` | 66 | `dashboard/tests.py` |
| `pages` | 1 | `pages/tests.py` |
| **Total** | **227** | |

Every app's suite is organized into up to three `TestCase` classes, mirroring the PRD's Sprint 9 checklist:

- **Model tests** — field validation (e.g. `Transaction.amount` rejecting zero/negative), `__str__` output, default values, timestamp behavior (`created_at` immutable across updates, `updated_at` advances), uniqueness constraints, and `ProtectedError` on deleting a still-referenced `Category`/`PaymentMethod`.
- **View tests** — every route requires authentication (redirect to `accounts:login?next=...` or a bare `302`); list views only ever return the logged-in user's own rows; update/delete of another user's object returns `404` (never leaks existence via a `403` or different error); full create/update/delete round-trips; the `ProtectedError` → friendly-`messages.error()` path end-to-end.
- **Form tests** — required fields enforced; FK dropdowns (`category`, `payment_method`, `parent_category`) scoped to the requesting user; a couple of security-relevant cases go further than "hidden from the dropdown" and assert a **guessed** cross-user `pk` is actively rejected as invalid (`transactions/tests.py::test_other_users_category_is_rejected_even_if_pk_is_guessed`).

`dashboard/tests.py` is the exception to this shape — it has no form class (its only input is a `?month=` param) and instead splits five ways: `DashboardAggregationTests` (the §8.5 balance formulas against hand-built fixtures spanning multiple months and multiple users), `DashboardProjectionTests` (the FR15 forecast: fixed recurrence, installment spreading, rounding, running projected balance), `AccountEvolutionTests` (the FR16 12-month series), `ChartGeometryTests`, and the two view classes. See [apps/dashboard.md § Tests](apps/dashboard.md#tests-dashboardtestspy-66-tests) for the specific scenarios.

`core/tests.py` covers the FR20 currency registry, the FR19 number format, and the two production-safety settings guards.

- `CurrencyRegistryTests` checks the entries themselves (every currency fully populated, separators never identical, the four best-known ones matching their conventional format, an unknown code raising with the valid options listed).
- `ActiveCurrencyTests` asserts the *configured* currency, its derived `CURRENCY_SYMBOL`, and the active `DECIMAL_SEPARATOR`/`THOUSAND_SEPARATOR` all agree — the link `core/formats/en/formats.py` provides, which fails immediately if those separators are ever hardcoded again.
- `SecretKeyGuardTests` runs `manage.py check` **in a subprocess**, because the guard fires at settings *import* time and no `override_settings` can reach it. Four paths: unset key + `DEBUG=False` refuses to boot with an actionable message, a blank key does the same (Django boots happily on `''`, so blank must count as unset), a real key boots, and a fresh clone with no `.env` still runs in development.
- `HttpsSettingsTests` asserts all five TLS settings track the single `HTTPS` flag, that HSTS is exactly `0` without it (a stray HSTS header pins browsers to HTTPS for a year and is painful to undo), and that `SECURE_PROXY_SSL_HEADER` is only trusted when TLS termination is actually declared. These pass under **either** value, so `HTTPS=True uv run python manage.py test core` verifies the other branch.

> **Run the suite with `HTTPS` unset.** Scoping the TLS check to `core` above is deliberate: with `HTTPS=True`, `SECURE_SSL_REDIRECT` makes Django's test client — which issues plain HTTP requests — receive a `301` to `https://` on **every** view test, so most of the suite fails. That is the setting working exactly as intended, not a broken test. Verify the flag with `manage.py check --deploy` (clean under `HTTPS=True`) and with `core`'s own tests; run everything else with the flag off.

**The suite is currency-agnostic on purpose.** Display assertions derive their expected string from `settings.CURRENCY` via `django.utils.formats.number_format` rather than hardcoding `R$ 1.000,00`, so the whole switch can be verified end-to-end:

```bash
CURRENCY=USD uv run python manage.py test
```

The full suite passes under `BRL`, `USD`, `EUR` and `CHF`.

`ChartGeometryTests` and the two currency classes are the only ones that touch no database at all — `dashboard/charts.py` is pure arithmetic, so its tests assert directly on coordinates (a bigger value must produce a *smaller* SVG `y`, bars in a group must not overlap, an all-zero series must not divide by zero). It still subclasses `TestCase` rather than `SimpleTestCase`, purely so the file stays uniform; the currency classes use `SimpleTestCase`, which needs no database at all.

## Recurring assertions across every app

A handful of patterns repeat by design, because they encode the project's non-negotiable rules (PRD R3, FR12) rather than incidental behavior:

1. **Auth required** — every list/create/update/delete view redirects or `302`s an anonymous request.
2. **Per-user isolation** — a second user's fixture object is created in `setUp()` specifically so tests can assert it never appears in the first user's list, and that operating on its `pk` as the first user returns `404`.
3. **`PROTECT` integrity** (categories, payments only) — a `Transaction` referencing the object under test is created, then deletion is attempted, asserting both the raw `ProtectedError` (model-level test) and the friendly redirect-with-message UX (view-level test).

If you add a new field, view, or model, the existing test classes in the same app are the template to extend — every app already has a `ModelTests`/`ViewTests`/`FormTests` class shaped this way.
