import shutil
import tempfile
from os.path import dirname as dir
from os.path import join

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help: str = "Copies the demo database into the application support folder"

    def handle(self, *args: object, **options: object) -> None:
        backup_archive: str | None = None
        try:
            application_support_folder = settings.UPLOAD_ROOT
            demo_support_folder = join(dir(dir(dir(dir(dir(dir(__file__)))))), "examples", "PraktomatSupport")

            # create a backup
            archive_base = join(tempfile.gettempdir(), "backup")
            backup_archive = shutil.make_archive(archive_base, "zip", application_support_folder)

            # delete old app support folder
            shutil.rmtree(application_support_folder)

            # copy demo files
            shutil.copytree(demo_support_folder, application_support_folder)

            # copy backup
            shutil.copy(backup_archive, application_support_folder)

            print(
                'Successfully installed demo files and database. Backup of old files in "{}"'.format(
                    join(application_support_folder, "backup.zip")
                )
            )

        except OSError as error:
            message = "An ERROR occurred while installing the demo files."
            if backup_archive is None:
                message += " No backup archive was created."
            else:
                message += f" A backup of your files can be found here: {backup_archive}"
            raise CommandError(message) from error
