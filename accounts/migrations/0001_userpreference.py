from django.conf import settings
from django.db import migrations, models


def create_preferences(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    Preference = apps.get_model('accounts', 'UserPreference')
    Preference.objects.bulk_create(
        [Preference(user_id=user.pk, base_currency='BRL') for user in User.objects.only('pk')]
    )


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='UserPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('base_currency', models.CharField(choices=[('BRL', 'Brazilian Real'), ('USD', 'US Dollar'), ('EUR', 'Euro'), ('GBP', 'British Pound'), ('JPY', 'Japanese Yen'), ('CHF', 'Swiss Franc')], default='BRL', max_length=3)),
                ('user', models.OneToOneField(on_delete=models.deletion.CASCADE, related_name='preferences', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(create_preferences, migrations.RunPython.noop),
    ]
