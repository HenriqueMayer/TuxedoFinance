# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""Insert an opt-in, isolated demonstration profile into the configured database."""

from datetime import date
import secrets

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from django.utils import timezone

from accounts.demo_data import seed_demo_profile


class Command(BaseCommand):
    help = 'Create a new fictional Portuguese (pt) or English (en) demo user. Never overwrite a user.'

    def add_arguments(self, parser):
        parser.add_argument('language', choices=['pt', 'en'])
        parser.add_argument('--username', help='New username (default: demo_pt or demo_en).')
        parser.add_argument('--as-of', help='Reference date YYYY-MM-DD (default: today).')

    def handle(self, *args, **options):
        language = options['language']
        username = options['username'] or f'demo_{language}'
        as_of = options['as_of'] or timezone.localdate()
        password = secrets.token_urlsafe(18)
        try:
            if isinstance(as_of, str):
                as_of = date.fromisoformat(as_of)
            user = seed_demo_profile(language=language, username=username, password=password, as_of=as_of)
        except (ValueError, ValidationError, IntegrityError) as error:
            raise CommandError(f'Demo creation rolled back: {error}') from error
        self.stdout.write(self.style.SUCCESS(f'Created demonstration user: {user.username}'))
        self.stdout.write(f'Password: {password}')
        self.stdout.write(f'Reference date: {as_of.isoformat()}')
        self.stdout.write(f'Transactions: {user.transactions.count()}; investment operations: {user.investments.count()}; saved scenarios: {user.scenario_drafts.count()}')
        self.stdout.write('Select Português (Brasil) in the interface.' if language == 'pt'
                          else 'Select English in the interface.')
        self.stdout.write('Existing users were not modified. See docs/demo-data.md for the presentation walkthrough.')
