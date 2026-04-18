import hashlib
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


def _file_hash(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


class Command(BaseCommand):
    help = 'Seed default verified icons from static files'

    def handle(self, *args, **options):
        static_dir = os.path.join(settings.BASE_DIR, 'static', 'img', 'verified_icons')
        created_count = 0
        updated_count = 0
        for name, filename in DEFAULT_ICONS:
            filepath = os.path.join(static_dir, filename)
            if not os.path.exists(filepath):
                self.stderr.write(self.style.WARNING(f'File not found: {filepath}'))
                continue
            source_hash = _file_hash(filepath)
            existing = VerifiedIcon.objects.filter(name=name).first()
            if existing:
                existing_hash = _file_hash(existing.image.path)
                if existing_hash != source_hash:
                    with open(filepath, 'rb') as f:
                        existing.image.save(filename, f, save=True)
                    updated_count += 1
                    self.stdout.write(f'Updated icon: {name}')
                continue
            with open(filepath, 'rb') as f:
                icon = VerifiedIcon(name=name)
                icon.image.save(filename, f, save=True)
            created_count += 1
            self.stdout.write(f'Created icon: {name}')
        self.stdout.write(self.style.SUCCESS(
            f'Seeded {created_count} new, updated {updated_count} icons'
        ))
