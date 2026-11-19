from datetime import timedelta
from django.apps.registry import Apps
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db import migrations


def disable_deadline_tolerance(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
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
