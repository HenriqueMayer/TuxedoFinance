# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('assistant', '0005_providerconnection_chat_preferences')]

    operations = [
        migrations.CreateModel(
            name='ActionProposal',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('request_id', models.UUIDField(default=uuid.uuid4, editable=False)),
                ('session_digest', models.CharField(max_length=64)),
                ('name', models.CharField(max_length=40)),
                ('parameters', models.JSONField(default=dict)),
                ('summary', models.JSONField(default=list)),
                ('dependency_digest', models.CharField(max_length=64)),
                ('status', models.CharField(choices=[('pending', 'Awaiting confirmation'), ('executing', 'Executing'),
                                                   ('executed', 'Executed'), ('cancelled', 'Cancelled')],
                                          default='pending', max_length=12)),
                ('result', models.JSONField(default=dict)),
                ('expires_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                    related_name='action_proposals', to='assistant.conversation')),
                ('generation_run', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                                      related_name='action_proposals', to='assistant.generationrun')),
                ('message', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                               related_name='action_proposals', to='assistant.message')),
            ],
            options={'ordering': ['created_at', 'pk']},
        ),
        migrations.AddConstraint(
            model_name='actionproposal',
            constraint=models.UniqueConstraint(fields=('conversation', 'request_id'), name='assistant_action_request_unique'),
        ),
    ]
