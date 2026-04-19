from django.contrib.auth import get_user_model

from club.models import BoardGame, Notification

User = get_user_model()


def generate_missing_complexity_notifications(user):
    games = BoardGame.objects.filter(owner=user, complexity__isnull=True)
    existing_urls = set(
        Notification.objects.filter(
            user=user,
            notification_type='missing_complexity',
        ).values_list('url', flat=True)
    )
    for game in games:
        url = f'/games/{game.pk}/edit/'
        if url in existing_urls:
            continue
        Notification.objects.create(
            user=user,
            message=f'"{game.name}" is missing complexity information.',
            url=url,
            url_label='Edit Game',
            notification_type='missing_complexity',
        )


def generate_missing_max_players_notifications(user):
    games = BoardGame.objects.filter(owner=user, max_players__isnull=True)
    existing_urls = set(
        Notification.objects.filter(
            user=user,
            notification_type='missing_max_players',
        ).values_list('url', flat=True)
    )
    for game in games:
        url = f'/games/{game.pk}/edit/'
        if url in existing_urls:
            continue
        Notification.objects.create(
            user=user,
            message=f'"{game.name}" is missing max player count.',
            url=url,
            url_label='Edit Game',
            notification_type='missing_max_players',
        )
