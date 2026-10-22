# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('assistant', '0004_generationrun_reasoning_effort')]

    operations = [
        migrations.AddField(
            model_name='providerconnection',
            name='last_model_slug',
            field=models.CharField(blank=True, default='', max_length=160),
        ),
        migrations.AddField(
            model_name='providerconnection',
            name='last_reasoning_effort',
            field=models.CharField(blank=True, default='', max_length=12),
        ),
    ]
