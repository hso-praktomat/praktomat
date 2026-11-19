from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0004_task_warning_threshold'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='task',
            options={'ordering': ['submission_date', 'title']},
        ),
    ]
