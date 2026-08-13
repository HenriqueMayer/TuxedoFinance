import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('banking', '0002_loyaltyentry_cash_amount_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Asset',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('code', models.CharField(max_length=20)),
                ('asset_class', models.CharField(choices=[('LIQUIDITY', 'Liquidity'), ('CURRENCY', 'Currency'), ('CRYPTO', 'Crypto'), ('FIXED_INCOME', 'Fixed income'), ('EQUITY', 'Equity'), ('OTHER', 'Other')], max_length=20)),
                ('currency', models.CharField(choices=[('BRL', 'Brazilian Real'), ('USD', 'US Dollar'), ('EUR', 'Euro'), ('GBP', 'British Pound'), ('JPY', 'Japanese Yen'), ('CHF', 'Swiss Franc')], max_length=3)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='investment_assets', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='InvestmentProduct',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('yield_mode', models.CharField(choices=[('MANUAL', 'Manual'), ('MONTHLY', 'Monthly rate (Coming soon)'), ('ANNUAL', 'Annual rate (Coming soon)')], default='MANUAL', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('bank', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='investment_products', to='banking.bank')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='investment_products', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['bank__name', 'name'],
            },
        ),
        migrations.CreateModel(
            name='Investment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('DEPOSIT', 'Deposit'), ('WITHDRAWAL', 'Withdrawal'), ('YIELD', 'Yield')], max_length=20)),
                ('quantity', models.DecimalField(decimal_places=8, max_digits=20, validators=[django.core.validators.MinValueValidator(Decimal('1E-8'))])),
                ('unit_price', models.DecimalField(decimal_places=8, max_digits=20, validators=[django.core.validators.MinValueValidator(Decimal('1E-8'))])),
                ('fees', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=16, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))])),
                ('cash_amount', models.DecimalField(blank=True, decimal_places=2, help_text='Native amount debited from or credited to the selected account.', max_digits=16, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('source_points', models.DecimalField(blank=True, decimal_places=2, max_digits=16, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
                ('date', models.DateField()),
                ('reason', models.CharField(blank=True, max_length=255)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('asset', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='operations', to='investments.asset')),
                ('bank_movement', models.OneToOneField(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='investment_operation', to='banking.bankmovement')),
                ('destination_account', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='investment_withdrawals', to='banking.bankaccount')),
                ('loyalty_entry', models.OneToOneField(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='investment_operation', to='banking.loyaltyentry')),
                ('source_account', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='funded_investments', to='banking.bankaccount')),
                ('source_program', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='funded_investments', to='banking.loyaltyprogram')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='investments', to=settings.AUTH_USER_MODEL)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='operations', to='investments.investmentproduct')),
            ],
            options={
                'ordering': ['-date', '-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='asset',
            constraint=models.UniqueConstraint(fields=('user', 'code'), name='unique_investment_asset_code_per_user'),
        ),
        migrations.AddConstraint(
            model_name='investmentproduct',
            constraint=models.UniqueConstraint(fields=('bank', 'name'), name='investments_unique_product_bank_name'),
        ),
        migrations.AddConstraint(
            model_name='investment',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__gt', 0)), name='investments_quantity_gt_zero'),
        ),
        migrations.AddConstraint(
            model_name='investment',
            constraint=models.CheckConstraint(condition=models.Q(('unit_price__gt', 0)), name='investments_unit_price_gt_zero'),
        ),
        migrations.AddConstraint(
            model_name='investment',
            constraint=models.CheckConstraint(condition=models.Q(('fees__gte', 0)), name='investments_fees_gte_zero'),
        ),
        migrations.AddConstraint(
            model_name='investment',
            constraint=models.CheckConstraint(condition=models.Q(('cash_amount__isnull', True), ('cash_amount__gt', 0), _connector='OR'), name='investments_cash_amount_null_or_gt_zero'),
        ),
        migrations.AddConstraint(
            model_name='investment',
            constraint=models.CheckConstraint(condition=models.Q(('source_points__isnull', True), ('source_points__gt', 0), _connector='OR'), name='investments_source_points_null_or_gt_zero'),
        ),
    ]
