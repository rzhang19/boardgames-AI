#!/usr/bin/env python
import argparse
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(
        description='Run the board game club test suite with parallelism by default.'
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
    args = parser.parse_args()

    cmd = [sys.executable, 'manage.py', 'test']

    if args.serial:
        cmd.append('--parallel')
        cmd.append('1')

    if args.fast:
        cmd.append('--keepdb')

    verbosity = min(args.verbose, 2)
    if verbosity:
        cmd.append(f'-v')
        cmd.append(str(verbosity))

    tags = []
    if args.unit:
        tags.append('unit')
    if args.integration:
        tags.append('integration')
    if args.system:
        tags.append('system')

    for tag in tags:
        cmd.extend(['--tag', tag])

    if args.file:
        name = args.file
        if not name.startswith('club.tests.'):
            if name.startswith('test_'):
                name = f'club.tests.{name}'
            elif not name.startswith('club'):
                name = f'club.tests.test_{name}'
        cmd.append(name)

    print(f'Running: {" ".join(cmd)}')
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()
