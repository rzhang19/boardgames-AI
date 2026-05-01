from django.conf import settings
from django.core.management.base import BaseCommand

from club.models import User


class Command(BaseCommand):
    help = 'Ensure a Django superuser exists (create-only; never updates password on redeploys)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Delete and recreate the superuser with the current .env password',
        )

    def handle(self, *args, **options):
        username = settings.SUPERUSER_USERNAME
        password = settings.SUPERUSER_PASSWORD

        if not username or not password:
            self.stdout.write(self.style.WARNING(
                'SUPERUSER_USERNAME and SUPERUSER_PASSWORD must be set. Skipping.'
            ))
            return

        if options['force']:
            deleted, _ = User.objects.filter(username=username).delete()
            if deleted:
                self.stdout.write(self.style.WARNING(
                    f'--force: deleted existing user "{username}".'
                ))

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                f'Superuser "{username}" already exists — skipping password update. '
                f'Use --force to recreate.'
            )
            return

        User.objects.create_superuser(
            username=username,
            password=password,
            is_site_admin=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f'Superuser "{username}" created. '
            f'Log into /admin/ and change the password immediately.'
        ))
