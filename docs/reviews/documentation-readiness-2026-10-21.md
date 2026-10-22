# Documentation and roadmap alignment — 2026-10-21

## Scope

Review public documentation against the current source after the Analytics,
Investments, Plan, Accounts and shared compact-density work. Preserve the
existing working tree, installation data and publication hold. Current behavior
belongs to the [requirements](../product-requirements.md),
[interface map](../interface-map.md) and [app guides](../README.md#per-app-reference).

## Changes

- Align both READMEs with the six workspaces, invoice credits, position emojis,
  local prices, planning and optional assistant. Distinguish the current source
  from the published v0.10.0 Docker quick start without changing its version.
- Correct stale investment identity and assistant-consultation descriptions.
  Keep bounded consultations and canonical simulations distinct from the six
  implemented actions that require reviewed confirmation. Keep authorization
  and inference default-off, with no paid fallback or application web/news tool.
- Update the requirements and owner walkthrough for current tabs, account
  presentation, credits, emojis and the shared compact summaries. Preserve
  functional requirement identifiers, existing anchors and unchecked owner
  acceptance. The documentation index links to the current capability inventory.
- Align the bilingual static preview metadata, investment copy and alternative
  text with the existing synthetic captures. Increment its stylesheet cache key;
  the 32 captures from the preceding layout batch were retained.
- Shorten the roadmap from 154 to 107 lines, removing delivered-work narration.
  Retain validation/release acceptance, paused interfaces, provider extensions,
  external evidence and Open Finance research. Real Inter pilot setup remains
  paused; its daily exception does not replace the broader 6–8-hour target.

## Validation

- `uv run python scripts/check_docs.py`: no unresolved local references.
- `uv run python scripts/check_version.py`: version 0.10.0 remains consistent.
- Isolated `manage.py check`: no issues. All 10 documentation/version tooling
  tests passed with a disposable data directory, no installation environment
  file and real assistant providers disabled.
- `npm run test:preview`: all 21 cases passed, covering EN/PT-BR, light/dark,
  desktop and 320/390px layouts, keyboard/lightbox recovery and native navigation.
  Current Portuguese desktop/phone preview screenshots were visually inspected
  in both themes. The preview remains a static synthetic tour.
- All pre-task anchors in the ten edited documentation/preview files and all
  existing functional requirement identifiers were retained. Other snapshotted
  working files were byte-identical before adding this review and its index.
- `git diff --check` passed.

## Boundaries and evidence

This batch changes documentation and static-preview text only. It does not
repeat the full application/browser or Docker suite and does not establish owner
acceptance or release readiness. Existing dated reviews retain their own scopes.
No model request, bank connection, migration, import or installation-data change
was performed. No commit, push or publication was performed.

The pre-task snapshot and validation logs remain under
`.local/documentation-readiness-2026-10-21/`; current static-preview screenshots
remain under `.local/test-results/preview/`.
