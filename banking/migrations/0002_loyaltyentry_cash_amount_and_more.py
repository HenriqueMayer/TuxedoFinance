import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('banking', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='loyaltyentry',
            name='cash_amount',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=16, null=True, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))]),
        ),
        migrations.AddField(
            model_name='loyaltyentry',
            name='funding_account',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='funded_loyalty_entries', to='banking.bankaccount'),
        ),
        migrations.AddField(
            model_name='loyaltyentry',
            name='funding_credit_card',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='funded_loyalty_entries', to='banking.creditcard'),
        ),
        migrations.AddField(
            model_name='loyaltyentry',
            name='funding_movement',
            field=models.OneToOneField(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='loyalty_purchase', to='banking.bankmovement'),
        ),
        migrations.AddField(
            model_name='rewardredemption',
            name='iof_movement',
            field=models.OneToOneField(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reward_iof_redemption', to='banking.bankmovement'),
        ),
        migrations.AddField(
            model_name='rewardredemption',
            name='loyalty_entry',
            field=models.OneToOneField(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reward_redemption', to='banking.loyaltyentry'),
        ),
        migrations.AddField(
            model_name='rewardredemption',
            name='reward_movement',
            field=models.OneToOneField(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='reward_redemption', to='banking.bankmovement'),
        ),
    ]
