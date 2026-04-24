from django.contrib.auth import get_user_model
from django.db.models import Q

from club.models import BoardGame, GroupMembership, Notification

User = get_user_model()


def _notify_user(user, message, url, url_label, notification_type):
    Notification.objects.create(
        user=user,
        message=message,
        url=url,
        url_label=url_label,
        notification_type=notification_type,
    )


def _notify_group_members(group, message, url, url_label, notification_type, exclude_user=None):
    if group.is_disbanded:
        return
    memberships = GroupMembership.objects.filter(group=group).select_related('user')
    for m in memberships:
        if exclude_user and m.user_id == exclude_user.pk:
            continue
        _notify_user(m.user, message, url, url_label, notification_type)


def _notify_group_admins(group, message, url, url_label, notification_type, exclude_user=None):
    if group.is_disbanded:
        return
    admin_memberships = GroupMembership.objects.filter(
        group=group, role='admin',
    ).select_related('user')
    for m in admin_memberships:
        if exclude_user and m.user_id == exclude_user.pk:
            continue
        _notify_user(m.user, message, url, url_label, notification_type)


def _notify_site_admins_and_superusers(message, url, url_label, notification_type, exclude_user=None):
    recipients = User.objects.filter(Q(is_site_admin=True) | Q(is_superuser=True))
    for recipient in recipients:
        if exclude_user and recipient.pk == exclude_user.pk:
            continue
        _notify_user(recipient, message, url, url_label, notification_type)


# ---------------------------------------------------------------------------
# Personal notifications (sent to affected user)
# ---------------------------------------------------------------------------

def notify_group_join_approved(user, group, actor):
    _notify_user(
        user,
        f'Your join request for "{group.name}" was approved by {actor.username}.',
        f'/groups/{group.slug}/',
        'View Group',
        'group_join_approved',
    )


def notify_group_join_rejected(user, group, actor):
    _notify_user(
        user,
        f'Your join request for "{group.name}" was rejected by {actor.username}.',
        '/groups/',
        'Browse Groups',
        'group_join_rejected',
    )


def notify_group_promoted_organizer(user, group, actor):
    _notify_user(
        user,
        f'You were promoted to organizer in "{group.name}" by {actor.username}.',
        f'/groups/{group.slug}/',
        'View Group',
        'group_promoted_organizer',
    )


def notify_group_promoted_admin(user, group, actor):
    _notify_user(
        user,
        f'You were promoted to admin in "{group.name}" by {actor.username}.',
        f'/groups/{group.slug}/',
        'View Group',
        'group_promoted_admin',
    )


def notify_group_demoted_organizer(user, group, actor):
    _notify_user(
        user,
        f'You were demoted to organizer in "{group.name}" by {actor.username}.',
        f'/groups/{group.slug}/',
        'View Group',
        'group_demoted_organizer',
    )


def notify_group_demoted_member(user, group, actor):
    _notify_user(
        user,
        f'You were demoted to member in "{group.name}" by {actor.username}.',
        f'/groups/{group.slug}/',
        'View Group',
        'group_demoted_member',
    )


def notify_group_removed(user, group, actor):
    _notify_user(
        user,
        f'You were removed from "{group.name}" by {actor.username}.',
        '/groups/',
        'Browse Groups',
        'group_removed',
    )


# ---------------------------------------------------------------------------
# All-member notifications (sent to every group member)
# ---------------------------------------------------------------------------

def notify_group_event_created(group, event, actor, count=1):
    if count > 1:
        message = f'{count} new events created in "{group.name}" from recurring schedule'
    else:
        message = f'New event in "{group.name}": "{event.title}"'
    _notify_group_members(
        group,
        message,
        f'/groups/{event.group.slug}/events/{event.pk}/',
        'View Event',
        'group_event_created',
        exclude_user=actor,
    )


def notify_group_event_updated(group, event, actor):
    _notify_group_members(
        group,
        f'Event updated in "{group.name}": "{event.title}"',
        f'/groups/{event.group.slug}/events/{event.pk}/',
        'View Event',
        'group_event_updated',
        exclude_user=actor,
    )


def notify_group_voting_ended(group, event, actor):
    _notify_group_members(
        group,
        f'Voting ended for "{event.title}" in "{group.name}"',
        f'/groups/{event.group.slug}/events/{event.pk}/',
        'View Event',
        'group_voting_ended',
    )


def notify_group_voting_resumed(group, event, actor):
    _notify_group_members(
        group,
        f'Voting resumed for "{event.title}" in "{group.name}"',
        f'/groups/{event.group.slug}/events/{event.pk}/',
        'View Event',
        'group_voting_resumed',
    )


# ---------------------------------------------------------------------------
# Admin-only notifications (sent to group admins)
# ---------------------------------------------------------------------------

def notify_group_member_joined(group, joined_user, method='open join'):
    _notify_group_admins(
        group,
        f'New member joined "{group.name}": {joined_user.username} (via {method})',
        f'/groups/{group.slug}/members/',
        'View Members',
        'group_member_joined',
    )


def notify_group_join_request(group, requesting_user):
    _notify_group_admins(
        group,
        f'New join request for "{group.name}" from {requesting_user.username}',
        f'/groups/{group.slug}/join-requests/',
        'Review Request',
        'group_join_request',
    )


def notify_group_member_left(group, left_user):
    _notify_group_admins(
        group,
        f'{left_user.username} left "{group.name}"',
        f'/groups/{group.slug}/members/',
        'View Members',
        'group_member_left',
    )


def notify_group_invite_created(group, actor):
    _notify_group_admins(
        group,
        f'Invite link created for "{group.name}" by {actor.username}',
        f'/groups/{group.slug}/',
        'View Group',
        'group_invite_created',
        exclude_user=actor,
    )


def notify_group_settings_changed(group, actor):
    _notify_group_admins(
        group,
        f'Group settings changed for "{group.name}" by {actor.username}',
        f'/groups/{group.slug}/',
        'View Group',
        'group_settings_changed',
        exclude_user=actor,
    )


def notify_group_grace_period(group):
    _notify_site_admins_and_superusers(
        f'"{group.name}" has entered grace period (approaching disbandment)',
        f'/groups/{group.slug}/',
        'View Group',
        'group_grace_period',
    )


def notify_group_restored(group, actor):
    _notify_site_admins_and_superusers(
        f'"{group.name}" has been restored by {actor.username}',
        f'/groups/{group.slug}/',
        'View Group',
        'group_restored',
        exclude_user=actor,
    )


# ---------------------------------------------------------------------------
# Existing notification functions (unchanged)
# ---------------------------------------------------------------------------

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
