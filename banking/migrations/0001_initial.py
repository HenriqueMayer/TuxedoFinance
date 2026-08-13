import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Bank',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='banks', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='BankAccount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('currency', models.CharField(choices=[('BRL', 'Brazilian Real'), ('USD', 'US Dollar'), ('EUR', 'Euro'), ('GBP', 'British Pound'), ('JPY', 'Japanese Yen'), ('CHF', 'Swiss Franc')], max_length=3)),
                ('opening_balance', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=16)),
                ('pix_enabled', models.BooleanField(default=True)),
                ('bank', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='accounts', to='banking.bank')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bank_accounts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['bank__name', 'name', 'currency'],
            },
        ),
        migrations.CreateModel(
            name='BankTransfer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('source_amount', models.DecimalField(decimal_places=2, max_digits=16, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('destination_amount', models.DecimalField(decimal_places=2, max_digits=16, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('date', models.DateField()),
                ('notes', models.TextField(blank=True)),
                ('destination_account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='incoming_transfers', to='banking.bankaccount')),
                ('source_account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='outgoing_transfers', to='banking.bankaccount')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bank_transfers', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CardInvoice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('reference_month', models.DateField()),
                ('due_date', models.DateField()),
                ('amount', models.DecimalField(decimal_places=2, max_digits=16, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))])),
                ('status', models.CharField(choices=[('SCHEDULED', 'Scheduled'), ('PAID', 'Paid')], default='SCHEDULED', max_length=10)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='card_invoices', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-reference_month', 'card__name'],
            },
        ),
        migrations.CreateModel(
            name='BankMovement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('direction', models.CharField(choices=[('CREDIT', 'Credit'), ('DEBIT', 'Debit')], max_length=6)),
                ('kind', models.CharField(choices=[('INCOME', 'Income'), ('EXPENSE', 'Expense'), ('TRANSFER', 'Transfer'), ('INVOICE', 'Invoice'), ('INVESTMENT', 'Investment'), ('REWARD', 'Reward'), ('ADJUSTMENT', 'Adjustment')], max_length=12)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=16, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('effective_date', models.DateField()),
                ('description', models.CharField(blank=True, max_length=255)),
                ('source_key', models.CharField(blank=True, max_length=100)),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='movements', to='banking.bankaccount')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='bank_movements', to=settings.AUTH_USER_MODEL)),
                ('transfer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='movements', to='banking.banktransfer')),
                ('invoice', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='settlement_movement', to='banking.cardinvoice')),
            ],
            options={
                'ordering': ['-effective_date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CreditCard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('closing_day', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(31)])),
                ('due_day', models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(31)])),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='credit_cards', to='banking.bankaccount')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='credit_cards', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='cardinvoice',
            name='card',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='invoices', to='banking.creditcard'),
        ),
        migrations.CreateModel(
            name='DebitCard',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='debit_cards', to='banking.bankaccount')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='debit_cards', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='ExchangeRate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('from_currency', models.CharField(choices=[('BRL', 'Brazilian Real'), ('USD', 'US Dollar'), ('EUR', 'Euro'), ('GBP', 'British Pound'), ('JPY', 'Japanese Yen'), ('CHF', 'Swiss Franc')], max_length=3)),
                ('to_currency', models.CharField(choices=[('BRL', 'Brazilian Real'), ('USD', 'US Dollar'), ('EUR', 'Euro'), ('GBP', 'British Pound'), ('JPY', 'Japanese Yen'), ('CHF', 'Swiss Franc')], max_length=3)),
                ('rate', models.DecimalField(decimal_places=8, max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal('1E-8'))])),
                ('effective_date', models.DateField()),
                ('notes', models.CharField(blank=True, max_length=255)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='banking_exchange_rates', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-effective_date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='LoyaltyProgram',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=100)),
                ('unit_name', models.CharField(default='Points', max_length=30)),
                ('bank', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='loyalty_programs', to='banking.bank')),
                ('cards', models.ManyToManyField(blank=True, related_name='loyalty_programs', to='banking.creditcard')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='loyalty_programs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='LoyaltyEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('direction', models.CharField(choices=[('CREDIT', 'Credit'), ('DEBIT', 'Debit')], max_length=6)),
                ('kind', models.CharField(choices=[('INVOICE_AWARD', 'Invoice award'), ('PURCHASE', 'Purchase'), ('ADJUSTMENT', 'Adjustment'), ('EXPIRATION', 'Expiration'), ('REDEMPTION', 'Redemption')], max_length=13)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=16, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('date', models.DateField()),
                ('notes', models.TextField(blank=True)),
                ('invoice', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='loyalty_entries', to='banking.cardinvoice')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='loyalty_entries', to=settings.AUTH_USER_MODEL)),
                ('program', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='entries', to='banking.loyaltyprogram')),
            ],
            options={
                'ordering': ['-date', '-pk'],
            },
        ),
        migrations.CreateModel(
            name='RewardRedemption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('points', models.DecimalField(decimal_places=2, max_digits=16, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('target_amount', models.DecimalField(decimal_places=2, max_digits=16, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('iof_amount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=16, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))])),
                ('date', models.DateField()),
                ('notes', models.TextField(blank=True)),
                ('iof_account', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='iof_reward_redemptions', to='banking.bankaccount')),
                ('iof_credit_card', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='iof_reward_redemptions', to='banking.creditcard')),
                ('program', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='redemptions', to='banking.loyaltyprogram')),
                ('target_account', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='reward_redemptions', to='banking.bankaccount')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reward_redemptions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-date', '-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='bank',
            constraint=models.UniqueConstraint(fields=('user', 'name'), name='banking_unique_bank_user_name'),
        ),
        migrations.AddConstraint(
            model_name='bankaccount',
            constraint=models.UniqueConstraint(fields=('bank', 'name', 'currency'), name='banking_unique_account_bank_name_currency'),
        ),
        migrations.AddConstraint(
            model_name='banktransfer',
            constraint=models.CheckConstraint(condition=models.Q(('source_amount__gt', 0)), name='banking_transfer_source_amount_gt_zero'),
        ),
        migrations.AddConstraint(
            model_name='banktransfer',
            constraint=models.CheckConstraint(condition=models.Q(('destination_amount__gt', 0)), name='banking_transfer_destination_amount_gt_zero'),
        ),
        migrations.AddConstraint(
            model_name='banktransfer',
            constraint=models.CheckConstraint(condition=models.Q(('source_account', models.F('destination_account')), _negated=True), name='banking_transfer_accounts_differ'),
        ),
        migrations.AddConstraint(
            model_name='bankmovement',
            constraint=models.CheckConstraint(condition=models.Q(('amount__gt', 0)), name='banking_movement_amount_gt_zero'),
        ),
        migrations.AddConstraint(
            model_name='bankmovement',
            constraint=models.UniqueConstraint(condition=models.Q(('source_key', ''), _negated=True), fields=('user', 'source_key'), name='banking_unique_movement_source_key'),
        ),
        migrations.AddConstraint(
            model_name='creditcard',
            constraint=models.UniqueConstraint(fields=('account', 'name'), name='banking_unique_credit_card_account_name'),
        ),
        migrations.AddConstraint(
            model_name='cardinvoice',
            constraint=models.UniqueConstraint(fields=('card', 'reference_month'), name='banking_unique_invoice_card_month'),
        ),
        migrations.AddConstraint(
            model_name='cardinvoice',
            constraint=models.CheckConstraint(condition=models.Q(('amount__gte', 0)), name='banking_invoice_amount_gte_zero'),
        ),
        migrations.AddConstraint(
            model_name='debitcard',
            constraint=models.UniqueConstraint(fields=('account', 'name'), name='banking_unique_debit_card_account_name'),
        ),
        migrations.AddConstraint(
            model_name='exchangerate',
            constraint=models.UniqueConstraint(fields=('user', 'from_currency', 'to_currency', 'effective_date'), name='banking_unique_exchange_pair_date'),
        ),
        migrations.AddConstraint(
            model_name='exchangerate',
            constraint=models.CheckConstraint(condition=models.Q(('rate__gt', 0)), name='banking_exchange_rate_gt_zero'),
        ),
        migrations.AddConstraint(
            model_name='exchangerate',
            constraint=models.CheckConstraint(condition=models.Q(('from_currency', models.F('to_currency')), _negated=True), name='banking_exchange_currencies_differ'),
        ),
        migrations.AddConstraint(
            model_name='loyaltyprogram',
            constraint=models.UniqueConstraint(fields=('user', 'name'), name='banking_unique_loyalty_user_name'),
        ),
        migrations.AddConstraint(
            model_name='loyaltyentry',
            constraint=models.CheckConstraint(condition=models.Q(('amount__gt', 0)), name='banking_loyalty_amount_gt_zero'),
        ),
        migrations.AddConstraint(
            model_name='rewardredemption',
            constraint=models.CheckConstraint(condition=models.Q(('points__gt', 0)), name='banking_redemption_points_gt_zero'),
        ),
        migrations.AddConstraint(
            model_name='rewardredemption',
            constraint=models.CheckConstraint(condition=models.Q(('target_amount__gt', 0)), name='banking_redemption_target_amount_gt_zero'),
        ),
        migrations.AddConstraint(
            model_name='rewardredemption',
            constraint=models.CheckConstraint(condition=models.Q(('iof_amount__gte', 0)), name='banking_redemption_iof_amount_gte_zero'),
        ),
    ]
