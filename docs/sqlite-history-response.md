# SQLite Git history response plan

## Status and scope

The ROADMAP Phase 1.2 audit found that historical versions of the tracked root
`db.sqlite3` contain personal identity data, password hashes, session records
and, in an older version, financial data. Removing the database from the current
Git index prevents future accidental commits but does not remove existing blobs
from branches, tags, forks, caches or clones.

This document records the required follow-up. It does not authorize or perform
credential changes, session deletion, history rewriting or force-pushing.

## Immediate containment

The repository owner should:

1. **Completed August 13, 2026:** invalidate all Django sessions associated with
   databases that were tracked. The local session table was cleared; any user
   must now authenticate again.
2. **Completed August 13, 2026:** change the password of the real account whose
   hash was published. If the old password was reused elsewhere, change it
   there too.
3. Confirm that no deployment used the former published `SECRET_KEY` fallback.
   The fallback was removed from the source during ROADMAP Phase 1.3; rotate
   any real key that matched its historical value.
4. Treat the exposed historical blobs as compromised even after cleanup,
   because existing copies cannot be recalled.

**Completion gate:** ROADMAP Phase 1.2 completed after steps 1 and 2 were
confirmed. Step 3 applies only if a deployment reused the former published
fallback.

## Coordinated history rewrite

Handle the rewrite as a separate, announced maintenance operation:

1. Freeze pushes and enumerate every branch and tag, including remote refs.
2. Create a protected mirror backup before rewriting.
3. Remove `db.sqlite3` from every reachable revision with an appropriate Git
   history-filtering tool.
4. Verify that no rewritten ref contains the path, personal database blobs or
   unintended changes.
5. Force-push the complete rewritten ref set in one coordinated window.
6. Instruct collaborators to archive any needed work, delete old clones and
   reclone. Ordinary pulls can reintroduce old objects or create confusing
   histories.
7. Review forks, release assets, caches and other distribution locations that
   may still retain a copy.

## Data impact and rollback

The Phase 1.2 index change has no database migration and does not modify the
owner's local SQLite file. Existing clones should back up their database outside
the checkout before pulling because Git may remove a formerly tracked working
copy while applying the deletion.

A history rewrite changes commit identifiers across affected refs. Its rollback
is restoration of the protected pre-rewrite mirror and another coordinated
force-push. That rollback would deliberately re-expose the removed database
history, so it is only an emergency recovery mechanism—not a normal way to
recover local financial data. Database recovery must use the owner's protected
backup.
