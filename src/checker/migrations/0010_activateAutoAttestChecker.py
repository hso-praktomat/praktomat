# Generated by Django 1.11.15 on 2018-11-10 07:46

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_add_coordinator_group'),
        ('tasks', '0005_task_ordering'),
        ('checker', '0009_isabelle_checker_trusted_to_additional_theories'),
    ]

    operations = [
        migrations.CreateModel(
            name='AutoAttestChecker',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('order', models.IntegerField(help_text='Determines the order in wich the checker will start. Not necessary continuously!')),
                ('public', models.BooleanField(default=True, help_text='Test results are displayed to the submitter.')),
                ('required', models.BooleanField(default=False, help_text='The test must be passed to submit the solution.')),
                ('always', models.BooleanField(default=True, help_text='The test will run on submission time.')),
                ('critical', models.BooleanField(default=False, help_text='If this test fails, do not display further test results.')),
                ('public_comment', models.TextField(blank=True, help_text='Comment which is shown to the user.')),
                ('private_comment', models.TextField(blank=True, help_text='Comment which is only visible to tutors')),
                ('final', models.BooleanField(default=True, help_text='Indicates whether the attestation is ready to be published')),
                ('published', models.BooleanField(default=True, help_text='Indicates whether the user can see the attestation.')),
                ('author', models.ForeignKey(blank=True, limit_choices_to={'groups__name': 'Tutor'}, null=True, on_delete=django.db.models.deletion.SET_NULL, to='accounts.User', verbose_name='attestation author')),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tasks.Task')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
