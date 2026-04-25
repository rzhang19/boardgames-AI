from django.contrib.auth import get_user_model

from club.models import Notification

User = get_user_model()


def unread_notification_count(request):
    if request.user.is_authenticated:
        count = Notification.objects.filter(
            user=request.user, is_read=False
        ).count()
    else:
        count = 0
    badge_display = str(count) if count <= 9 else '9+'
    return {
        'unread_notification_count': count,
        'notification_badge_display': badge_display,
    }


def view_only_status(request):
    return {
        'is_view_only': (
            request.user.is_authenticated
            and getattr(request.user, 'is_view_only', False)
        ),
    }
