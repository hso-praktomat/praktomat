# -*- coding: utf-8 -*-
# Generated by Django 1.11.28 on 2020-03-08 10:23
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('checker', '0010_activateAutoAttestChecker'),
        ('checker', '0012_auto_20190408_1427'),
        ('tasks','0008_on_delete_set_null'),
    ]

    operations = [
        migrations.AlterField(
            model_name='autoattestchecker',
            name='order',
            field=models.IntegerField(help_text='Determines the order in which the checker will start. Not necessary continuously!'),
        ),
        migrations.AlterField(
            model_name='autoattestchecker',
            name='author',
            field=models.ForeignKey(blank=True, limit_choices_to={'groups__name': 'Tutor'}, null=True, on_delete=django.db.models.deletion.SET_NULL, to='accounts.User', verbose_name='attestation author'),
        ),
    ]
