from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('banking', '0004_banktransfer_fx_evidence'),
    ]

    operations = [
        migrations.AddField(
            model_name='creditcard',
            name='card_type',
            field=models.CharField(
                choices=[
                    ('PHYSICAL', 'Physical'),
                    ('VIRTUAL', 'Virtual'),
                    ('ADDITIONAL', 'Additional'),
                ],
                default='PHYSICAL',
                max_length=10,
            ),
        ),
    ]
