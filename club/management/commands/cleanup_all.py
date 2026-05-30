from django.core.management import call_command
from django.core.management.base import BaseCommand


SUBCOMMANDS = [
    'cleanup_temporary_games',
    'cleanup_deleted_users',
    'cleanup_disbanded_groups',
    'cleanup_notifications',
]


class Command(BaseCommand):
    help = 'Run all cleanup commands: temporary games, deleted users, disbanded groups, and old notifications'

    def handle(self, *args, **options):
        self.stdout.write('Running all cleanup commands...\n')

        results = []
        for cmd in SUBCOMMANDS:
            try:
                call_command(cmd, stdout=self.stdout)
                results.append((cmd, True))
            except Exception as e:
                self.stderr.write(f'{cmd}: {e}')
                results.append((cmd, False))

        failed = [cmd for cmd, ok in results if not ok]
        summary = ', '.join(
            f'{cmd}: {"OK" if ok else "FAILED"}'
            for cmd, ok in results
        )
        self.stdout.write(f'\ncleanup_all completed: {summary}\n')

        if failed:
            self.stdout.write(self.style.WARNING(
                f'Failed commands: {", ".join(failed)}'
            ))
