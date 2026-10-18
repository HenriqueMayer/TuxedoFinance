# Frontend and documentation organization — 2026-10-18

This fourth organization lot is based on `893e5fc`. It separates frontend
sources and technical guidance by responsibility while retaining the approved
design, interaction contracts, financial behavior and installation data. The
[Python lot](python-organization-2026-10-18.md) and earlier
[tooling/browser lot](repository-organization-2026-10-18.md) remain separate
deliveries.

## Source ownership

`assets/css/tailwind.css` is now a 49-line ordered build entry instead of a
753-line mixture. Ten source modules separate shared primitives and consultation
rails from category, banking, transaction and investment/planning presentation.
The [style-source index](../../assets/README.md) identifies all owners and explains
the intentionally ordered late states. Existing imports, layers and the
font-face URL retain their positions and meaning; rules were not regrouped
across cascade boundaries.

Four Django editors now include their interaction blocks from owning partials:
`transactions/_form_script.html`, `investments/_form_script.html`,
`investments/_setup_form_script.html` and
`banking/_loyalty_form_script.html`. These remain Django-rendered scripts so
translated messages, prefixed identifiers and bound context keep their original
meaning. Includes execute at the original points and retain the same context.
No client configuration adapter, new JavaScript loader or additional runtime
request was introduced.

The existing shared JavaScript files and catalogue assets already have coherent
responsibilities. Their paths, bytes, APIs and load order remain unchanged. The
browser still loads one compiled application stylesheet. This delivery adds no
framework, bundler or dependency.

## Documentation ownership

The [frontend index](../frontend.md) links eight canonical guides: runtime,
presentation, forms, catalogue, navigation, charts, consultation and workspace
composition. It replaces the 1,496-line combined guide with a short entry point
and preserves all 31 previous heading/explicit anchors, including its original
title anchor. Existing links in historical reports remain usable; current
contributor, agent, app and interface references point to the owning guides.

The extraction retains 36 source blocks and 174 source paragraphs. Changes to
the extracted material are limited to relative/canonical link destinations,
heading hierarchy, the moved help-style owner and notes identifying the new
CSS/script owners. No form, help, history, chart or accessibility contract was
dropped. Existing cohesive app, operations and product guides remain in place.

`uv run python scripts/check_docs.py` now checks repository-local Markdown/HTML
paths and anchors, including new source guides and the Design Lab. It excludes
ignored runtime artifacts through Git's source inventory and performs no network
requests. Fenced and inline examples do not create fake links or anchors. Eight
tooling cases exercise missing targets, section aliases, duplicate/Unicode
headings, reference links, examples, outside paths and CLI source discovery.
CI runs the same check; this is a local-source check, not external URL validation.

## Preservation evidence

- Expanding the ten new CSS imports in their original positions preserves the
  prior rules and ordering. The final PostCSS/Tailwind build is byte-identical to the
  committed stylesheet: 172,772 bytes.
- Replacing each new script include with its literal body reconstructs the four
  original templates byte for byte. Eight templates compile; 14 comparisons of
  the extracted `extra_js` blocks match in English and Brazilian Portuguese,
  including inactive branches and prefixed identifiers above 999. These are
  block comparisons, not fourteen complete-page renders.
- All 367 recorded existing Python/static/translation sources retain their
  starting hashes. Application services, models, migration history and URLs are
  unchanged. Compiling the unchanged translation catalogue produces the same
  committed binary.
- Installation environment, database, backup and dependency paths were preserved.
  The committed public tour was not regenerated or changed.

## Validation

Checks use local synthetic/disposable data and the official browser runner.
Generated reports stay under `.local/coverage/` and
`.local/test-results/frontend-organization/`; extraction evidence was inspected
locally rather than added as a runtime dependency.

| Check | Observed result |
|---|---|
| Version consistency, Django system check and migration check | Passed; no pending model changes. |
| Full Django suite | 723 tests passed in one complete traversal. |
| Combined line/branch coverage | 95% with the existing measurement scope including executed tests/migrations and the unchanged 70% floor. |
| Python repository-tool suite | 40 passed, including eight documentation-check cases. |
| JavaScript amount/allocation suite | 16 passed. |
| Focused application/catalogue browser suite | 49 passed in one selected traversal, with no failures or skips. |
| Documentation paths and anchors | Passed with zero unresolved local references. All 31 prior frontend anchors remain available. |
| Compiled assets | Byte-identical CSS and translation binary. |
| Lock consistency, focused Ruff rules and whitespace | Passed. |

The browser selection exercised loyalty miniatures and native purchases,
catalogue geometry and mobile overflow, investment setup/operation recovery,
shared keyboard and conditional form contracts, Portuguese phone forms and
exact category-allocation behavior. It used Chromium desktop/phone viewports,
both themes, HTMX recovery and no-JavaScript submissions. It is a targeted
selection from the existing suite, not a full browser-inventory run.

## Limits

This lot does not claim performance improvements or add product behavior. The
complete application browser inventory, physical mobile devices, other browser
engines, real Docker execution, vulnerability audits, remote CI and publication
checks are not part of this validation. The unchanged public static-tour suite
was not repeated. No merge, release or publication is part of this delivery.
