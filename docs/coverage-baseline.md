# Coverage baseline

The Django suite is measured with branch coverage. The FIN-8 local verification
on **2026-09-05 (UTC)** passed **196 Django tests** with **89% combined coverage**
using the existing CI measurement scope. This is a dated measurement, not a
promise that the test count remains fixed. Repository-tool tests and browser
suites run separately and are not included in that count.

The **2026-10-16** maintenance verification passed **624 Django tests** with
**94% combined coverage** under the same measurement policy. A diagnostic report
excluding executed test modules, migrations and `manage.py` showed **90%** for
the remaining executed application code. This is a separate view of the same
run, not a new gate or a promise about unexecuted tooling:

```bash
uv run coverage report --omit='*/test_*.py,*/tests.py,*/migrations/*,manage.py'
```

See the [project health review](reviews/project-health-2026-10-16.md) for the
financial/history regression scope and isolated performance observations.

The **2026-10-18** repository-organization verification passed **723 Django
tests** with **95% combined coverage** under the existing measurement scope.
See the [dated organization review](reviews/repository-organization-2026-10-18.md)
for isolation, test-inventory reconciliation and remaining validation limits.
The subsequent [Python organization lot](reviews/python-organization-2026-10-18.md)
retained the same 723-case inventory and measured 95% with that policy after
moving tests into app-owned packages.

## Policy

CI enforces a repository-wide **70% combined line and branch coverage** floor
through `coverage run --branch` and `coverage report --fail-under=70`.
When branch measurement is enabled, Coverage.py includes both executed
statements and branch destinations in the reported total. There is no separate
line-only or branch-only gate. See the
[Coverage.py explanation](https://coverage.readthedocs.io/en/latest/branch.html#how-to-measure-branch-coverage).

The configured measurement includes executed test modules and migrations; the
dated 89%, 94% and 95% totals must not be interpreted as application-only coverage.
The maintenance measurement retained that scope and threshold. New financial workflows
still need focused behavior and isolation tests, regardless of the overall score.

## Commands and artifacts

Use the isolated [Python check workflow](../CONTRIBUTING.md#python-checks) to
collect coverage. After that run, optional machine-readable and HTML reports are:

```bash
uv run coverage xml
uv run coverage html
```

After Python tests moved into app-owned packages, an optional application-only
diagnostic must omit the complete test packages, including support fixtures:

```bash
uv run coverage report --omit='*/tests/*,*/migrations/*,manage.py'
```

This remains a diagnostic view; the CI scope and combined-coverage floor above
are unchanged. The earlier omission command belongs to the dated flat-layout
measurement.

CI uploads these reports when their steps complete. Configuration in
`pyproject.toml` writes data to `.local/coverage/.coverage`, XML to
`.local/coverage/coverage.xml`, and HTML to `.local/coverage/html/`. These are
ignored local outputs and must not be committed. Earlier root artifacts are
preserved; the new paths do not authorize their deletion. A successful
local report does not establish that remote CI ran or passed.
