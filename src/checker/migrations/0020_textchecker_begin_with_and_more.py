# Generated by Django 5.2 on 2025-05-09 12:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('checker', '0019_scriptchecker_arguments'),
    ]

    operations = [
        migrations.AddField(
            model_name='textchecker',
            name='begin_with',
            field=models.CharField(blank=True, default='// #', help_text='Space-separated line prefixes for single-line comments (e.g., // #).', max_length=100),
        ),
        migrations.AddField(
            model_name='textchecker',
            name='ignore_case_and_whitespace',
            field=models.BooleanField(
                default=True, help_text='Ignore case differences and all whitespace (e.g., spaces, tabs) during matching.'),
        ),
        migrations.AddField(
            model_name='textchecker',
            name='multi_block',
            field=models.CharField(blank=True, default='/* */', help_text='Space-separated start and end symbols for block comments (e.g., /* */).', max_length=100),
        ),
        migrations.AddField(
            model_name='textchecker',
            name='skip_lines',
            field=models.BooleanField(default=True, help_text='Skip lines that begin with comment symbols or are inside block comments.'),
        ),
        migrations.AddField(
            model_name='textchecker',
            name='use_regex',
            field=models.BooleanField(default=False, help_text='Treat input as regular expressions.'),
        ),
        migrations.AlterField(
            model_name='textchecker',
            name='text',
            field=models.TextField(help_text='Enter multiple lines, one per pattern.'),
        ),
    ]