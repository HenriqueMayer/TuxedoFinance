# Coverage baseline

The Django suite uses branch coverage. Repository-tool and browser suites run
separately. Current results belong to the exact revision's CI run or pull
request; earlier test counts do not certify the present checkout.

## Policy

CI enforces a repository-wide **70% combined line and branch coverage** floor
through `coverage run --branch` and `coverage report --fail-under=70`.
When branch measurement is enabled, Coverage.py includes both executed
statements and branch destinations in the reported total. There is no separate
line-only or branch-only gate. See the
[Coverage.py explanation](https://coverage.readthedocs.io/en/latest/branch.html#how-to-measure-branch-coverage).

The configured measurement includes executed test modules and migrations; its
total must not be interpreted as application-only coverage. New financial
workflows need focused behavior and isolation tests, regardless of the score.

## Commands and artifacts

Use the isolated [Python check workflow](../CONTRIBUTING.md#python-checks) to
collect coverage. After that run, optional machine-readable and HTML reports are:

```bash
uv run coverage xml
uv run coverage html
```

An optional application-only diagnostic must omit complete test packages,
including support fixtures:

```bash
uv run coverage report --omit='*/tests/*,*/migrations/*,manage.py'
```

This is a diagnostic view; the CI scope and combined-coverage floor above
remain unchanged.

CI uploads these reports when their steps complete. Configuration in
`pyproject.toml` writes data to `.local/coverage/.coverage`, XML to
`.local/coverage/coverage.xml`, and HTML to `.local/coverage/html/`. These are
ignored local outputs and must not be committed. Earlier root artifacts are
preserved; the new paths do not authorize their deletion. A successful
local report does not establish that remote CI ran or passed.
