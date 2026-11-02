from utilities.TestSuite import TestCase

from configuration.models import Chunk
from django.template import Context, Template, TemplateSyntaxError
from django.core.cache import cache
from unittest.mock import patch
from datetime import date

from django.db import migrations
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.writer import MigrationWriter
from django.test import SimpleTestCase


class TestHistoricalMigrationContracts(SimpleTestCase):
    def setUp(self) -> None:
        self.loader = MigrationLoader(None)

    def test_initial_configuration_retains_byte_metadata_and_date_default(self) -> None:
        state = self.loader.project_state([('configuration', '0001_initial')])
        fields = state.models['configuration', 'settings'].fields
        self.assertEqual(fields['new_users_via_sso'].help_text, b'If enabled, users previously unknown to the Praktomat can register via sigle sign on (eg. Shibboleth).')
        self.assertEqual(fields['deny_registration_from'].default, date(2222, 1, 1))
        self.assertEqual(len(fields), 12)
        for name, field in fields.items():
            if name != 'id':
                with self.subTest(field=name):
                    self.assertIsInstance(field.help_text, bytes)
        chunk_fields = state.models['configuration', 'chunk'].fields
        self.assertEqual(chunk_fields['key'].help_text, b'A unique name for this chunk of content')
        self.assertEqual(chunk_fields['settings'].help_text, b'Makes it easy to display chunks as inlines in Settings.')
        self.assertEqual(chunk_fields['settings'].default, 1)

    def test_typo_correction_operations_keep_bytes_and_original_order(self) -> None:
        migration = self.loader.disk_migrations['configuration', '0008_typo_corrections']
        names: list[str] = []
        for operation in migration.operations:
            self.assertIsInstance(operation, migrations.AlterField)
            assert isinstance(operation, migrations.AlterField)
            names.append(operation.name)
            self.assertIsInstance(operation.field.help_text, bytes)
        self.assertEqual(names, [
            'accept_all_solutions', 'account_manual_validation', 'acount_activation_days',
            'anonymous_attestation', 'attestation_allow_run_checkers', 'attestation_reply_to',
            'deny_registration_from', 'final_grades_published', 'invisible_attestor', 'new_users_via_sso',
        ])
        self.assertEqual(migration.dependencies, [('configuration', '0007_settings_final_grades_options')])

    def test_historical_author_and_checker_labels_are_not_decoded(self) -> None:
        cases = (
            ('solutions', '0001_initial', 'solution', 'author', b'solution author'),
            ('attestation', '0002_auto_20151006_1416', 'attestation', 'author', b'attestation author'),
            ('checker', '0004_textchecker_and_scalabuilder', 'textchecker', 'choices', b'Select:'),
        )
        for app, name, model, field_name, label in cases:
            with self.subTest(migration=name, model=model):
                state = self.loader.project_state([(app, name)])
                field = state.models[app, model].fields[field_name]
                self.assertEqual(field.verbose_name, label)
                serialized, _ = MigrationWriter.serialize(field)
                self.assertIn(repr(label), serialized)
                if field_name == 'choices':
                    self.assertEqual(field.choices, [
                        (0, b'The text must not be in the solution'),
                        (1, b'The text has to be in the solution'),
                    ])

    def test_tutor_relation_keeps_historical_target_and_options(self) -> None:
        cases: tuple[tuple[str, str, dict[str, str]], ...] = (
            ('0001_initial', 'The tutors in charge of the tutorium.', {}),
            ('0004_typo_corrections', 'The tutors in charge of the tutorial.', {}),
            ('0006_limit_choices_to', 'The tutors in charge of the tutorial.', {'groups__name': 'Tutor'}),
        )
        for name, help_text, limit_choices_to in cases:
            with self.subTest(migration=name):
                state = self.loader.project_state([('accounts', name)])
                field = state.models['accounts', 'tutorial'].fields['tutors']
                _, path, _, kwargs = field.deconstruct()
                self.assertEqual(path, 'django.db.models.ManyToManyField')
                self.assertEqual(kwargs['to'], 'accounts.user')
                self.assertEqual(kwargs['related_name'], 'tutored_tutorials')
                self.assertEqual(kwargs['help_text'], help_text)
                self.assertEqual(kwargs.get('limit_choices_to', {}), limit_choices_to)
                user = state.apps.get_model('accounts', 'User')
                self.assertEqual(user.__module__, '__fake__')
                self.assertIsNot(user, state.apps.get_model('auth', 'User'))

    def test_data_migrations_keep_historical_registry_callbacks(self) -> None:
        cases = (
            ('accounts', '0002_add_groups', 'add_groups'),
            ('accounts', '0003_add_coordinator_group', 'add_coordinator_group'),
            ('configuration', '0002_initial_configuration', 'initial_configuration'),
            ('configuration', '0005_settings_inactive_chunk', 'settings_inactive_chunk'),
            ('configuration', '0006_settings_warning_message_chunk', 'settings_warning_message_chunk'),
            ('configuration', '0017_fix_initial_deadline_tolerance', 'disable_deadline_tolerance'),
        )
        for app, name, callback_name in cases:
            with self.subTest(migration=name):
                migration = self.loader.disk_migrations[app, name]
                self.assertEqual(len(migration.operations), 1)
                operation = migration.operations[0]
                assert isinstance(operation, migrations.RunPython)
                self.assertEqual(getattr(operation.code, '__name__'), callback_name)
                self.assertEqual(getattr(operation.code, '__module__'), f'{app}.migrations.{name}')
                self.assertFalse(operation.reversible)
                serialized, _ = MigrationWriter.serialize(operation)
                self.assertIn(f'{app}.migrations.{name}.{callback_name}', serialized)


class TestChunks(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def test_existing_and_missing_chunks(self) -> None:
        Chunk.objects.create(key='B5-test', content='<strong>content</strong>')
        self.assertEqual(Template('{% load chunks %}{% chunk "B5-test" %}').render(Context()), '<strong>content</strong>')
        self.assertEqual(Template('{% load chunks %}{% chunk "missing" %}').render(Context()), '')

    def test_cached_chunk_and_timeout(self) -> None:
        chunk = Chunk.objects.create(key='B5-cache', content='old')
        template = Template('{% load chunks %}{% chunk "B5-cache" 60 %}')
        self.assertEqual(template.render(Context()), 'old')
        chunk.content = 'new'
        chunk.save()
        self.assertEqual(template.render(Context()), 'old')

    def test_invalid_syntax_is_rejected_at_compile_time(self) -> None:
        for tag in ('chunk', 'chunk unquoted', 'chunk "x" 1 extra', 'chunk "x" invalid'):
            with self.subTest(tag=tag), self.assertRaises(TemplateSyntaxError):
                Template('{% load chunks %}{% ' + tag + ' %}')

    def test_unexpected_database_errors_propagate(self) -> None:
        with patch('configuration.models.Chunk.objects.get', side_effect=RuntimeError('database failed')):
            with self.assertRaisesRegex(RuntimeError, 'database failed'):
                Template('{% load chunks %}{% chunk "uncached" %}').render(Context())

class TestConfiguration(TestCase):
    def setUp(self) -> None:
        pass

    def tearDown(self) -> None:
        pass

    # These ought to be added by the initial migration
    def testWelcomeMessage(self) -> None:
        chunk = Chunk.objects.get(key="Welcome Message")
        self.assertIsNotNone(chunk)

    def testLoginMessage(self) -> None:
        chunk = Chunk.objects.get(key="Login Message")
        self.assertIsNotNone(chunk)
