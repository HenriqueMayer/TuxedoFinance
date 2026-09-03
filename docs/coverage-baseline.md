# Coverage baseline

The stabilized suite is measured in CI with branch coverage. On 2026-09-03 the
complete Django suite passed with 186 tests and 89% total coverage. CI publishes
`coverage.xml` and an HTML report as build artifacts for every push and pull
request.

The policy is a modest 70% minimum line-coverage floor (`--fail-under=70`).
Branch coverage is reported to expose untested financial-service decisions, but
it is not a separate gate. The floor is intentionally repository-wide rather
than a per-module promise; new financial workflows should still add focused
tests and keep their affected-tests list in the change description. Tests,
Django checks, migration checks, translation validation, lint, and the locked
dependency audit remain hard CI gates.

Run the same report locally with:

```bash
uv run coverage run --branch manage.py test
uv run coverage report --show-missing --fail-under=70
uv run coverage xml
uv run coverage html
```

The generated `.coverage`, `coverage.xml`, and `htmlcov/` files are local build
outputs and must not be committed.
