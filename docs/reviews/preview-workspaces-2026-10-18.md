# Workspace preview refinement — 2026-10-18

This intermediate iteration is historical. The later
[direct preview refinement](preview-simple-2026-10-18.md) removes its demo and
large introduction while retaining the workspace navigation and themed images.

## Scope

This presentation-only follow-up starts from `653fb5a`. The earlier
[README refresh](readme-preview-2026-10-18.md) retains its original evidence.
The application, financial calculations, installation data and version remain
unchanged.

Both READMEs replace the slogan with factual, informal copy, remove the large
static Home image and retain the prominent preview link and Docker/native quick
starts. A native disclosure contains a localized short GIF, keeping the main
page compact. All 17 existing heading/compatibility anchors in each edition
remain available; English and Portuguese shell commands are identical.

The static tour now uses the approved five-workspace sidebar and phone dock,
with Reports under Home. It retains native hash links and Back/Forward, carries
workspace context across language changes, and shows all sections without
JavaScript. The skip link moves focus into the current workspace. Theme changes
select genuine corresponding captures. Lightbox dismissal restores visible
focus, including after history changes replace its owner. Public copy uses no
technical-warning banner; the footer identifies demonstration data.

The bow tie, locally bundled Inter/OFL, forest/cream/caramel palette, neutral
dark surfaces and restrained actions follow the application's visual concept.
Thumbnails crop the captured application frame through CSS to avoid duplicate
navigation, while original images and lightbox keep the full 1440 × 1000 view.
The tour demonstrates screenshots; financial controls inside them do not submit.

## Captures and demonstrations

The isolated capture workflow generates 24 images: six areas, two themes and
two languages. It retains temporary storage, ephemeral credentials, all-image
staging, owned loopback endpoints, installation-database fingerprint checks and
cleanup on failure. Only synthetic balances are captured. Synthetic account and
investment openings have explicit dates, avoiding an irrelevant legacy-date
warning in public Plan captures without suppressing real application warnings.

Each localized GIF shows actual preview navigation: Home/bow-tie layers,
Transactions, Accounts, Plan, dark theme and Home. The recordings use real
pointer events within a single document. Cirro validates and renders the footage;
FFmpeg only converts the final format. Final GIFs use 900 × 563 pixels, 10 fps,
about 12 seconds and approximately 2 MB each. Raw recordings, event logs,
screenplays, WebM renders and review frames remain ignored under
`.local/test-results/preview-redesign/demo/`.

## Validation and limits

| Check | Observed result |
|---|---|
| Real isolated capture workflow | All 24 images staged and replaced; installation-database fingerprint guard passed |
| Static-preview browser suite | 17 tests passed in 37.2 seconds; both languages/themes, desktop/phone, keyboard, history, language context, lightbox, sandboxed links and native file/no-JavaScript access |
| Python repository tooling | 40 tests passed, including capture isolation/staging/cleanup cases |
| README review | Eight local CommonMark renders: EN/PT, 1440/390 pixels, light/dark; no horizontal overflow, native demo disclosure, localized GIF decoding and real Enter activation of the preview link |
| Final demos | Cirro validation/render/playback inspection passed; EN 12.4s/124 frames/2,083,679 bytes, PT 12.6s/126 frames/2,089,792 bytes; both decoded at 900 × 563, 10 fps, with recorded SHA-256 checks |
| Quick starts and previous anchors | Matching EN/PT commands, valid shell syntax, all 34 previous anchors retained |
| Django system/migration checks | No system issues or model changes |
| Version consistency and Python undefined-name lint | Passed; version remains 0.10.0 |
| Data/source preservation | All 531 protected application/template/asset/translation hashes unchanged; five installation paths retained their identities |
| Documentation and whitespace | 58 documents, 513 local references, no unresolved links; `git diff --check` passed |

The README review uses a GitHub-like local layout, with remote badges and preview
destinations stubbed. It does not certify GitHub's renderer, badge status or the
currently published preview. Desktop and phone preview layouts, original images
and recorded demo frames were inspected in both themes.

The complete application/Django and financial browser suites were not rerun for
this presentation-only change. No Docker container, upgrade rehearsal,
publication, merge, release or version increment is part of this follow-up.
Current maintenance instructions live in the [preview guide](../preview.md).

Logs, local CommonMark renders, preservation snapshots and browser screenshots
remain under ignored `.local/test-results/preview-redesign/` and
`.local/test-results/preview/`. During development, the embedded-tour fixture was
given a realistic height instead of HTML's 150px default, and the skip-link test
was corrected to account for native fragment-navigation focus. The final full
preview run above passed after those corrections.
