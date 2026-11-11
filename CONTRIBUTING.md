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

| Workflow | Runs | Jobs |
|---|---|---|
| `ci.yml` | For every pull request | The backend checks, the client checks and the browser journeys, then `Application and tooling checks`, which passes when the three passed |
| `docker.yml` | For every pull request | `Validate Linux amd64` and `Validate Linux arm64`: each builds the image and starts it |
| `pages.yml` | For a change in `site/`, `web/` or `backend/` | It builds and checks the public site, and does not publish it |

The rule of the branches `main` and `develop` requires three checks by their
names: `Application and tooling checks`, `Validate Linux amd64` and
`Validate Linux arm64`. Do not rename these jobs, and do not add a path
filter to their workflows: a required check that does not run blocks the
merge.

## Rules that the checks cannot enforce

- Financial rules live in models and services, never in `api.py` or in the
  client.
- The client does not calculate money.
- Test data is fictional. Never use an installation database in a test.
- Interface text has English and Brazilian Portuguese.
