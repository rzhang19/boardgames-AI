#!/usr/bin/env python
import argparse
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

AREA_MODULE_MAP = {
    'games': 'test_games',
    'groups': 'test_groups',
    'events': 'test_events',
    'voting': 'test_voting',
    'users': 'test_users',
    'social': 'test_social',
    'admin': 'test_admin',
    'ui': 'test_ui',
    'site': 'test_site',
    'tags': 'test_tags',
    'activity': 'test_activity',
}

AREA_LEVELS = {
    'games': ['unit', 'integration'],
    'groups': ['unit', 'integration'],
    'events': ['unit', 'integration'],
    'voting': ['unit', 'integration'],
    'users': ['unit', 'integration'],
    'social': ['unit', 'integration'],
    'admin': ['integration'],
    'ui': ['integration'],
    'site': ['unit'],
    'tags': ['unit'],
    'activity': ['unit', 'integration'],
}


def _create_parser():
    parser = argparse.ArgumentParser(
        description=(
            'Run the board game club test suite. '
            'Default: 4 parallel workers. Use --serial for sequential (1 worker).'
        ),
    )
    parser.add_argument(
        '--unit', action='store_true',
        help='Run only unit tests (tagged @tag("unit"))',
    )
    parser.add_argument(
        '--integration', action='store_true',
        help='Run only integration tests (tagged @tag("integration"))',
    )
    parser.add_argument(
        '--system', action='store_true',
        help='Run only system tests (tagged @tag("system"))',
    )
    parser.add_argument(
        '--fast', action='store_true',
        help='Reuse the test database (adds --keepdb)',
    )
    parser.add_argument(
        '--file',
        help='Run a single test file, e.g. --file test_events',
    )
    parser.add_argument(
        '--serial', action='store_true',
        help='Disable parallelism (run tests sequentially)',
    )
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help='Increase verbosity (-v, -vv)',
    )
    for area in AREA_MODULE_MAP:
        parser.add_argument(
            f'--{area}', action='store_true',
            help=f'Run {area}-related tests from the subdirectory structure',
        )
    return parser


def _resolve_file_label(name):
    if name.startswith('club.tests.'):
        return [name]
    subdirs = ['unit', 'integration', 'system']
    if name.startswith('test_'):
        base = name
    else:
        base = f'test_{name}'
    targets = []
    for subdir in subdirs:
        module_path = f'club.tests.{subdir}.{base}'
        file_path = os.path.join(BASE_DIR, 'club', 'tests', subdir, f'{base}.py')
        if os.path.isfile(file_path):
            targets.append(module_path)
    if not targets:
        targets.append(f'club.tests.{base}')
    return targets


def build_test_command(args):
    cmd = [sys.executable, 'manage.py', 'test']

    if args.serial:
        cmd.extend(['--parallel', '1'])

    if args.fast:
        cmd.append('--keepdb')

    verbosity = min(args.verbose, 2)
    if verbosity:
        cmd.extend(['-v', str(verbosity)])

    if args.file:
        cmd.extend(_resolve_file_label(args.file))
        return cmd

    active_areas = [
        area for area in AREA_MODULE_MAP if getattr(args, area, False)
    ]

    if active_areas:
        specified_levels = []
        if args.unit:
            specified_levels.append('unit')
        if args.integration:
            specified_levels.append('integration')
        if args.system:
            specified_levels.append('system')

        targets = []
        for area in active_areas:
            module_name = AREA_MODULE_MAP[area]
            area_levels = AREA_LEVELS[area]
            search_levels = (
                [l for l in specified_levels if l in area_levels]
                if specified_levels
                else area_levels
            )
            for level in search_levels:
                module_path = f'club.tests.{level}.{module_name}'
                file_path = os.path.join(
                    BASE_DIR, 'club', 'tests', level,
                    f'{module_name}.py',
                )
                if os.path.isfile(file_path):
                    targets.append(module_path)

        if not targets:
            return None

        cmd.extend(targets)
        return cmd

    tags = []
    if args.unit:
        tags.append('unit')
    if args.integration:
        tags.append('integration')
    if args.system:
        tags.append('system')

    for tag in tags:
        cmd.extend(['--tag', tag])

    return cmd


def main():
    parser = _create_parser()
    args = parser.parse_args()

    cmd = build_test_command(args)
    if cmd is None:
        print('No test files found for the specified criteria.')
        sys.exit(0)

    print(f'Running: {" ".join(cmd)}')
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()
