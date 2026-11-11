# Instructions for coding agents

Read [docs/architecture.md](docs/architecture.md) and
[docs/development.md](docs/development.md) first. They are the contract.

## Layout

`backend/` Django API and domain. `web/` React client. `site/` public page
with the demonstration. `docs/` current reference.

## Commands

| Where | Command |
|---|---|
| `backend/` | `SECRET_KEY=dev uv run python manage.py test` |
| `backend/` | `uv run ruff check . && uv run ruff format --check .` |
| `web/` | `npm run lint && npm run typecheck && npm test` |
| `web/` | `npx vite build && npm run journeys` |
| `web/` | `npm run api:types` after any change of the API |
| `site/` | `npm run build && npm test` after a change of `site/`, of `web/src/demo/` or of `backend/reports/demo.py` |

## Rules

- One session writes. A helper agent only reads and reports.
- Investigate before asking. Reuse decisions that are already made.
- Write the failing test first. Run the checks of the folder that changed, and
  read the exit status, not only the last line of the output.
- Financial rules live in models and services. An API operation calls them.
  The client does not calculate money.
- Every operation checks the session and the owner. Add both tests with a new
  operation.
- Interface text needs English and Brazilian Portuguese (`web/src/i18n/`).
- A new object opens in the window (`web/src/ui/Window.tsx`). Do not add a
  second pattern. Read `web/DESIGN.md` before a visual change.
- For interface work, look at the rendered screen on a desktop and on a phone,
  in both themes, before reporting it as done. Say what was not checked.
- Update the documentation file of the subject in the same change. Do not add
  dated reviews, plans or process notes to the repository.
- Never use or change an installation database, `.env` file or backup.
- Do not commit, push, merge or publish without an explicit request.
