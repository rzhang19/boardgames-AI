from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from club.models import GroupCreationLog, GroupMembership, SiteSettings


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
    return is_group_admin(user, group)


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
