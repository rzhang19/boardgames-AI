from django.core.management.base import BaseCommand
from django.utils import timezone

from club.models import Group


class Command(BaseCommand):
    help = 'Delete disbanded groups whose 30-day grace period has expired'

    def handle(self, *args, **options):
        cutoff = timezone.now()
        groups = []
        for group in Group.objects.filter(disbanded_at__isnull=False):
            if group.is_grace_period_expired:
                groups.append(group)

        count = len(groups)
        for group in groups:
            group.delete()

        self.stdout.write(f'Deleted {count} expired disbanded group(s)')
