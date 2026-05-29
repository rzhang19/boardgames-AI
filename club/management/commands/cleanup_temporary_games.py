from django.core.management.base import BaseCommand
from django.utils import timezone

from club.models import BoardGame, GameOwnershipProposal


class Command(BaseCommand):
    help = 'Delete temporary games older than 7 days with no pending proposals and expire stale proposals'

    def handle(self, *args, **options):
        now = timezone.now()
        cutoff = now - timezone.timedelta(hours=168)

        expired_proposals = GameOwnershipProposal.objects.filter(
            status='pending',
            expires_at__lt=now,
        )
        expired_count = expired_proposals.update(status='expired')

        games_with_pending = set(
            GameOwnershipProposal.objects.filter(
                status='pending',
            ).values_list('board_game_id', flat=True)
        )

        games_to_delete = BoardGame.objects.filter(
            is_temporary=True,
            created_at__lt=cutoff,
        ).exclude(pk__in=games_with_pending)

        delete_count = games_to_delete.count()
        games_to_delete.delete()

        self.stdout.write(
            f'Expired {expired_count} proposal(s), deleted {delete_count} temporary game(s)'
        )
