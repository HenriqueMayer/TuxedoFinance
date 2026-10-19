# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('assistant', '0003_generationrun')]

    operations = [
        migrations.AddField(
            model_name='generationrun',
            name='reasoning_effort',
            field=models.CharField(blank=True, default='', max_length=12),
        ),
    ]
