from datetime import timedelta
from django.db import migrations, models

def disable_deadline_tolerance(apps, schema_editor):
    Settings = apps.get_model("configuration", "Settings")
    conf = Settings.objects.get(id=1)
    conf.deadline_tolerance = timedelta(hours=0)
    conf.save()


class Migration(migrations.Migration):

    dependencies = [
        ('configuration', '0016_remove_settings_hide_solutions_of_expired_tasks'),
    ]

    operations = [
        migrations.RunPython(disable_deadline_tolerance),
    ]
