# Direct preview and New entry — 2026-10-18

## Scope

This follow-up simplifies the preceding
[workspace-preview iteration](preview-workspaces-2026-10-18.md) at the owner's
request. Both READMEs remove the video disclosure; the two generated GIFs are
removed from source delivery. Earlier recordings and evidence remain ignored in
`.local/`. The prominent preview link, bilingual copy and quick starts remain.

The tour opens directly on Home's dashboard, with category bars, balances and
invoices visible in the captured application. The large introductory bow tie
and its unused styles are removed; the small wordmark retains the identity.
Home/form thumbnails also omit their captured duplicate titles; the balance
and form panels stay intact, and original images remain available in full.
Reports stays one section tab away. Home and Transactions expose New entry,
which opens a separate view of the actual transaction form, rather than a
second form implementation. The owner explicitly selected this simpler,
non-editable presentation.

The new form captures show Expense and Credit card activated through native
controls, with an available saved-card miniature. No transaction is filled or
submitted. All 28 captures use the same 1440 × 1000 viewport and synthetic
profiles: seven areas, two languages and two themes. The all-image staging guard
also rejects a missing new-entry image before replacing existing images.

New entry keeps Transactions active in primary navigation. Native hashes,
Back/Forward, language/theme context, keyboard actions, image enlargement,
phone dock and no-JavaScript access remain supported. The previous `#top` and
`#dashboard-preview` anchors still resolve to Home. Application source, financial
calculations, installation data and release identity are unchanged.

## Verification

The isolated capture workflow and eight capture-tool tests passed, including
cleanup and incomplete-batch preservation. The full repository-tool suite
passed 40 tests; isolated Django system checks found no issues, and version
consistency remains 0.10.0.

The final static-preview browser run passed all 17 tests in 40.5 seconds.
It covers both themes/languages, desktop/phone bounds, New entry activation
through Home and Transactions, parent navigation, keyboard/history, language
context, lightbox focus, sandboxed links and native file/no-JavaScript access.
Eight additional entry renders verified desktop/phone layout in both languages
and themes, including final links above the dock. The dashboard and form renders
were visually inspected, including the refined thumbnail crops.

Both READMEs retain their preview actions and valid shell commands, with no GIF
references. Documentation checks found 59 documents, 515 local references and no
unresolved links. Python undefined-name lint and `git diff --check` passed.
All 531 protected application source hashes and five installation identities
remain unchanged; the capture wrapper's database fingerprint guard passed.

Logs and captures are ignored under `.local/test-results/preview-simple/`,
`.local/test-results/preview-redesign/` and `.local/test-results/preview/`.
The owning maintenance contract is the [preview guide](../preview.md).
The complete financial/Django application suite and container checks were not
rerun for this presentation-only follow-up. Nothing was merged or published.
