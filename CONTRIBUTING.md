# Contributing

Read [Development](docs/development.md) for setup and commands, and
[Architecture](docs/architecture.md) before adding an operation or a screen.

## A change

1. Write the test that proves the behavior. See it fail.
2. Make the change in the folder that owns it (`backend/`, `web/` or `site/`).
3. Run the checks of that folder. They are listed in
   [Development](docs/development.md#checks).
4. Update the documentation file of the subject in the same change.
5. Add a line to the `Unreleased` section of the [changelog](CHANGELOG.md)
   when the owner of an installation can notice the change.

## What a pull request runs

| Workflow | Runs for a change in |
|---|---|
| `backend.yml` | `backend/` |
| `web.yml` | `web/` or `backend/`: the client depends on the API schema, and the journeys use the real backend |
| `docker.yml` | `backend/`, `web/`, `Dockerfile` or `.dockerignore`: it builds the image and starts it |
| `pages.yml` | `site/`, `web/` or `backend/`: it builds and checks the public site, and does not publish it |

A change of documentation alone runs none of them.

## Rules that the checks cannot enforce

- Financial rules live in models and services, never in `api.py` or in the
  client.
- The client does not calculate money.
- Test data is fictional. Never use an installation database in a test.
- Interface text has English and Brazilian Portuguese.
