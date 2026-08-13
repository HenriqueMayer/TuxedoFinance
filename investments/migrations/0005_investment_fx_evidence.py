from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


def backfill_rate_evidence(apps, schema_editor):
    Investment = apps.get_model('investments', 'Investment')
    Rate = apps.get_model('banking', 'ExchangeRate')
    for operation in Investment.objects.exclude(fx_rate__isnull=True).iterator():
        if operation.fx_source_currency == operation.fx_target_currency:
            operation.fx_effective_date = operation.date
        else:
            direct = Rate.objects.filter(
                user_id=operation.user_id,
                from_currency=operation.fx_source_currency,
                to_currency=operation.fx_target_currency,
                effective_date__lte=operation.date,
            ).order_by('-effective_date', '-created_at').first()
            inverse = None
            if direct is None:
                inverse = Rate.objects.filter(
                    user_id=operation.user_id,
                    from_currency=operation.fx_target_currency,
                    to_currency=operation.fx_source_currency,
                    effective_date__lte=operation.date,
                ).order_by('-effective_date', '-created_at').first()
            evidence = direct or inverse
            if evidence is not None:
                expected = direct.rate if direct else (
                    Decimal('1') / inverse.rate
                ).quantize(Decimal('0.00000001'))
                if expected == operation.fx_rate:
                    operation.fx_source_rate_id = evidence.pk
                    operation.fx_effective_date = evidence.effective_date
        operation.save(update_fields=[
            'fx_source_rate', 'fx_effective_date',
        ])


class Migration(migrations.Migration):
    dependencies = [
        ('banking', '0004_banktransfer_fx_evidence'),
        ('investments', '0004_investment_fx_rate_investment_fx_snapshot_status_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='investment',
            name='fx_effective_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='investment',
            name='fx_source_rate',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='investment_snapshots',
                to='banking.exchangerate',
            ),
        ),
        migrations.RunPython(backfill_rate_evidence, migrations.RunPython.noop),
    ]
