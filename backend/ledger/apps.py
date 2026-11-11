from django.apps import AppConfig


class LedgerConfig(AppConfig):
    name = "ledger"

    def ready(self):
        # Writes, sign-in and migrate keep the derived ledger rows current;
        # reads only read them (ledger.ledger_state).
        from django.db.models.signals import post_migrate

        from ledger import (
            category_defaults,  # noqa: F401  Connects the default-category receiver.
            ledger_state,
        )

        ledger_state.connect()
        post_migrate.connect(
            ledger_state.synchronize_outdated_rules,
            sender=self,
            dispatch_uid="ledger-outdated-rules",
        )
