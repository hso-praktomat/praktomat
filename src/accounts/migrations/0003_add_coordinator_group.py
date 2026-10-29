from django.apps.registry import Apps
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db import migrations


def add_coordinator_group(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Group = apps.get_model("auth", "Group")
    coordinator = Group.objects.get_or_create(name="Coordinator")[0]
    coordinator.save()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_add_groups'),
    ]

    operations = [
        migrations.RunPython(add_coordinator_group)
    ]
