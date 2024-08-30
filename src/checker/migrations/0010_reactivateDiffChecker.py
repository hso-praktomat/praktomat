# Generated by Django 1.11.15 on 2018-11-23 00:22
from __future__ import unicode_literals

import checker.basemodels
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0005_task_ordering'),
        ('checker', '0009_isabelle_checker_trusted_to_additional_theories'),
    ]

    operations = [
        migrations.CreateModel(
            name='DiffChecker',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('order', models.IntegerField(help_text='Determines the order in wich the checker will start. Not necessary continuously!')),
                ('public', models.BooleanField(default=True, help_text='Test results are displayed to the submitter.')),
                ('required', models.BooleanField(default=False, help_text='The test must be passed to submit the solution.')),
                ('always', models.BooleanField(default=True, help_text='The test will run on submission time.')),
                ('critical', models.BooleanField(default=False, help_text='If this test fails, do not display further test results.')),
                ('shell_script', checker.basemodels.CheckerFileField(help_text='The shell script whose output for the given input file is compared to the given output file: The substrings JAVA and PROGRAM got replaced by Praktomat determined values.', max_length=500, upload_to=checker.basemodels.get_checkerfile_storage_path)),
                ('input_file', checker.basemodels.CheckerFileField(blank=True, help_text='The file containing the input for the program.', max_length=500, upload_to=checker.basemodels.get_checkerfile_storage_path)),
                ('output_file', checker.basemodels.CheckerFileField(blank=True, help_text='The file containing the output for the program.', max_length=500, upload_to=checker.basemodels.get_checkerfile_storage_path)),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tasks.Task')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
