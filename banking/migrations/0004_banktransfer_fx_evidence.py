from django.db import migrations, models
import django.db.models.deletion


def backfill_effective_dates(apps, schema_editor):
    Transfer = apps.get_model('banking', 'BankTransfer')
    Transfer.objects.filter(
        fx_snapshot_status__in=['CAPTURED', 'RECONSTRUCTED'],
        fx_effective_date__isnull=True,
    ).update(fx_effective_date=models.F('date'))


class Migration(migrations.Migration):
    dependencies = [
        ('banking', '0003_banktransfer_fx_rate_banktransfer_fx_snapshot_status_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='banktransfer',
            name='fx_effective_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='banktransfer',
            name='fx_source_rate',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='transfer_snapshots',
                to='banking.exchangerate',
            ),
        ),
        migrations.RunPython(backfill_effective_dates, migrations.RunPython.noop),
    ]
