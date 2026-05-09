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

    def test_file_flag_targets_flat_module(self):
        args = _make_args(file='test_events')
        cmd = self.run_tests.build_test_command(args)
        self.assertIn('club.tests.test_events', cmd)

    def test_file_flag_with_prefix(self):
        args = _make_args(file='club.tests.test_events')
        cmd = self.run_tests.build_test_command(args)
        self.assertIn('club.tests.test_events', cmd)

    def test_file_flag_without_test_prefix(self):
        args = _make_args(file='events')
        cmd = self.run_tests.build_test_command(args)
        self.assertIn('club.tests.test_events', cmd)


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
        self.assertIn('club.tests.test_events', cmd)
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
