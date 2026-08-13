from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('investments', '0002_remove_investment_investments_quantity_gt_zero_and_more')]

    operations = [
        migrations.AddField(model_name='asset', name='opening_balance', field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Existing balance before the first recorded operation.', max_digits=16, validators=[django.core.validators.MinValueValidator(Decimal('0.00'))])),
        migrations.AddField(model_name='asset', name='opening_product', field=models.ForeignKey(blank=True, help_text='Product that holds the opening balance.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='opening_balance_assets', to='investments.investmentproduct')),
    ]
