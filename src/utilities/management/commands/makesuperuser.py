"""
Management utility to make a super a superuser.
"""

from typing import Any

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError, CommandParser


class Command(BaseCommand):
    help: str = 'Make a user a superuser.'

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument('--username', dest='username', default=None,
                            help='Specifies the username of the existing user (mail address for shibboleth users).')

    def handle(self, *args: Any, **options: Any) -> None:
        username = options.get('username', None)
        verbosity = int(options.get('verbosity', 1))

        if not username:
            raise CommandError('Please specify a user with --username')

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as error:
            raise CommandError(f'User "{username}" does not exist') from error

        if verbosity >= 1:
            self.stdout.write(f'Found user {user}\n')
        user.is_staff = True
        user.is_active = True
        user.is_superuser = True
        user.save()
        if verbosity >= 1:
            self.stdout.write('Superuser created successfully.\n')
