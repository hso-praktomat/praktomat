# Generated by Django 2.2.28 on 2022-05-20 19:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('configuration', '0012_settings_deadline_tolerance'),
    ]

    operations = [
        migrations.AddField(
            model_name='settings',
            name='tutors_can_edit_solutions',
            field=models.BooleanField(default=False, help_text='If enabled, tutors can also upload solutions for students in their tutorial.'),
        ),
    ]
