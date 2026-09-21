# Versioning and releases

Tuxedo Finance uses [Semantic Versioning](https://semver.org/) with versions in
the form `MAJOR.MINOR.PATCH`:

- `MAJOR` changes when an upgrade is intentionally incompatible.
- `MINOR` changes when backward-compatible functionality is added.
- `PATCH` changes when backward-compatible defects or security issues are fixed.

Before `1.0.0`, a minor version may include an announced compatibility break.
Any such change must be called out in the changelog and in the release notes.

## Source of truth

The canonical application version is `[project].version` in the root
[`pyproject.toml`](../pyproject.toml). The corresponding project entry in
`uv.lock`, both README version badges and the changelog are validated against it
by `scripts/check_version.py`.

`package.json` is a private manifest for Tailwind and Playwright development
tools. It does not carry a second application version.

Release tags use the same version prefixed with `v`, for example `v0.3.0`.

## Preparing a release

1. Choose the next version from the changes accumulated in `main` and prepare
   the release changes on a branch based on the current `main`.
2. Update `[project].version` in `pyproject.toml`.
3. Run `uv lock` so the editable project entry in `uv.lock` matches.
4. Move the relevant entries from `Unreleased` to a dated version section in
   [`CHANGELOG.md`](../CHANGELOG.md).
5. Run `uv run python scripts/check_version.py` and the complete
   [development checks](../CONTRIBUTING.md), including isolated browser tests
   and static-preview tests. Verify equivalent content and version badges in
   both READMEs before preparing the release.

6. Open the release pull request to `main` and wait for CI.
7. After the release commit is on `main`, create and push the annotated tag:

   ```bash
   git switch main
   git pull --ff-only origin main
   version=$(uv run python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')
   git tag -a "v$version" -m "Tuxedo Finance v$version"
   git push origin "v$version"
   ```

8. Create the GitHub release from that tag using the matching changelog section.

Feature branches target `main` directly. They normally add notes under
`Unreleased` but do not create tags themselves. There is no intermediate
integration branch.

## Maintaining the changelog

Add a concise `Unreleased` entry when a change is notable to users, operators,
or contributors. Use the Keep a Changelog headings `Added`, `Changed`,
`Deprecated`, `Removed`, `Fixed`, and `Security` as needed. Do not create a new
version section on a feature branch, and do not rewrite a published version.

Implementation-only refactors, wording corrections, and CI maintenance normally
do not need separate entries unless they change supported behavior or close a
meaningful security risk. At release time, move the accumulated entries into a
dated version section, update the comparison links at the bottom of
`CHANGELOG.md`, and use that same section as the GitHub release notes.

## Automated guarantees

CI validates every pull request and pushes to `main`. It also runs
for `v*` tags; tagged builds fail when the tag differs from `pyproject.toml` or
when the matching dated changelog section is missing. This prevents publishing
two different versions under the same release identity.

## Container releases

Docker distribution starts with v0.3.0; v0.2.0 has no published container.
Feature branches add `Unreleased` entries; do not tag an existing version again
to distribute new code.

On a published stable GitHub Release, `.github/workflows/docker.yml` checks out
its tag, validates its version and membership in main, and builds/tests amd64
and arm64 on native runners. It publishes those exact tested images to GHCR,
then assembles the version manifest and attaches `compose.yaml` and
`docker.env.example` to the release. OCI labels record version and source
revision. Pull requests validate images without publishing. Prereleases are
validated but not published by this workflow.

Supported image references are `ghcr.io/henriquemayer/tuxedofinance:vX.Y.Z` or a
recorded digest. No moving `latest` tag is maintained, so publishing an older
release cannot silently change an installation's selected version.

Before the first release, enable GitHub Actions and package creation for the
repository. The publishing job uses its GITHUB_TOKEN with package-write and
release-asset-write permissions. Ensure the GHCR package is public (package
settings -> visibility) and inherits the repository's Actions access. The
workflow explicitly verifies anonymous pulls of both architectures; a private
package causes that step to fail. Correct visibility/access and rerun the
failed publication before advertising the image.

For the first release, rehearse the no-clone quick start from only its downloaded
assets on a clean installation. Verify anonymous pulling, signup, both languages,
assets, retained data after recreation, backup and restore. Link issue #18 to
the delivering PR and release only once this verification succeeds. A local
image build or merged packaging PR alone does not establish registry availability.
