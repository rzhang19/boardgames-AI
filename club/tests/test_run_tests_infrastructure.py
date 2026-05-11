import importlib.util
import os
import sys
from argparse import Namespace
from unittest.mock import patch

from django.test import TestCase, tag

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def _get_run_tests_module():
    spec = importlib.util.spec_from_file_location(
        'run_tests',
        os.path.join(PROJECT_ROOT, 'scripts', 'run_tests.py'),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_args(**kwargs):
    defaults = {
        'unit': False,
        'integration': False,
        'system': False,
        'fast': False,
        'file': None,
        'serial': False,
        'verbose': 0,
        'games': False,
        'groups': False,
        'events': False,
        'voting': False,
        'users': False,
        'social': False,
        'admin': False,
        'ui': False,
        'site': False,
    }
    defaults.update(kwargs)
    return Namespace(**defaults)


@tag("unit")
class TestSubdirectoryStructure(TestCase):

    def test_unit_directory_exists(self):
        path = os.path.join(PROJECT_ROOT, 'club', 'tests', 'unit')
        self.assertTrue(
            os.path.isdir(path),
            f'Directory {path} does not exist',
        )

    def test_unit_directory_has_init(self):
        path = os.path.join(PROJECT_ROOT, 'club', 'tests', 'unit', '__init__.py')
        self.assertTrue(
            os.path.isfile(path),
            f'File {path} does not exist',
        )

    def test_integration_directory_exists(self):
        path = os.path.join(PROJECT_ROOT, 'club', 'tests', 'integration')
        self.assertTrue(
            os.path.isdir(path),
            f'Directory {path} does not exist',
        )

    def test_integration_directory_has_init(self):
        path = os.path.join(
            PROJECT_ROOT, 'club', 'tests', 'integration', '__init__.py',
        )
        self.assertTrue(
            os.path.isfile(path),
            f'File {path} does not exist',
        )

    def test_system_directory_exists(self):
        path = os.path.join(PROJECT_ROOT, 'club', 'tests', 'system')
        self.assertTrue(
            os.path.isdir(path),
            f'Directory {path} does not exist',
        )

    def test_system_directory_has_init(self):
        path = os.path.join(
            PROJECT_ROOT, 'club', 'tests', 'system', '__init__.py',
        )
        self.assertTrue(
            os.path.isfile(path),
            f'File {path} does not exist',
        )


@tag("unit")
class TestBuildTestCommandNoFlags(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.run_tests = _get_run_tests_module()

    def test_no_flags_produces_basic_command(self):
        args = _make_args()
        cmd = self.run_tests.build_test_command(args)
        self.assertEqual(cmd[0], sys.executable)
        self.assertIn('test', cmd)
        self.assertNotIn('--tag', cmd)

    def test_unit_flag_uses_tag(self):
        args = _make_args(unit=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIn('--tag', cmd)
        idx = cmd.index('--tag')
        self.assertEqual(cmd[idx + 1], 'unit')

    def test_integration_flag_uses_tag(self):
        args = _make_args(integration=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIn('--tag', cmd)
        idx = cmd.index('--tag')
        self.assertEqual(cmd[idx + 1], 'integration')

    def test_system_flag_uses_tag(self):
        args = _make_args(system=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIn('--tag', cmd)
        idx = cmd.index('--tag')
        self.assertEqual(cmd[idx + 1], 'system')

    def test_serial_flag_adds_parallel_1(self):
        args = _make_args(serial=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIn('--parallel', cmd)
        idx = cmd.index('--parallel')
        self.assertEqual(cmd[idx + 1], '1')

    def test_fast_flag_adds_keepdb(self):
        args = _make_args(fast=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIn('--keepdb', cmd)

    def test_verbose_flag_adds_verbosity(self):
        args = _make_args(verbose=2)
        cmd = self.run_tests.build_test_command(args)
        self.assertIn('-v', cmd)

    def test_file_flag_targets_subdirectory_modules(self):
        args = _make_args(file='test_events')
        cmd = self.run_tests.build_test_command(args)
        self.assertIn('club.tests.unit.test_events', cmd)
        self.assertIn('club.tests.integration.test_events', cmd)

    def test_file_flag_with_prefix(self):
        args = _make_args(file='club.tests.test_events')
        cmd = self.run_tests.build_test_command(args)
        self.assertIn('club.tests.test_events', cmd)

    def test_file_flag_without_test_prefix(self):
        args = _make_args(file='events')
        cmd = self.run_tests.build_test_command(args)
        self.assertIn('club.tests.unit.test_events', cmd)
        self.assertIn('club.tests.integration.test_events', cmd)


@tag("unit")
class TestBuildTestCommandAreaFlags(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.run_tests = _get_run_tests_module()

    @patch('os.path.isfile', return_value=True)
    def test_unit_games_targets_unit_test_games(self, mock_isfile):
        args = _make_args(unit=True, games=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIsNotNone(cmd)
        self.assertIn('club.tests.unit.test_games', cmd)
        self.assertNotIn('--tag', cmd)

    @patch('os.path.isfile', return_value=True)
    def test_integration_groups_targets_integration_test_groups(self, mock_isfile):
        args = _make_args(integration=True, groups=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIsNotNone(cmd)
        self.assertIn('club.tests.integration.test_groups', cmd)

    @patch('os.path.isfile', return_value=True)
    def test_games_standalone_targets_all_levels(self, mock_isfile):
        args = _make_args(games=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIsNotNone(cmd)
        self.assertIn('club.tests.unit.test_games', cmd)
        self.assertIn('club.tests.integration.test_games', cmd)

    @patch('os.path.isfile', return_value=True)
    def test_admin_standalone_targets_integration_only(self, mock_isfile):
        args = _make_args(admin=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIsNotNone(cmd)
        self.assertIn('club.tests.integration.test_admin', cmd)
        self.assertNotIn('club.tests.unit.test_admin', cmd)

    @patch('os.path.isfile', return_value=True)
    def test_site_standalone_targets_unit_only(self, mock_isfile):
        args = _make_args(site=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIsNotNone(cmd)
        self.assertIn('club.tests.unit.test_site', cmd)
        self.assertNotIn('club.tests.integration.test_site', cmd)

    @patch('os.path.isfile', return_value=True)
    def test_ui_standalone_targets_integration_only(self, mock_isfile):
        args = _make_args(ui=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIsNotNone(cmd)
        self.assertIn('club.tests.integration.test_ui', cmd)
        self.assertNotIn('club.tests.unit.test_ui', cmd)

    @patch('os.path.isfile', return_value=True)
    def test_multiple_areas_targeted(self, mock_isfile):
        args = _make_args(games=True, groups=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIsNotNone(cmd)
        self.assertIn('club.tests.unit.test_games', cmd)
        self.assertIn('club.tests.integration.test_games', cmd)
        self.assertIn('club.tests.unit.test_groups', cmd)
        self.assertIn('club.tests.integration.test_groups', cmd)

    @patch('os.path.isfile', return_value=True)
    def test_unit_games_with_system_finds_no_target(self, mock_isfile):
        args = _make_args(system=True, games=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIsNone(cmd)

    @patch('os.path.isfile', return_value=False)
    def test_nonexistent_target_returns_none(self, mock_isfile):
        args = _make_args(unit=True, games=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIsNone(cmd)

    @patch('os.path.isfile', return_value=True)
    def test_file_flag_overrides_areas(self, mock_isfile):
        args = _make_args(file='test_events', games=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIsNotNone(cmd)
        self.assertNotIn('club.tests.unit.test_games', cmd)

    @patch('os.path.isfile', return_value=True)
    def test_unit_events_targets_unit_only(self, mock_isfile):
        args = _make_args(unit=True, events=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIsNotNone(cmd)
        self.assertIn('club.tests.unit.test_events', cmd)
        self.assertNotIn('club.tests.integration.test_events', cmd)

    @patch('os.path.isfile', return_value=True)
    def test_integration_voting_targets_integration_only(self, mock_isfile):
        args = _make_args(integration=True, voting=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIsNotNone(cmd)
        self.assertIn('club.tests.integration.test_voting', cmd)
        self.assertNotIn('club.tests.unit.test_voting', cmd)

    @patch('os.path.isfile', return_value=True)
    def test_unit_social_targets_unit_only(self, mock_isfile):
        args = _make_args(unit=True, social=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIsNotNone(cmd)
        self.assertIn('club.tests.unit.test_social', cmd)
        self.assertNotIn('club.tests.integration.test_social', cmd)

    @patch('os.path.isfile', return_value=True)
    def test_unit_users_targets_unit_only(self, mock_isfile):
        args = _make_args(unit=True, users=True)
        cmd = self.run_tests.build_test_command(args)
        self.assertIsNotNone(cmd)
        self.assertIn('club.tests.unit.test_users', cmd)
        self.assertNotIn('club.tests.integration.test_users', cmd)


@tag("unit")
class TestHelpShowsAreaFlags(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.run_tests = _get_run_tests_module()

    def test_help_contains_all_area_flags(self):
        areas = [
            'games', 'groups', 'events', 'voting', 'users',
            'social', 'admin', 'ui', 'site',
        ]
        parser = self.run_tests._create_parser()
        help_text = parser.format_help()
        for area in areas:
            self.assertIn(f'--{area}', help_text)


TESTS_DIR = os.path.join(PROJECT_ROOT, 'club', 'tests')


@tag("unit")
class TestMigratedClassPlacement(TestCase):

    def test_parse_bgg_link_test_in_unit_games(self):
        with open(os.path.join(TESTS_DIR, 'unit', 'test_games.py'), 'r') as f:
            content = f.read()
        self.assertIn('class ParseBggLinkTest', content)

    def test_group_name_validation_test_in_unit_groups(self):
        with open(os.path.join(TESTS_DIR, 'unit', 'test_groups.py'), 'r') as f:
            content = f.read()
        self.assertIn('class GroupNameValidationTest', content)

    def test_game_pool_deduplication_test_in_unit_groups(self):
        with open(os.path.join(TESTS_DIR, 'unit', 'test_groups.py'), 'r') as f:
            content = f.read()
        self.assertIn('class GamePoolDeduplicationTest', content)

    def test_game_pool_availability_test_in_unit_events(self):
        with open(os.path.join(TESTS_DIR, 'unit', 'test_events.py'), 'r') as f:
            content = f.read()
        self.assertIn('class GamePoolAvailabilityTest', content)

    def test_event_game_override_model_test_in_unit_events(self):
        with open(os.path.join(TESTS_DIR, 'unit', 'test_events.py'), 'r') as f:
            content = f.read()
        self.assertIn('class EventGameOverrideModelTest', content)


@tag("unit")
class TestFlatDirectoryCleanup(TestCase):

    FILES_TO_DELETE = [
        'test_admin_confirmation.py',
        'test_auth.py',
        'test_beta_access.py',
        'test_bgg.py',
        'test_bgg_views.py',
        'test_block.py',
        'test_change_password.py',
        'test_email_optional.py',
        'test_ensure_superuser.py',
        'test_event_duration.py',
        'test_event_presence.py',
        'test_events.py',
        'test_feedback.py',
        'test_friendship.py',
        'test_game_ownership.py',
        'test_game_pool.py',
        'test_game_session.py',
        'test_games.py',
        'test_group_games.py',
        'test_group_models.py',
        'test_group_notifications.py',
        'test_group_owned_games.py',
        'test_group_views.py',
        'test_integration.py',
        'test_mobile_responsive.py',
        'test_models.py',
        'test_notifications.py',
        'test_permissions.py',
        'test_private_events.py',
        'test_profile.py',
        'test_random_select.py',
        'test_results_gating.py',
        'test_settings.py',
        'test_site_admin_settings.py',
        'test_site_lockdown.py',
        'test_sticky_header.py',
        'test_superuser_manage.py',
        'test_tag_views.py',
        'test_tags.py',
        'test_theme.py',
        'test_timezone.py',
        'test_unsaved_changes.py',
        'test_users_page.py',
        'test_verified_badge.py',
        'test_verified_icon.py',
        'test_view_only.py',
        'test_vote_validation.py',
        'test_voting.py',
        'test_voting_toggle.py',
    ]

    FILES_TO_KEEP = [
        '__init__.py',
        'test_run_tests_infrastructure.py',
    ]

    def test_no_flat_test_files_remain(self):
        for fname in self.FILES_TO_DELETE:
            path = os.path.join(TESTS_DIR, fname)
            self.assertFalse(
                os.path.exists(path),
                f'Flat test file should be deleted: {fname}'
            )

    def test_expected_files_remain(self):
        for fname in self.FILES_TO_KEEP:
            path = os.path.join(TESTS_DIR, fname)
            self.assertTrue(
                os.path.exists(path),
                f'Expected file to remain: {fname}'
            )

    def test_subdirectories_exist(self):
        for subdir in ['unit', 'integration', 'system']:
            path = os.path.join(TESTS_DIR, subdir)
            self.assertTrue(
                os.path.isdir(path),
                f'Subdirectory should exist: {subdir}/'
            )
