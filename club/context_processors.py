from django.contrib.auth import get_user_model

from club.models import Notification, SiteSettings

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


def site_lockdown_status(request):
    site_settings = SiteSettings.load()
    return {
        'site_lockdown_active': site_settings.site_lockdown_active,
    }


def user_theme(request):
    if request.user.is_authenticated:
        return {'user_theme': request.user.theme}
    return {'user_theme': 'system'}
