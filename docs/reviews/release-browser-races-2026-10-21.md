# Release browser races — 2026-10-21

## Scope and authorization

This review covers the final browser checks for the unpublished 0.11.0 release.
The owner authorized committing the accumulated work, merging to main and
publishing the Docker distribution on 2026-10-21. That authorization does not
establish a successful CI run or public image; those remain separate release
gates, recorded on [PR #36](https://github.com/HenriqueMayer/TuxedoFinance/pull/36).

All browser runs use the repository's disposable database and loopback-server
entry points. No real model calls, bank connections, installation database or
personal credentials were used.

## Observations before correction

The complete local 700-case run finished with 622 passed, 73 skipped and five
failures. Two interrupted native navigations passed isolated reruns after local
Docker network mutations stopped. Two old outside-click assertions were changed
to avoid the deliberately clickable bank title bar; the nine-case account file
then passed. The old outer-border color assertion was aligned with the current
institution identity; the ten-case chart file then passed.

The subsequent exact-head checks at
`b4f5520c0f14873c3437a0527e3508d28b4b6afc` exposed additional timing problems:

- [Native CI](https://github.com/HenriqueMayer/TuxedoFinance/actions/runs/39687791804)
  finished with 621 passed, 73 skipped and six failed. Four assistant variants
  confirmed deletion during a pending conversation read, but no POST was sent.
  Two asset-refresh tests expected an enhanced XHR while the new document's
  deferred scripts were still loading; the native GET itself succeeded.
- [Docker validation](https://github.com/HenriqueMayer/TuxedoFinance/actions/runs/39687791665)
  passed on arm64 with 622 passed and 78 skipped. The amd64 run finished with
  621 passed, 78 skipped and one failure after two consecutive Back operations.
  Both architectures passed all five upgrade, lifecycle and restore baselines.
- Repeating the two investment FX cases passed natively in 17.3 seconds and in
  the exact candidate container in 14.9 seconds. This did not close the finding:
  a controlled delayed-history response reproduced an inconsistent document.
- The history probe first showed `/investments/` and its list heading. Releasing
  the older authorized position GET then replaced the content with that
  position while leaving the list URL unchanged. The HTML history cache stayed
  empty throughout.
- A separately controlled conversation GET reproduced the ignored confirmation:
  pressing the deletion control sent zero POSTs while the read was pending.

The raw traces, synthetic screenshots and server logs are retained under the
ignored `.local/release-2026-10-21/` directory. The failed results above must not
be described as a complete passing release check.

## Correction boundaries

The history runtime cancels superseded history GETs, including when an allowed
body request takes over. It retains fresh server authorization, the empty HTML
cache and the separate unsaved-edit decision. It never replays or cancels a
financial POST as a restoration strategy.

The assistant lets an explicit confirmation replace a pending read, while
continuing to block duplicate pending writes. Late read responses cannot
restore a deleted conversation. Financial drafts and the existing server-side
owner, session and confirmation checks remain authoritative.

The asset test waits for the new native document to finish loading before
requiring its next navigation to be enhanced. Clicking a native link before
enhancement remains supported behavior.

A targeted assistant rerun also exposed an older test inspecting the hidden
conversation's disclosure before Restore finished its authorization GET. That
test now waits for the visible restored panel before reading its history. The
product continues to hide retained content until authorization completes.

These changes do not alter layout, copy, financial calculations, schema or
provider gates. Existing preview images remain representative.

## Focused verification and final gate

The focused native history run passed all 30 cases in 2.0 minutes: six new
controlled race cases, five investment-FX cases, eight previous-workspace and
departure cases, and 11 private-history/BFCache/native cases. The asset-refresh
file passed all three cases in 8.9 seconds. The isolated Django system check,
migration-drift check, version consistency and documentation-link check passed.

The complete assistant local-chat file passed all 24 cases in 1.2 minutes,
including both controlled confirmation cases and the original draft, restore,
privacy, native, cancellation and recovery cases. The five guarded synthetic
assistant files passed all 33 cases in 3.2 minutes, covering financial actions,
consultations, simulations, Markdown exports, progress, streaming and native
recovery without a live provider. These four focused groups total 90 passing
browser cases.

Complete CI, both container architectures and the release-triggered publication
must then pass on the resulting commit before the release is reported complete.
Public assets, anonymous pulls, image identity, persistence and backup/restore
require independent verification after publication.
