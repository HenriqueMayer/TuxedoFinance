# Contributing

Read [Development](docs/development.md) for setup and commands, and
[Architecture](docs/architecture.md) before adding an operation or a screen.

## A change

1. Write the test that proves the behavior. See it fail.
2. Make the change in the folder that owns it (`backend/` or `web/`).
3. Run the checks of that folder. They are listed in
   [Development](docs/development.md#checks).
4. Update the documentation file of the subject in the same change.
5. Add a line to the `Unreleased` section of the [changelog](CHANGELOG.md)
   when the owner of an installation can notice the change.

## What a pull request runs

`backend.yml` runs for a change in `backend/`. `web.yml` runs for a change in
`web/` or `backend/`, because the client depends on the API schema and the
journeys use the real backend. A change of documentation alone runs neither.

## Rules that the checks cannot enforce

- Financial rules live in models and services, never in `api.py` or in the
  client.
- The client does not calculate money.
- Test data is fictional. Never use an installation database in a test.
- Interface text has English and Brazilian Portuguese.
