from django.core.management.base import BaseCommand
from django.utils import timezone

from club.models import Notification


class Command(BaseCommand):
    help = 'Delete read notifications older than 30 days'

    def handle(self, *args, **options):
        cutoff = timezone.now() - timezone.timedelta(days=30)
        count, _ = Notification.objects.filter(
            is_read=True,
            created_at__lt=cutoff,
        ).delete()
        self.stdout.write(f'Deleted {count} old read notifications.')
