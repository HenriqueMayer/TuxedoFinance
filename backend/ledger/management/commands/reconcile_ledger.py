"""Synchronize derived ledger rows after a change that sent no signal.

Writes, sign-in and ``migrate`` synchronize the ledger
(``transactions.ledger_state``); page loads only read it. A direct database
edit, a queryset ``update()`` or a data migration sends no signal. This
command synchronizes the selected users as of today and records their
synchronization state.

The output contains only counts and, for each failed user, the username and an
error code. It never shows amounts, titles or other financial data.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from ledger.ledger_state import error_code
from ledger.services import sync_user_ledger


class Command(BaseCommand):
    help = (
        "Synchronize the derived ledger rows of the selected users (default: all users) as of today. "
        "Use it after direct database edits. The output shows only counts and error codes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            action="append",
            dest="usernames",
            metavar="USERNAME",
            help="Synchronize only this user. Repeat the option for more users.",
        )

    def handle(self, *args, **options):
        user_model = get_user_model()
        username_field = user_model.USERNAME_FIELD
        users = user_model.objects.order_by("pk")
        usernames = options["usernames"]
        if usernames:
            users = users.filter(**{f"{username_field}__in": usernames})
            missing = sorted(set(usernames) - set(users.values_list(username_field, flat=True)))
            if missing:
                raise CommandError(
                    f"Unknown users: {', '.join(missing)}. No ledger was synchronized."
                )
        # Load the users first, so that no read cursor stays open while each
        # synchronization writes.
        users = list(users)
        failed = 0
        for user in users:
            try:
                sync_user_ledger(user)
            except Exception as error:
                # Each synchronization is atomic, so a failure leaves the
                # ledger of this user as it was. Continue with the next user.
                failed += 1
                self.stderr.write(
                    f"Ledger synchronization failed for user {user.get_username()}: {error_code(error)}"
                )
        self.stdout.write(f"Ledger synchronized for {len(users) - failed} of {len(users)} users.")
        if failed:
            raise CommandError(f"Ledger synchronization failed for {failed} of {len(users)} users.")
