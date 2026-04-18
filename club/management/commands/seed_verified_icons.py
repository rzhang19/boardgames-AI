import os

from django.conf import settings
from django.core.management.base import BaseCommand

from club.models import VerifiedIcon

DEFAULT_ICONS = [
    ('Checkmark', 'checkmark.svg'),
    ('Dice', 'dice.svg'),
    ('Meeple', 'meeple.svg'),
    ('Gear', 'gear.svg'),
    ('Rocket', 'rocket.svg'),
    ('Crown', 'crown.svg'),
    ('Star', 'star.svg'),
]


class Command(BaseCommand):
    help = 'Seed default verified icons from static files'

    def handle(self, *args, **options):
        static_dir = os.path.join(settings.BASE_DIR, 'static', 'img', 'verified_icons')
        created_count = 0
        for name, filename in DEFAULT_ICONS:
            if VerifiedIcon.objects.filter(name=name).exists():
                continue
            filepath = os.path.join(static_dir, filename)
            if not os.path.exists(filepath):
                self.stderr.write(self.style.WARNING(f'File not found: {filepath}'))
                continue
            with open(filepath, 'rb') as f:
                icon = VerifiedIcon(name=name)
                icon.image.save(filename, f, save=True)
            created_count += 1
            self.stdout.write(f'Created icon: {name}')
        self.stdout.write(self.style.SUCCESS(f'Seeded {created_count} icons'))
