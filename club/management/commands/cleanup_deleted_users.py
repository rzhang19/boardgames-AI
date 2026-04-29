from django.core.management.base import BaseCommand
from django.utils import timezone

from club.models import User


class Command(BaseCommand):
    help = 'Permanently delete users whose 30-day soft-delete grace period has expired'

    def handle(self, *args, **options):
        now = timezone.now()
        users = []
        for user in User.objects.filter(deleted_at__isnull=False):
            if user.is_deletion_grace_period_expired:
                users.append(user)

        count = len(users)
        for user in users:
            user.delete()

        self.stdout.write(f'Permanently deleted {count} expired user(s)')
