# Portfolio product presentation — 2026-10-22

## Scope and result

At the owner's request, the public preview now combines the earlier editorial
opening and ledger-paper bow tie with an interactive explanation of the current
application. Eight illustrative HTML/SVG views replace screenshot thumbnails as
the main product demonstration. The original captures and their public paths
remain available. The owning contract is [preview maintenance](../preview.md).

The six workspaces retain their existing navigation and secondary ownership.
The Transactions example has a keyboard-operable local search. The assistant
section offers prepared expense, spending-scenario and budget-review
conversations, with an explicitly illustrative confirmation step. All examples
use fictional records and fixed dates. They make no provider/account request
and save no financial record. The sole persisted preview preference is theme.
English and Brazilian Portuguese remain equivalent.

The existing local Inter font, forest/caramel colors, ledger bow tie and Tuxedo
mark form the visual direction. The opening restores hierarchy and whitespace;
HTML text, category bars, a labelled SVG cash chart and responsive layouts keep
the examples sharp at different sizes. Meaningful demo/chat text was enlarged
after visual review, especially source links and financial caveats on phones.

Native fragments preserve old links, Back/Forward and language context.
Keyboard workspace activation focuses its destination heading; pointer
activation keeps its link. History navigation recovers focus from replaced
views. The confirmation example focuses its visible result instead of leaving
focus on a hidden button. Without JavaScript, every workspace/conversation stays
readable and enhancement-only controls are hidden.

## Verification and boundaries

Visual review covered 1440px desktop and 390/320px phone layouts in light/dark
themes, including all eight workspaces and the assistant scenarios. Additional
browser renders cover both languages and the 768px intermediate layout.
Financial fixture totals and scenario changes were reconciled across the views
and chat. Rendered examples and their source/caveat text were inspected again
after the readability refinement.

The static browser suite covers keyboard Enter/Space, search/no-results/recovery,
focus restoration, history, language/theme context, compatible fragments,
unknown fragments, native local-file navigation without JavaScript, final action
bounds and sandboxed external links. The assistant checks also verify that
example selection/confirmation produce no request or browser-storage change.

`npm run test:preview` passed all 28 scenarios in 2.0 minutes. After the final
phone navigation refinement, the eight 390/320px cases passed again in 48.1
seconds with additional label-containment assertions. Icons now sit above the
full labels on phones, preserving readable text without overlap. The final
mobile artifacts remain in `.local/test-results/preview-mobile/`; these checks
did not replace the full-run evidence.

Isolated Django system checks reported no issues. Documentation validation
reported no unresolved local references; JavaScript syntax and
`git diff --check` passed. Browser and visual artifacts remain ignored under
`.local/test-results/preview/` and `.local/test-results/preview-portfolio/`.

This work changes only the presentation, its regression tests, brand-asset copy
and owning documentation. No application source, financial service, migration,
installation configuration, database or private assistant state was changed.
The full Django/application E2E suites, Docker, live inference and hosted Pages
were not exercised for the initial presentation-only handoff. At that handoff,
no commit, merge, release or publication had been performed.

## Workspace-scroll follow-up

The owner reported a small upward jump when selecting a workspace inside the
demonstration. A real click reproduced `scrollY` changing from 1137 to 780:
native hash scrolling and the explicit demo reveal were both treating this
content replacement as section navigation.

Enhanced links inside the demo now prevent the fragment scroll, append a history
entry only when the workspace changes, and restore the captured coordinates
after replacing the content and updating focus. The same reproduction retains
1137 before and after the click. Reopening a workspace also stays in place.
Direct links, sources outside the demo and native no-JavaScript navigation keep
their section destinations. No layout or authenticated application behavior was
changed.

Six focused browser cases cover 1440/390/320px in both themes, including panels
with different heights, repeated activation, nested views and real pointer/Enter
events. Assertions compare both scroll coordinates in two painted frames after
the update. Existing direct-link, assistant-source and history coverage also
checks that deliberate navigation still reveals the destination. The history
test now starts with genuinely visible controls at a nonzero scroll position,
so it records a real reader location before Back/Forward. Native local-file
workspace selection and Back were checked with JavaScript as well.

The six scroll cases and legacy-fragment case passed together (7/7); the four
direct-link/assistant-source checks and corrected history test also passed.
The final full static run passed 33 of 34 cases, with only the native file test
showing the same offscreen-focus preparation problem. After waiting for local
fonts and making the source control visible before Enter, that unchanged
native-navigation contract passed three consecutive repetitions in both
languages (21.6 seconds). Thus every current case has a passing result; the full
suite was not repeated again after this test-only setup correction. Full-run
artifacts remain in `.local/test-results/preview-scroll-final/`, with native
repetitions in `.local/test-results/preview-scroll-native-repeat/`. Current
syntax, documentation-link and whitespace checks passed.

## Publication preparation

After accepting the presentation and scroll correction, the owner explicitly
approved GitHub Pages publication. The delivery branch was rebased onto
`9317c8c` (the existing 1.0.0 release). Both that release's changelog/review entries
and the preview entries were retained; the application version remains 1.0.0.

A fresh `npm run test:preview` passed all 34 cases in 2.3 minutes on this base,
including the previously corrected native file test. This supersedes the partial
full-run result above for the final preview tree. JavaScript syntax,
`git diff --check` and documentation validation passed; the documentation check
found 100 documents, 846 local references and no unresolved links. The independent
publication review found no blocking issue, private-data asset or runtime
provider request. Final local artifacts remain ignored under
`.local/test-results/preview-publication/` and its adjacent log.
