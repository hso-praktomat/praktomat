from django.apps.registry import Apps
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db import migrations


def settings_inactive_chunk(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Chunk = apps.get_model("configuration", "Chunk")
    Chunk.objects.get_or_create(key="inactive user")[0].save()



class Migration(migrations.Migration):

    dependencies = [
        ('configuration', '0004_settings_jplag_setting'),
    ]

    operations = [
        migrations.RunPython(settings_inactive_chunk),
    ]
