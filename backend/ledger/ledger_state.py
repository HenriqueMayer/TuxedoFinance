"""Keep the derived ledger rows current without page loads.

Page loads do not synchronize the ledger: they call
``transactions.services.read_ledger_state``, which never writes (step B). These
triggers synchronize instead:

* A change of a ledger input. The receivers below mark the ledger of the
  owner stale in the database transaction of the change, so a rolled-back
  change leaves the state unchanged. They also register
  ``synchronize_after_commit``, which runs after the commit: in a shell, a
  script, the admin or a view that does not synchronize explicitly.
* A sign-in (``user_logged_in``). Django sessions last two weeks by default,
  so each active user signs in at least that often.
* ``migrate``, for states recorded by another ``LEDGER_RULES_VERSION``
  (``synchronize_outdated_rules``, a ``post_migrate`` receiver).

A trigger never raises: the change, the sign-in or the migration has already
succeeded. A refused synchronization marks the ledger stale, so page loads run
the occurrence-limit check and redirect to the recovery list. The log shows
only error codes and, for ``migrate``, usernames.

``WATCHED_MODELS`` lists the models whose rows ``sync_user_ledger``,
``build_projection_plan`` and ``banking.services.sync_redemption_iof_transaction``
read to derive movements and invoices. The guide lists the fields that each model
contributes. Synchronization writes ``BankMovement`` and ``CardInvoice``
itself, so they are not watched.

Limits:

* Queryset ``update()``, ``bulk_create()``, ``bulk_update()``, raw SQL,
  historical models in data migrations and direct database edits send no
  signals. After such a change, run ``manage.py reconcile_ledger``.
* A receiver marks the owner of the changed row (``user_id``). A legacy row
  that refers to an instrument of another user is not followed.
* In autocommit mode, for example a script without ``transaction.atomic``,
  Django runs the callback at once, so each watched save synchronizes.
"""

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.signals import post_delete, post_save

from banking.models import (
    BankAccount,
    CardInvoiceCredit,
    CreditCard,
    DebitCard,
    InvoicePayment,
    LoyaltyEntry,
    RewardRedemption,
)
from ledger import services
from ledger.models import LedgerSyncState, OccurrenceOverride, ScheduleAmount, Transaction
from ledger.projection import ProjectionLimitExceeded

logger = logging.getLogger(__name__)

WATCHED_MODELS = (
    Transaction,
    BankAccount,
    DebitCard,
    CreditCard,
    CardInvoiceCredit,
    LoyaltyEntry,
    RewardRedemption,
    InvoicePayment,
    ScheduleAmount,
    OccurrenceOverride,
)

# Fields that synchronization does not read, by watched model. A save whose
# update_fields are all in this set does not change derived rows, so it
# neither marks the ledger stale nor synchronizes (for example the planning
# toggle of an account). Other fields of these models keep the marks.
UNREAD_UPDATE_FIELDS = {
    BankAccount: frozenset({"planning_enabled", "reserved_amount", "updated_at"}),
    InvoicePayment: frozenset({"movement", "updated_at"}),
    LoyaltyEntry: frozenset({"funding_movement", "updated_at"}),
    RewardRedemption: frozenset({"loyalty_entry", "reward_movement", "iof_movement", "updated_at"}),
}


def error_code(error):
    """Return a short code for a synchronization error, without its message.

    A validation message can quote financial records, so only its code is
    shown. Other errors show their class name.
    """
    if isinstance(error, ValidationError):
        items = getattr(error, "error_list", None)
        if items is None:
            items = [item for errors in error.error_dict.values() for item in errors]
        code = getattr(error, "code", None) or next(
            (item.code for item in items if item.code), None
        )
        return code or "invalid"
    return type(error).__name__


def _mark_stale(user_id):
    try:
        services.mark_ledger_stale(user_id)
    except Exception as error:
        logger.error("The ledger could not be marked stale: %s", error_code(error))


def _synchronize(user, trigger):
    """Synchronize when the ledger is not current; log a failure and never raise."""
    try:
        services.ensure_ledger_current(user)
    except ProjectionLimitExceeded as error:
        # The refusal happens before any write. A stale state makes page
        # loads run the occurrence-limit check, which redirects to recovery.
        logger.warning(
            "Ledger synchronization after %s was refused: %s", trigger, error_code(error)
        )
        _mark_stale(user.pk)
    except Exception as error:
        logger.error("Ledger synchronization after %s failed: %s", trigger, error_code(error))


def synchronize_after_commit(user_id):
    """Synchronize the ledger of ``user_id`` after a committed change of a ledger input.

    A view that synchronized explicitly has already recorded a current
    state, so this costs one SELECT. A deleted user needs nothing.
    """
    try:
        if services.ledger_is_current(user_id):
            return
        user = get_user_model().objects.filter(pk=user_id).first()
    except Exception as error:
        logger.error("Ledger synchronization after a commit failed: %s", error_code(error))
        return
    if user is not None:
        _synchronize(user, "a commit")


def ledger_input_changed(sender, instance, update_fields=None, **kwargs):
    """Receive ``post_save`` and ``post_delete`` of a watched model.

    A fixture load (``raw=True``) changes inputs too, so it also marks.
    """
    if update_fields and frozenset(update_fields) <= UNREAD_UPDATE_FIELDS.get(sender, frozenset()):
        return
    user_id = instance.user_id
    services.mark_ledger_stale(user_id)

    def synchronize():
        synchronize_after_commit(user_id)

    # A named function, not functools.partial: Django logs the __qualname__
    # of a robust callback that raises.
    transaction.on_commit(synchronize, robust=True)


def synchronize_on_login(sender, request, user, **kwargs):
    """Receive ``user_logged_in``; the sign-in succeeds also when synchronization fails."""
    _synchronize(user, "a sign-in")


def synchronize_outdated_rules(
    sender, *, using=DEFAULT_DB_ALIAS, plan=None, verbosity=1, stdout=None, **kwargs
):
    """Receive ``post_migrate``: synchronize the users whose state has another rules version.

    A state with an older or a newer ``rules_version`` is outdated; a missing
    state is not selected, because the first write or sign-in synchronizes
    it. The receiver does nothing for ``flush`` (no ``plan``), for another
    database, before the state table exists and while migrations remain
    unapplied, because the models may not match the schema then. A failed
    user is marked stale and logged with the username and an error code.
    """
    if plan is None or using != DEFAULT_DB_ALIAS:
        return
    try:
        connection = connections[using]
        if LedgerSyncState._meta.db_table not in connection.introspection.table_names():
            return
        user_ids = list(
            LedgerSyncState.objects.exclude(rules_version=services.LEDGER_RULES_VERSION)
            .order_by("user_id")
            .values_list("user_id", flat=True)
        )
        if not user_ids:
            return
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            return
        users = list(get_user_model().objects.filter(pk__in=user_ids).order_by("pk"))
    except Exception as error:
        logger.error("Ledger rules check after migrate failed: %s", error_code(error))
        return
    failed = 0
    for user in users:
        try:
            services.sync_user_ledger(user)
        except Exception as error:
            failed += 1
            logger.warning(
                "Ledger synchronization after migrate failed for user %s: %s",
                user.get_username(),
                error_code(error),
            )
            _mark_stale(user.pk)
    if verbosity >= 1 and stdout is not None:
        # migrate passes an OutputWrapper; it adds no second line ending.
        stdout.write(
            f"Ledger synchronized for {len(users) - failed} of {len(users)} users "
            "with other ledger rules.\n"
        )


def connect():
    """Connect the input and sign-in receivers; ``TransactionsConfig.ready`` calls this once."""
    for model in WATCHED_MODELS:
        label = model._meta.label_lower
        post_save.connect(
            ledger_input_changed, sender=model, dispatch_uid=f"ledger-input-saved:{label}"
        )
        post_delete.connect(
            ledger_input_changed, sender=model, dispatch_uid=f"ledger-input-deleted:{label}"
        )
    user_logged_in.connect(synchronize_on_login, dispatch_uid="ledger-sign-in")
