from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('investments', '0001_initial')]

    operations = [
        migrations.RemoveConstraint(model_name='investment', name='investments_quantity_gt_zero'),
        migrations.RemoveConstraint(model_name='investment', name='investments_unit_price_gt_zero'),
        migrations.AddField(model_name='asset', name='valuation_mode', field=models.CharField(choices=[('MONETARY', 'Monetary value'), ('UNITS', 'Units and price')], default='UNITS', max_length=10)),
        migrations.AddField(model_name='investment', name='amount', field=models.DecimalField(blank=True, decimal_places=2, help_text='Position value for monetary assets.', max_digits=16, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))])),
        migrations.AlterField(model_name='investment', name='quantity', field=models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True, validators=[django.core.validators.MinValueValidator(Decimal('1E-8'))])),
        migrations.AlterField(model_name='investment', name='unit_price', field=models.DecimalField(blank=True, decimal_places=8, max_digits=20, null=True, validators=[django.core.validators.MinValueValidator(Decimal('1E-8'))])),
        migrations.AddConstraint(model_name='investment', constraint=models.CheckConstraint(condition=models.Q(('quantity__isnull', True), ('quantity__gt', 0), _connector='OR'), name='investments_quantity_null_or_gt_zero')),
        migrations.AddConstraint(model_name='investment', constraint=models.CheckConstraint(condition=models.Q(('unit_price__isnull', True), ('unit_price__gt', 0), _connector='OR'), name='investments_unit_price_null_or_gt_zero')),
        migrations.AddConstraint(model_name='investment', constraint=models.CheckConstraint(condition=models.Q(('amount__isnull', True), ('amount__gt', 0), _connector='OR'), name='investments_amount_null_or_gt_zero')),
    ]
