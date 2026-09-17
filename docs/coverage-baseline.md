# Coverage baseline

The Django suite is measured with branch coverage. The FIN-8 local verification
on **2026-09-05 (UTC)** passed **196 Django tests** with **89% combined coverage**
using the existing CI measurement scope. This is a dated measurement, not a
promise that the test count remains fixed. Repository-tool tests and browser
suites run separately and are not included in that count.

## Policy

CI enforces a repository-wide **70% combined line and branch coverage** floor
through `coverage run --branch` and `coverage report --fail-under=70`.
When branch measurement is enabled, Coverage.py includes both executed
statements and branch destinations in the reported total. There is no separate
line-only or branch-only gate. See the
[Coverage.py explanation](https://coverage.readthedocs.io/en/latest/branch.html#how-to-measure-branch-coverage).

The existing measurement includes executed test modules and migrations; the
89% total must not be interpreted as application-only coverage. This maintenance
change retains that measurement scope and threshold. New financial workflows
still need focused behavior and isolation tests, regardless of the overall score.

## Commands and artifacts

Use the isolated [Python check workflow](../CONTRIBUTING.md#python-checks) to
collect coverage. After that run, optional machine-readable and HTML reports are:

```bash
uv run coverage xml
uv run coverage html
```

CI uploads these reports when their steps complete. `.coverage`, `coverage.xml`,
and `htmlcov/` are ignored local outputs and must not be committed. A successful
local report does not establish that remote CI ran or passed.
