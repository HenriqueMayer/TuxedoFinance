# Development

## Requirements

Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node.js 22 with npm.
`gettext` is needed only to compile translations.

## First run

```bash
cd backend
cp .env.example .env        # then set SECRET_KEY in .env
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

In a second terminal:

```bash
cd web
npm ci
npm run dev
```

Open http://localhost:5173. The client sends `/api` to the backend on port
8000.

To run it as one server, build the client (`npx vite build` in `web/`) and
open http://127.0.0.1:8000.

## Checks

Run the checks of the folder that you changed.

| Folder | Command | Checks |
|---|---|---|
| `backend/` | `uv run ruff check . && uv run ruff format --check .` | Lint and format |
| `backend/` | `uv run python manage.py test` | Domain and API tests |
| `backend/` | `uv run python manage.py check && uv run python manage.py makemigrations --check --dry-run` | The Django system check, and no missing migration |
| `web/` | `npm run lint && npm run typecheck && npm test` | Lint, types, unit tests |
| `web/` | `npx vite build && npm run journeys` | Browser journeys |
| `site/` | `npm run build && npm test` | The public site and its demonstration, from static files |

`npm run format` in `web/` writes the format that `npm run lint` checks.

The journeys and the site checks need a browser of Playwright once:
`npx playwright install chromium`, in `web/` and in `site/`.

CI runs the same commands on a clean checkout, and three more checks of the
backend: the tests with branch coverage (`coverage run manage.py test`, then
`coverage report --fail-under=84`), and the compiled translations, which must
equal the tracked `django.mo`.

Backend commands need `SECRET_KEY`. Without a `.env` file, set it for the
command: `SECRET_KEY=dev uv run python manage.py test`.

The journeys start their own backend on port 8765 with a temporary data
directory. They never use an installation database.

## After a change of the API

```bash
cd web
npm run api:types
```

This writes `src/api/schema.json` and `src/api/schema.d.ts`. Commit both. CI
fails when they differ from the backend.

## Translations

Interface text is in `web/src/i18n/`. `en.ts` defines the keys and
`pt-BR.ts` must have the same ones; the type check enforces it.

Messages of the backend (validation) are in
`backend/locale/pt_BR/LC_MESSAGES/django.po`. After a new or changed
message, update the file, translate the new entries, and compile:

```bash
cd backend
uv run python manage.py makemessages -l pt_BR --ignore=.venv --ignore=var --no-obsolete --no-location
uv run python manage.py compilemessages --ignore=.venv
```

Commit `django.po` and `django.mo`. An entry marked `fuzzy` is not used:
translate it and remove the mark.

## Conventions

- Code and documentation are in English. Interface text has English and
  Brazilian Portuguese.
- A test is written before the behavior that it proves, and it must fail
  first.
- A comment states a reason or a rule that the code cannot show.
- Read [Architecture](architecture.md) before adding an operation or a screen.
