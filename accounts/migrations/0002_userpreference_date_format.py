from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0001_userpreference')]

    operations = [
        migrations.AddField(
            model_name='userpreference',
            name='date_format',
            field=models.CharField(
                choices=[('DMY', 'DD/MM/YYYY'), ('MDY', 'MM/DD/YYYY')],
                default='DMY',
                max_length=3,
            ),
        ),
    ]
