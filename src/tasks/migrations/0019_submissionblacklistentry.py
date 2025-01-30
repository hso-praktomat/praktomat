# Generated by Django 5.1.2 on 2025-01-30 01:53

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0008_accept_disclaimer'),
        ('tasks', '0018_task_custom_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubmissionBlacklistEntry',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tasks.task')),
                ('user', models.ForeignKey(limit_choices_to={'groups__name': 'User'}, on_delete=django.db.models.deletion.CASCADE, to='accounts.user')),
            ],
        ),
    ]
