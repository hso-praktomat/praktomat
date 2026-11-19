from django.apps.registry import Apps
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db import migrations

def settings_warning_message_chunk(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Chunk = apps.get_model("configuration", "Chunk")
    Chunk.objects.get_or_create(key="warning message")[0].save()



class Migration(migrations.Migration):

    dependencies = [
        ('configuration', '0005_settings_inactive_chunk'),
    ]

    operations = [
        migrations.RunPython(settings_warning_message_chunk),
    ]
