# Generated by Django 2.2.28 on 2024-04-23 18:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0014_task_hide_solutions_of_expired_tasks'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='task',
            name='hide_solutions_of_expired_tasks',
        ),
        migrations.AddField(
            model_name='task',
            name='exam',
            field=models.BooleanField(default=False, help_text="If enabled, solutions (incl. attestations) of expired tasks and active tasks that are not exams are not accessible for students while this task is accepting submissions. Media files will only be visible while the task is active. After the deadline passed, solutions for this task won't be visible until they got attested."),
        ),
    ]
