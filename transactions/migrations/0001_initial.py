import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('banking', '0002_loyaltyentry_cash_amount_and_more'),
        ('categories', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Transaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=150)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('transaction_type', models.CharField(choices=[('INCOME', 'Income'), ('EXPENSE', 'Expense')], max_length=20)),
                ('payment_channel', models.CharField(choices=[('ACCOUNT', 'Bank account'), ('PIX', 'PIX'), ('DEBIT_CARD', 'Debit card'), ('CREDIT_CARD', 'Credit card')], max_length=20)),
                ('installments', models.PositiveSmallIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(48)])),
                ('billing_override', models.PositiveSmallIntegerField(blank=True, choices=[(0, 'Current bill'), (1, 'Next bill')], default=None, null=True)),
                ('is_fixed', models.BooleanField(default=False)),
                ('fixed_until', models.DateField(blank=True, null=True)),
                ('date', models.DateField()),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('bank_account', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='banking.bankaccount')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='categories.category')),
                ('credit_card', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='banking.creditcard')),
                ('debit_card', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='banking.debitcard')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-date', '-created_at'],
                'constraints': [models.CheckConstraint(condition=models.Q(('amount__gt', 0)), name='transactions_amount_gt_zero'), models.CheckConstraint(condition=models.Q(models.Q(('bank_account__isnull', False), ('credit_card__isnull', True), ('debit_card__isnull', True), ('payment_channel__in', ['ACCOUNT', 'PIX'])), models.Q(('bank_account__isnull', True), ('credit_card__isnull', True), ('debit_card__isnull', False), ('payment_channel', 'DEBIT_CARD')), models.Q(('bank_account__isnull', True), ('credit_card__isnull', False), ('debit_card__isnull', True), ('payment_channel', 'CREDIT_CARD')), _connector='OR'), name='transactions_coherent_payment_instrument')],
            },
        ),
    ]
