# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import decimal
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('banking', '0009_card_appearance'),
        ('categories', '0002_category_transaction_type'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CardInvoiceCredit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=150)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=16, validators=[MinValueValidator(decimal.Decimal('0.01'))])),
                ('date', models.DateField()),
                ('reference_month', models.DateField()),
                ('notes', models.TextField(blank=True)),
                ('idempotency_key', models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ('card', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='invoice_credits', to='banking.creditcard')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='invoice_credits', to='categories.category')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='card_invoice_credits', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-date', '-pk'],
                'constraints': [models.CheckConstraint(condition=models.Q(('amount__gt', 0)), name='banking_invoice_credit_amount_gt_zero')],
            },
        ),
    ]
