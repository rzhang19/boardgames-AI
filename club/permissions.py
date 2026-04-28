from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from datetime import timedelta

from club.models import GroupCreationLog, GroupMembership, PrivateEventCreationLog, SiteSettings


def is_group_admin(user, group):
    if not user.is_authenticated:
        return False
    return GroupMembership.objects.filter(
        user=user, group=group, role='admin',
    ).exists()


def is_group_organizer(user, group):
    if not user.is_authenticated:
        return False
    return GroupMembership.objects.filter(
        user=user, group=group, role__in=['admin', 'organizer'],
    ).exists()


def is_group_member(user, group):
    if not user.is_authenticated:
        return False
    return GroupMembership.objects.filter(
        user=user, group=group,
    ).exists()


def can_create_event(user, group):
    return is_group_organizer(user, group)


def can_manage_members(user, group):
    return is_group_admin(user, group)


def can_edit_group_settings(user, group):
    # NOTE: To open individual settings actions to organizers in the future,
    # create per-action permission functions (e.g., can_edit_group_name,
    # can_edit_group_join_policy) that check for organizer role, and call them
    # from the group_settings view instead of this single gate function.
    # The group_settings view should then conditionally show/disable fields
    # based on the specific action permissions.
    if not user.is_authenticated:
        return False
    return GroupMembership.objects.filter(
        user=user, group=group, role='admin',
    ).exists()


def can_view_group(user, group):
    if not user.is_authenticated:
        return group.discoverable
    return (
        group.discoverable
        or is_group_member(user, group)
        or user.is_superuser
        or user.is_site_admin
    )


def can_view_votes(user, group):
    return is_group_member(user, group)


def can_create_group(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_site_admin:
        return True
    from django.utils import timezone
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(days=7)
    recent_count = GroupCreationLog.objects.filter(
        user=user,
        created_at__gte=cutoff,
    ).count()
    return recent_count < 2 + user.group_creation_override


def can_delete_group(user):
    if user.is_superuser:
        return True
    if user.is_site_admin:
        return SiteSettings.load().allow_site_admins_to_delete_groups
    return False


def can_restore_group(user):
    return user.is_superuser or user.is_site_admin


def group_admin_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        group = kwargs.get('group')
        if group is None:
            from django.shortcuts import get_object_or_404
            from club.models import Group
            group = get_object_or_404(Group, slug=kwargs.get('slug'))
        if not is_group_admin(request.user, group):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def group_organizer_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        group = kwargs.get('group')
        if group is None:
            from django.shortcuts import get_object_or_404
            from club.models import Group
            group = get_object_or_404(Group, slug=kwargs.get('slug'))
        if not is_group_organizer(request.user, group):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def group_member_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        group = kwargs.get('group')
        if group is None:
            from django.shortcuts import get_object_or_404
            from club.models import Group
            group = get_object_or_404(Group, slug=kwargs.get('slug'))
        if not is_group_member(request.user, group):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Private event permissions
# ---------------------------------------------------------------------------

PRIVATE_EVENT_RATE_LIMIT = 5
PRIVATE_EVENT_RATE_WINDOW_HOURS = 168


def can_create_private_event(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_site_admin:
        return True
    if not user.email_verified:
        return False
    cutoff = timezone.now() - timedelta(hours=PRIVATE_EVENT_RATE_WINDOW_HOURS)
    recent_count = PrivateEventCreationLog.objects.filter(
        user=user,
        created_at__gte=cutoff,
    ).count()
    return recent_count < PRIVATE_EVENT_RATE_LIMIT


def can_view_private_event(user, event):
    if event.group_id is not None:
        return None
    if not user.is_authenticated:
        if event.privacy == 'public':
            return True
        if event.privacy == 'invite_only_public':
            return True
        return False
    if user.is_superuser or user.is_site_admin:
        return True
    if event.created_by == user:
        return True
    if event.additional_organizers.filter(pk=user.pk).exists():
        return True
    from club.models import EventAttendance
    if EventAttendance.objects.filter(user=user, event=event).exists():
        return True
    if event.privacy == 'public':
        return True
    if event.privacy == 'invite_only_public':
        return True
    from club.models import EventInvite
    if EventInvite.objects.filter(user=user, event=event).exists():
        return True
    return False


def can_rsvp_private_event(user, event):
    if event.group_id is not None:
        return None
    if not user.is_authenticated:
        return False
    if event.created_by == user:
        return True
    if event.additional_organizers.filter(pk=user.pk).exists():
        return True
    if user.is_superuser or user.is_site_admin:
        return True
    if event.privacy == 'public':
        return True
    from club.models import EventInvite
    if EventInvite.objects.filter(user=user, event=event).exists():
        return True
    return False


def can_invite_to_event(user, event, target_user=None):
    if not user.is_authenticated:
        return False
    if event.created_by == user:
        return True
    if not event.is_organizer(user):
        return False
    if event.allow_invite_others == 'nobody':
        return False
    if event.allow_invite_others == 'anyone':
        return True
    if event.allow_invite_others == 'friends_only':
        if target_user is None:
            return True
        from club.models import Friendship
        return Friendship.are_friends(user, target_user)
    return False


def can_edit_private_event_settings(user, event):
    if not user.is_authenticated:
        return False
    if event.group_id is not None:
        return False
    return event.created_by == user
