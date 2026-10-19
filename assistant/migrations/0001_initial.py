# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name='Conversation', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('title', models.CharField(blank=True, default='', max_length=120)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                      related_name='assistant_conversations', to=settings.AUTH_USER_MODEL)),
        ], options={'ordering': ['-updated_at', '-pk']}),
        migrations.CreateModel(name='Message', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('role', models.CharField(choices=[('user', 'User'), ('assistant', 'Assistant')], max_length=12)),
            ('content', models.TextField()),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                               related_name='messages', to='assistant.conversation')),
        ], options={'ordering': ['created_at', 'pk']}),
    ]
