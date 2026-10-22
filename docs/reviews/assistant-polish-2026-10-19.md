# Assistant visual refinements — 2026-10-19

## Scope

This increment refines the existing, uncommitted
[conversation layout](assistant-chat-ux-2026-10-19.md) after `0235eae` on
`feat/tuxedo-assistant-foundation`. The owner approved changes to the header,
empty state and message composer, retaining the logo, animation, 44px targets
and current behavior. Earlier working changes remain present.

The attached CSS report was treated as design input. Its proposed 24–34px
activation areas were adapted to the existing accessibility contract; no
renderer, prompt suggestions or provider changes were added.

## Delivered presentation

- Header and conversation actions share a continuous surface with one Context
  boundary. The Context badge is visually compact inside its 44px native link.
- The empty-state bow tie and heading are centered. Less inner transcript
  padding lets that block fit a narrow 320×480 window. The decorative bow tie
  changes independently of the approved animated cat/orbit artwork.
- The composer frame supplies its own border and a theme-aware focus halo,
  without another horizontal rule above it. Model and native consent controls
  align vertically, with restrained hover/focus feedback.
- Send and Stop retain stationary 44px buttons. Background clipping provides a
  34px visual face without shrinking the target or its focus outline. The
  message editor also retains a 44px minimum; constrained-height sheets use a
  44px cap, superseding the previous increment's 40px editor cap.

The existing 28px cat, 48px orbit, 60px launcher, 4-second/12-second motion,
reduced-motion handling, panel position and outer shadow are preserved.
Model selection, explicit per-message context consent, keyboard submission,
streaming, cancellation, references, private history and native forms retain
their existing contracts.

## Validation and boundaries

Automated checks use disposable data and the repository npm browser runner.
The streaming fixture blocks external transports; no test uses a linked account,
the installation database or a live model. The owning current contracts are the
[navigation guide](../frontend/navigation.md#assistant-panel),
[assistant guide](../apps/assistant.md) and [interface map](../interface-map.md).

| Check | Result for this refinement |
|---|---|
| Assistant Django suite | 187 passed with isolated settings/data. |
| Guarded chat and streaming browser cases | 19 passed, including both themes, narrow screens, native submission, invalid POSTs, keyboard consent and retained financial drafts. |
| Standard assistant and Design Lab browser cases | 28 passed, including history/privacy, native fallback, touch and artwork/reduced-motion checks. Together, 47 scoped browser cases passed against the final unchanged assets. |
| JavaScript unit checks | 16 passed. |
| Configuration/schema | Django system check clean; no missing migrations. |
| Assets/documentation | CSS rebuilt; JavaScript syntax, local documentation links and diff whitespace checks passed. No new translated strings were introduced. |

Browser commands:

```bash
npm run test:e2e -- --assistant-fixtures tests/e2e/assistant/chat-ux.spec.js tests/e2e/assistant/streaming.spec.js
npm run test:e2e -- tests/e2e/assistant/local-chat.spec.js tests/e2e/catalogue/assistant.spec.js
```

The local rendered preview was opened in a new authenticated browser tab beside
an empty transaction form. Opening the assistant and focusing its empty message
field used no financial POST, message send or model generation. No changes to
the environment file, schema, provider gates or financial records were needed.

Before/after captures and test logs remain ignored under
`.local/runtime/assistant-polish-20261019/`. They include both themes, desktop
and phone layouts, empty and populated conversations, native controls, invalid
responses and small-height editing states. Before captures were retained from
the preceding unchanged layout; current after captures and source hashes belong
to this refinement. Rendered inspection found no control collisions, preserved
native consent/error focus, and confirmed native Send above the mobile dock.

Phone checks use Chromium viewport/touch emulation and constrained-height
simulation; an operating-system keyboard on a physical handset was not tested.
The complete application browser inventory was not rerun for this scoped
presentation change. No commit, publication, release or paid API use is included.
