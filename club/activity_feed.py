from django.contrib.auth import get_user_model
from django.db.models import Q

from club.models import ActivityFeedItem, Block, GroupMembership

User = get_user_model()


def record_event_created(event, actor):
    ActivityFeedItem.objects.create(
        activity_type='event_created',
        actor=actor,
        event=event,
        group=event.group,
    )


def record_event_created_batch(first_event, actor, count):
    ActivityFeedItem.objects.create(
        activity_type='event_created',
        actor=actor,
        event=first_event,
        group=first_event.group,
        extra_data={'count': count},
    )


def record_event_updated(event, actor):
    ActivityFeedItem.objects.create(
        activity_type='event_updated',
        actor=actor,
        event=event,
        group=event.group,
    )


def record_member_joined(user, group):
    ActivityFeedItem.objects.create(
        activity_type='member_joined',
        actor=user,
        group=group,
    )


def get_feed_for_user(user, limit=None, days=None):
    user_group_ids = set(
        GroupMembership.objects.filter(
            user=user,
            group__disbanded_at__isnull=True,
        ).values_list('group_id', flat=True)
    )

    admin_org_group_ids = set(
        GroupMembership.objects.filter(
            user=user,
            role__in=['admin', 'organizer'],
            group__disbanded_at__isnull=True,
        ).values_list('group_id', flat=True)
    )

    blocked_ids = Block.get_blocked_user_ids(user)

    qs = ActivityFeedItem.objects.filter(
        Q(
            group_id__in=user_group_ids,
            activity_type__in=['event_created', 'event_updated'],
        ) | Q(
            group_id__in=admin_org_group_ids,
            activity_type='member_joined',
        )
    ).select_related('actor', 'event', 'group')

    if blocked_ids:
        qs = qs.exclude(actor_id__in=blocked_ids)

    qs = qs.exclude(actor__deleted_at__isnull=False)

    if days:
        from django.utils import timezone
        cutoff = timezone.now() - timezone.timedelta(days=days)
        qs = qs.filter(timestamp__gte=cutoff)

    qs = qs.order_by('-timestamp')

    if limit:
        qs = qs[:limit]

    return qs
