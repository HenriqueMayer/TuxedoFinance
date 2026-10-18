# README and preview refresh — 2026-10-18

## Scope

This local presentation update starts from `9a427a3`. It changes the bilingual
repository introduction, the static tour and its disposable capture tooling.
Application behavior, financial calculations, personal records and release
identity remain unchanged.

The English README decreases from 266 to 122 lines and Portuguese from 269 to
125, including compatibility anchors. Both now share a native SVG cover based on
the homepage's ledger-paper bow tie, concise introductory copy, three badges,
an emphasized caramel preview action, theme-aware Home imagery, five workspace
descriptions and links to owning
guides. Their commands, capabilities, release/check-out distinction and license
information are equivalent. All fourteen earlier heading anchors in each
edition remain available.

Both READMEs include a copyable published-image Docker quick start with matching
commands. Download links, explicit image selection, protected signing-key
creation, persistent storage and startup remain documented. The Docker guide
owns detailed installation/operation instructions without a circular link back
to the README.

The tour uses the current editorial visual language, factual copy and current
workspace names. Its six public section anchors, fourteen screenshot paths,
language/theme controls, native file access, external-tab behavior and lightbox
remain intact.

## Capture changes

All fourteen images were regenerated from an isolated installation with
fictional English/Portuguese profiles. The viewport is now 1440 × 1000 without
the former 80-pixel left crop, preserving the new sidebar. Accounts deliberately
opens one synthetic bank; Plan shows `/planning/` with explicit category limits
instead of its secondary yield simulator. Synthetic cards use the supported
appearance fields, and synthetic account opening dates are explicitly defined.

No production capture path was introduced. The existing isolated directory,
empty environment file, ephemeral credentials, owned loopback server, all-image
staging, database-preservation check and cleanup guards remain unchanged.

## Current validation

| Check | Observed result |
|---|---|
| Real capture workflow | Passed; all fourteen images staged and replaced successfully, with the installation database fingerprint preserved |
| Static-preview browser baseline, before the README-only follow-up | 14 passed in 16.7 seconds |
| Python repository tooling baseline, before the README-only follow-up | 40 passed |
| Local README rendering, repeated after the follow-up | Eight CommonMark renders: both languages, 1440/390 pixels and light/dark themes; local images, theme selection, preview-action bounds and keyboard destination passed |
| Docker quick-start blocks | English/Portuguese commands identical, shell syntax valid and matching the owning guide; no container was started |
| Earlier README anchors | All 28 retained |
| Documentation references | No unresolved local references |
| Version consistency | Passed; application/lockfile/README version remains 0.10.0 |
| Python undefined-name lint and whitespace | Passed |

The browser suite exercises real Tab/Enter/Escape actions, action bounds,
lightbox focus restoration, theme/language controls, image dimensions, mobile
overflow, local files without JavaScript and sandboxed external links. Desktop
and phone renders were visually inspected in both themes, together with the
new Accounts/Plan captures. The README review uses local CommonMark with a
GitHub-like layout; it does not certify GitHub's remote Markdown renderer or the
current remote CI badge.
The follow-up's preview destinations were stubbed during keyboard checks; those
checks verify the link and interaction, not the public site's availability.
Only documentation and its SVG action changed in that follow-up, so the static
tour and repository tooling baselines above were not rerun. Local README renders,
documentation/version checks and anchor preservation were repeated.

All 531 protected application/template/asset/translation source hashes remained
identical. Installation paths retained their recorded identities. Captures used
only temporary synthetic databases, and the wrapper's database fingerprint
guard passed. Raw logs, review renders and preservation evidence are ignored
under `.local/test-results/presentation-refresh/`; browser screenshots remain
under `.local/test-results/preview/`.

## Release boundary

This update does not change the version, publish Pages, create a release/tag or
validate a new container distribution. The current checkout and regenerated
images can include unreleased functionality; the READMEs distinguish them from
the published v0.10.0 image and tour.

The complete application/Django suites and upgrade/container rehearsals were
not repeated for this presentation-only update. Earlier application evidence,
including the two timing failures and passing focused rechecks, remains in the
[organization closeout](organization-closeout-2026-10-18.md).

A future 1.0 release should be an explicit stability milestone following the
[versioning workflow](../versioning.md), with its own compatibility, upgrade and
release validation. The amount of visual change alone does not require a major
increment.
