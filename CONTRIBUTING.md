# Contributing to CashFlow

Thank you for improving CashFlow. By submitting a contribution, you agree that
it is provided under the repository's [PolyForm Noncommercial License](LICENSE)
and that copies and modified distributions preserve the required copyright and
license notices.

## Before opening a change

- Keep CashFlow a small, self-hosted personal-finance application; do not add
  SaaS-scale infrastructure or unsupported deployment packaging.
- Preserve user isolation, Decimal-based financial calculations, accessibility
  and no-JavaScript fallbacks.
- Update README, PRD, data model and affected app documentation with code.
- Add or update English and Brazilian Portuguese interface strings together.
- Run `manage.py check`, `makemigrations --check --dry-run`, tests and
  `compilemessages` before proposing a change.

## License notices

Do not remove or weaken the copyright or license notices in this repository.
Where practical, new distributable source files should include the concise
identifier `SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0`.
