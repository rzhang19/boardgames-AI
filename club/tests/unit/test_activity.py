from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.utils import timezone

from club.activity_feed import (
    get_feed_for_user,
    record_event_created,
    record_event_created_batch,
    record_event_updated,
    record_member_joined,
)
from club.models import (
    ActivityFeedItem,
    Block,
    Event,
    Group,
    GroupMembership,
)

User = get_user_model()


def _create_user(username, password='testpass123', **kwargs):
    return User.objects.create_user(username=username, password=password, **kwargs)


def _create_group(creator, name='Test Group'):
    group = Group.objects.create(name=name, created_by=creator)
    GroupMembership.objects.create(user=creator, group=group, role='admin')
    return group


def _create_event(creator, group, title='Test Event', days_ahead=7):
    event_date = timezone.now() + timedelta(days=days_ahead)
    return Event.objects.create(
        title=title,
        date=event_date,
        created_by=creator,
        group=group,
        voting_deadline=event_date,
    )


@tag("unit")
class ActivityFeedItemModelTest(TestCase):

    def setUp(self):
        self.user = _create_user('actor')
        self.group = _create_group(self.user)
        self.event = _create_event(self.user, self.group)

    def test_create_event_activity_item(self):
        item = ActivityFeedItem.objects.create(
            activity_type='event_created',
            actor=self.user,
            event=self.event,
            group=self.group,
        )
        self.assertEqual(item.activity_type, 'event_created')
        self.assertEqual(item.actor, self.user)
        self.assertEqual(item.event, self.event)
        self.assertEqual(item.group, self.group)
        self.assertIsNotNone(item.timestamp)

    def test_create_member_joined_activity_item(self):
        new_user = _create_user('newmember')
        item = ActivityFeedItem.objects.create(
            activity_type='member_joined',
            actor=new_user,
            group=self.group,
        )
        self.assertEqual(item.activity_type, 'member_joined')
        self.assertEqual(item.actor, new_user)
        self.assertIsNone(item.event)
        self.assertEqual(item.group, self.group)

    def test_extra_data_defaults_to_empty_dict(self):
        item = ActivityFeedItem.objects.create(
            activity_type='event_created',
            actor=self.user,
            event=self.event,
            group=self.group,
        )
        self.assertEqual(item.extra_data, {})

    def test_extra_data_stores_batch_count(self):
        item = ActivityFeedItem.objects.create(
            activity_type='event_created',
            actor=self.user,
            event=self.event,
            group=self.group,
            extra_data={'count': 5},
        )
        self.assertEqual(item.extra_data['count'], 5)

    def test_ordering_is_newest_first(self):
        item1 = ActivityFeedItem.objects.create(
            activity_type='event_created',
            actor=self.user,
            event=self.event,
            group=self.group,
        )
        item2 = ActivityFeedItem.objects.create(
            activity_type='event_updated',
            actor=self.user,
            event=self.event,
            group=self.group,
        )
        items = list(ActivityFeedItem.objects.all())
        self.assertEqual(items[0], item2)
        self.assertEqual(items[1], item1)

    def test_str_representation(self):
        item = ActivityFeedItem.objects.create(
            activity_type='event_created',
            actor=self.user,
            event=self.event,
            group=self.group,
        )
        self.assertIn('event_created', str(item))
        self.assertIn(self.user.username, str(item))


@tag("unit")
class RecordEventCreatedTest(TestCase):

    def setUp(self):
        self.user = _create_user('creator')
        self.group = _create_group(self.user)
        self.event = _create_event(self.user, self.group)

    def test_creates_activity_item(self):
        record_event_created(self.event, self.user)
        self.assertEqual(ActivityFeedItem.objects.count(), 1)
        item = ActivityFeedItem.objects.first()
        self.assertEqual(item.activity_type, 'event_created')
        self.assertEqual(item.actor, self.user)
        self.assertEqual(item.event, self.event)
        self.assertEqual(item.group, self.group)

    def test_extra_data_is_empty(self):
        record_event_created(self.event, self.user)
        item = ActivityFeedItem.objects.first()
        self.assertEqual(item.extra_data, {})


@tag("unit")
class RecordEventCreatedBatchTest(TestCase):

    def setUp(self):
        self.user = _create_user('creator')
        self.group = _create_group(self.user)
        self.event = _create_event(self.user, self.group)

    def test_creates_activity_item_with_count(self):
        record_event_created_batch(self.event, self.user, count=5)
        self.assertEqual(ActivityFeedItem.objects.count(), 1)
        item = ActivityFeedItem.objects.first()
        self.assertEqual(item.activity_type, 'event_created')
        self.assertEqual(item.extra_data, {'count': 5})
        self.assertEqual(item.event, self.event)


@tag("unit")
class RecordEventUpdatedTest(TestCase):

    def setUp(self):
        self.user = _create_user('editor')
        self.group = _create_group(self.user)
        self.event = _create_event(self.user, self.group)

    def test_creates_activity_item(self):
        record_event_updated(self.event, self.user)
        self.assertEqual(ActivityFeedItem.objects.count(), 1)
        item = ActivityFeedItem.objects.first()
        self.assertEqual(item.activity_type, 'event_updated')
        self.assertEqual(item.actor, self.user)
        self.assertEqual(item.event, self.event)
        self.assertEqual(item.group, self.group)


@tag("unit")
class RecordMemberJoinedTest(TestCase):

    def setUp(self):
        self.admin = _create_user('admin')
        self.group = _create_group(self.admin)

    def test_creates_activity_item(self):
        new_member = _create_user('newmember')
        record_member_joined(new_member, self.group)
        self.assertEqual(ActivityFeedItem.objects.count(), 1)
        item = ActivityFeedItem.objects.first()
        self.assertEqual(item.activity_type, 'member_joined')
        self.assertEqual(item.actor, new_member)
        self.assertEqual(item.group, self.group)
        self.assertIsNone(item.event)


@tag("unit")
class GetFeedForUserVisibilityTest(TestCase):

    def setUp(self):
        self.member = _create_user('member')
        self.admin = _create_user('groupadmin')
        self.outsider = _create_user('outsider')
        self.group = Group.objects.create(name='Feed Group', created_by=self.admin)
        GroupMembership.objects.create(user=self.admin, group=self.group, role='admin')
        GroupMembership.objects.create(user=self.member, group=self.group, role='member')

        self.event = _create_event(self.admin, self.group)

    def test_event_created_visible_to_group_member(self):
        record_event_created(self.event, self.admin)
        feed = get_feed_for_user(self.member)
        self.assertEqual(feed.count(), 1)

    def test_event_created_not_visible_to_outsider(self):
        record_event_created(self.event, self.admin)
        feed = get_feed_for_user(self.outsider)
        self.assertEqual(feed.count(), 0)

    def test_event_updated_visible_to_group_member(self):
        record_event_updated(self.event, self.admin)
        feed = get_feed_for_user(self.member)
        self.assertEqual(feed.count(), 1)

    def test_member_joined_visible_to_group_admin(self):
        new_member = _create_user('newuser')
        record_member_joined(new_member, self.group)
        feed = get_feed_for_user(self.admin)
        self.assertEqual(feed.count(), 1)

    def test_member_joined_not_visible_to_regular_member(self):
        new_member = _create_user('newuser')
        record_member_joined(new_member, self.group)
        feed = get_feed_for_user(self.member)
        self.assertEqual(feed.count(), 0)

    def test_member_joined_visible_to_organizer(self):
        organizer = _create_user('organizer')
        GroupMembership.objects.create(user=organizer, group=self.group, role='organizer')
        new_member = _create_user('newuser')
        record_member_joined(new_member, self.group)
        feed = get_feed_for_user(organizer)
        self.assertEqual(feed.count(), 1)


@tag("unit")
class GetFeedForUserFilteringTest(TestCase):

    def setUp(self):
        self.member = _create_user('member')
        self.admin = _create_user('admin')
        self.group = _create_group(self.admin)
        GroupMembership.objects.create(user=self.member, group=self.group, role='member')

    def test_excludes_blocked_users(self):
        blocked_user = _create_user('blocked')
        event = _create_event(blocked_user, self.group)
        record_event_created(event, blocked_user)
        Block.objects.create(blocker=self.member, blocked=blocked_user)
        feed = get_feed_for_user(self.member)
        self.assertEqual(feed.count(), 0)

    def test_excludes_soft_deleted_actors(self):
        actor = _create_user('deletedactor')
        event = _create_event(actor, self.group)
        record_event_created(event, actor)
        actor.deleted_at = timezone.now()
        actor.save()
        feed = get_feed_for_user(self.member)
        self.assertEqual(feed.count(), 0)

    def test_excludes_disbanded_groups(self):
        self.group.disbanded_at = timezone.now()
        self.group.save()
        event = _create_event(self.admin, self.group)
        record_event_created(event, self.admin)
        feed = get_feed_for_user(self.member)
        self.assertEqual(feed.count(), 0)

    def test_days_filter_limits_results(self):
        event = _create_event(self.admin, self.group)
        record_event_created(event, self.admin)
        feed = get_feed_for_user(self.member, days=7)
        self.assertEqual(feed.count(), 1)
        old_item = ActivityFeedItem.objects.first()
        old_item.timestamp = timezone.now() - timedelta(days=10)
        old_item.save()
        feed = get_feed_for_user(self.member, days=7)
        self.assertEqual(feed.count(), 0)

    def test_limit_parameter(self):
        for i in range(5):
            event = _create_event(self.admin, self.group, title=f'Event {i}')
            record_event_created(event, self.admin)
        feed = get_feed_for_user(self.member, limit=3)
        self.assertEqual(len(feed), 3)

    def test_feed_ordered_by_timestamp_desc(self):
        event1 = _create_event(self.admin, self.group, title='First')
        record_event_created(event1, self.admin)
        event2 = _create_event(self.admin, self.group, title='Second')
        record_event_updated(event2, self.admin)
        feed = list(get_feed_for_user(self.member))
        self.assertEqual(feed[0].activity_type, 'event_updated')
        self.assertEqual(feed[1].activity_type, 'event_created')

    def test_multiple_groups_combined(self):
        group2 = _create_group(self.admin, name='Second Group')
        GroupMembership.objects.create(user=self.member, group=group2, role='member')
        event1 = _create_event(self.admin, self.group, title='Event 1')
        event2 = _create_event(self.admin, group2, title='Event 2')
        record_event_created(event1, self.admin)
        record_event_created(event2, self.admin)
        feed = get_feed_for_user(self.member)
        self.assertEqual(feed.count(), 2)
