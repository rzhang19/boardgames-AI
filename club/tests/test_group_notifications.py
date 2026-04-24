from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.utils import timezone

from club.models import (
    Event, Group, GroupMembership, Notification,
)
from club.notifications import (
    notify_group_demoted_member,
    notify_group_demoted_organizer,
    notify_group_event_created,
    notify_group_event_updated,
    notify_group_grace_period,
    notify_group_invite_created,
    notify_group_join_approved,
    notify_group_join_rejected,
    notify_group_member_joined,
    notify_group_member_left,
    notify_group_join_request,
    notify_group_promoted_admin,
    notify_group_promoted_organizer,
    notify_group_removed,
    notify_group_restored,
    notify_group_settings_changed,
    notify_group_voting_ended,
    notify_group_voting_resumed,
)

User = get_user_model()


def _make_admin(user, group):
    return GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_organizer(user, group):
    return GroupMembership.objects.create(user=user, group=group, role='organizer')


def _make_member(user, group):
    return GroupMembership.objects.create(user=user, group=group, role='member')


# ---------------------------------------------------------------------------
# Personal notifications
# ---------------------------------------------------------------------------

@tag("unit")
class NotifyGroupJoinApprovedTest(TestCase):

    def test_creates_notification_for_user(self):
        user = User.objects.create_user(username='u', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='Test Group')
        notify_group_join_approved(user, group, actor)
        notif = Notification.objects.get(user=user)
        self.assertEqual(notif.notification_type, 'group_join_approved')
        self.assertIn('Test Group', notif.message)
        self.assertIn('actor', notif.message)
        self.assertEqual(notif.url, f'/groups/{group.slug}/')
        self.assertEqual(notif.url_label, 'View Group')

    def test_does_not_notify_other_users(self):
        user = User.objects.create_user(username='u', password='p')
        other = User.objects.create_user(username='other', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        notify_group_join_approved(user, group, actor)
        self.assertFalse(Notification.objects.filter(user=other).exists())


@tag("unit")
class NotifyGroupJoinRejectedTest(TestCase):

    def test_creates_notification_for_user(self):
        user = User.objects.create_user(username='u', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        notify_group_join_rejected(user, group, actor)
        notif = Notification.objects.get(user=user)
        self.assertEqual(notif.notification_type, 'group_join_rejected')
        self.assertIn('rejected', notif.message)
        self.assertIn('actor', notif.message)


@tag("unit")
class NotifyGroupPromotedOrganizerTest(TestCase):

    def test_creates_notification(self):
        user = User.objects.create_user(username='u', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        notify_group_promoted_organizer(user, group, actor)
        notif = Notification.objects.get(user=user)
        self.assertEqual(notif.notification_type, 'group_promoted_organizer')
        self.assertIn('organizer', notif.message)
        self.assertIn('actor', notif.message)


@tag("unit")
class NotifyGroupPromotedAdminTest(TestCase):

    def test_creates_notification(self):
        user = User.objects.create_user(username='u', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        notify_group_promoted_admin(user, group, actor)
        notif = Notification.objects.get(user=user)
        self.assertEqual(notif.notification_type, 'group_promoted_admin')
        self.assertIn('admin', notif.message)
        self.assertIn('actor', notif.message)


@tag("unit")
class NotifyGroupDemotedOrganizerTest(TestCase):

    def test_creates_notification(self):
        user = User.objects.create_user(username='u', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        notify_group_demoted_organizer(user, group, actor)
        notif = Notification.objects.get(user=user)
        self.assertEqual(notif.notification_type, 'group_demoted_organizer')
        self.assertIn('demoted to organizer', notif.message)
        self.assertIn('actor', notif.message)


@tag("unit")
class NotifyGroupDemotedMemberTest(TestCase):

    def test_creates_notification(self):
        user = User.objects.create_user(username='u', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        notify_group_demoted_member(user, group, actor)
        notif = Notification.objects.get(user=user)
        self.assertEqual(notif.notification_type, 'group_demoted_member')
        self.assertIn('demoted to member', notif.message)
        self.assertIn('actor', notif.message)


@tag("unit")
class NotifyGroupRemovedTest(TestCase):

    def test_creates_notification(self):
        user = User.objects.create_user(username='u', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        notify_group_removed(user, group, actor)
        notif = Notification.objects.get(user=user)
        self.assertEqual(notif.notification_type, 'group_removed')
        self.assertIn('removed', notif.message)
        self.assertIn('actor', notif.message)
        self.assertEqual(notif.url_label, 'Browse Groups')


# ---------------------------------------------------------------------------
# All-member notifications
# ---------------------------------------------------------------------------

@tag("unit")
class NotifyGroupEventCreatedTest(TestCase):

    def setUp(self):
        self.creator = User.objects.create_user(username='creator', password='p')
        self.member = User.objects.create_user(username='member', password='p')
        self.outsider = User.objects.create_user(username='outsider', password='p')
        self.group = Group.objects.create(name='Event Group')
        _make_admin(self.creator, self.group)
        _make_member(self.member, self.group)
        self.event = Event.objects.create(
            title='Game Night',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.creator,
            group=self.group,
        )

    def test_notifies_all_members_except_creator(self):
        notify_group_event_created(self.group, self.event, self.creator)
        self.assertTrue(Notification.objects.filter(user=self.member).exists())
        self.assertFalse(Notification.objects.filter(user=self.creator).exists())
        self.assertFalse(Notification.objects.filter(user=self.outsider).exists())

    def test_notification_content(self):
        notify_group_event_created(self.group, self.event, self.creator)
        notif = Notification.objects.get(user=self.member)
        self.assertEqual(notif.notification_type, 'group_event_created')
        self.assertIn('Game Night', notif.message)
        self.assertIn('Event Group', notif.message)
        self.assertEqual(notif.url, f'/groups/{self.group.slug}/events/{self.event.pk}/')
        self.assertEqual(notif.url_label, 'View Event')

    def test_recurring_event_count(self):
        notify_group_event_created(self.group, self.event, self.creator, count=3)
        notif = Notification.objects.get(user=self.member)
        self.assertIn('3', notif.message)
        self.assertIn('recurring', notif.message)


@tag("unit")
class NotifyGroupEventUpdatedTest(TestCase):

    def test_notifies_all_members_except_actor(self):
        actor = User.objects.create_user(username='actor', password='p')
        member = User.objects.create_user(username='member', password='p')
        group = Group.objects.create(name='G')
        _make_admin(actor, group)
        _make_member(member, group)
        event = Event.objects.create(
            title='Ev', date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=actor, group=group,
        )
        notify_group_event_updated(group, event, actor)
        self.assertTrue(Notification.objects.filter(user=member).exists())
        self.assertFalse(Notification.objects.filter(user=actor).exists())
        notif = Notification.objects.get(user=member)
        self.assertEqual(notif.notification_type, 'group_event_updated')


@tag("unit")
class NotifyGroupVotingEndedTest(TestCase):

    def test_notifies_all_members_including_actor(self):
        actor = User.objects.create_user(username='actor', password='p')
        member = User.objects.create_user(username='member', password='p')
        group = Group.objects.create(name='G')
        _make_admin(actor, group)
        _make_member(member, group)
        event = Event.objects.create(
            title='Ev', date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=actor, group=group,
        )
        notify_group_voting_ended(group, event, actor)
        self.assertTrue(Notification.objects.filter(user=member).exists())
        notif = Notification.objects.get(user=member)
        self.assertEqual(notif.notification_type, 'group_voting_ended')
        self.assertIn('ended', notif.message)


@tag("unit")
class NotifyGroupVotingResumedTest(TestCase):

    def test_notifies_all_members(self):
        member = User.objects.create_user(username='member', password='p')
        group = Group.objects.create(name='G')
        _make_member(member, group)
        event = Event.objects.create(
            title='Ev', date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=member, group=group,
        )
        notify_group_voting_resumed(group, event, member)
        notif = Notification.objects.get(user=member)
        self.assertEqual(notif.notification_type, 'group_voting_resumed')
        self.assertIn('resumed', notif.message)


# ---------------------------------------------------------------------------
# Admin-only notifications
# ---------------------------------------------------------------------------

@tag("unit")
class NotifyGroupMemberJoinedTest(TestCase):

    def test_notifies_admins_only(self):
        admin = User.objects.create_user(username='admin', password='p')
        organizer = User.objects.create_user(username='organizer', password='p')
        member = User.objects.create_user(username='member', password='p')
        joined = User.objects.create_user(username='joined', password='p')
        group = Group.objects.create(name='G')
        _make_admin(admin, group)
        _make_organizer(organizer, group)
        _make_member(member, group)
        notify_group_member_joined(group, joined, method='open join')
        self.assertTrue(Notification.objects.filter(user=admin).exists())
        self.assertFalse(Notification.objects.filter(user=organizer).exists())
        self.assertFalse(Notification.objects.filter(user=member).exists())
        self.assertFalse(Notification.objects.filter(user=joined).exists())

    def test_notification_content(self):
        admin = User.objects.create_user(username='admin', password='p')
        joined = User.objects.create_user(username='joined', password='p')
        group = Group.objects.create(name='G')
        _make_admin(admin, group)
        notify_group_member_joined(group, joined, method='invite')
        notif = Notification.objects.get(user=admin)
        self.assertEqual(notif.notification_type, 'group_member_joined')
        self.assertIn('joined', notif.message)
        self.assertIn('invite', notif.message)


@tag("unit")
class NotifyGroupJoinRequestTest(TestCase):

    def test_notifies_admins(self):
        admin = User.objects.create_user(username='admin', password='p')
        requester = User.objects.create_user(username='req', password='p')
        group = Group.objects.create(name='G')
        _make_admin(admin, group)
        notify_group_join_request(group, requester)
        notif = Notification.objects.get(user=admin)
        self.assertEqual(notif.notification_type, 'group_join_request')
        self.assertIn('req', notif.message)
        self.assertIn('join-requests', notif.url)


@tag("unit")
class NotifyGroupMemberLeftTest(TestCase):

    def test_notifies_admins(self):
        admin = User.objects.create_user(username='admin', password='p')
        leaver = User.objects.create_user(username='leaver', password='p')
        group = Group.objects.create(name='G')
        _make_admin(admin, group)
        _make_member(leaver, group)
        notify_group_member_left(group, leaver)
        notif = Notification.objects.get(user=admin)
        self.assertEqual(notif.notification_type, 'group_member_left')
        self.assertIn('leaver', notif.message)
        self.assertIn('left', notif.message)


@tag("unit")
class NotifyGroupInviteCreatedTest(TestCase):

    def test_notifies_admins(self):
        admin = User.objects.create_user(username='admin', password='p')
        other_admin = User.objects.create_user(username='admin2', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        _make_admin(admin, group)
        _make_admin(other_admin, group)
        _make_admin(actor, group)
        notify_group_invite_created(group, actor)
        notifs = Notification.objects.filter(notification_type='group_invite_created')
        self.assertEqual(notifs.count(), 2)
        self.assertFalse(notifs.filter(user=actor).exists())
        self.assertTrue(notifs.filter(user=admin).exists())
        self.assertTrue(notifs.filter(user=other_admin).exists())


@tag("unit")
class NotifyGroupSettingsChangedTest(TestCase):

    def test_notifies_admins_except_actor(self):
        admin = User.objects.create_user(username='admin', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        _make_admin(admin, group)
        _make_admin(actor, group)
        notify_group_settings_changed(group, actor)
        self.assertTrue(Notification.objects.filter(user=admin).exists())
        self.assertFalse(Notification.objects.filter(user=actor).exists())


@tag("unit")
class NotifyGroupGracePeriodTest(TestCase):

    def test_notifies_site_admins_and_superusers(self):
        site_admin = User.objects.create_user(
            username='siteadmin', password='p', is_site_admin=True,
        )
        superuser = User.objects.create_superuser(
            username='super', password='p', email='s@example.com',
        )
        regular = User.objects.create_user(username='regular', password='p')
        group = Group.objects.create(name='G')
        notify_group_grace_period(group)
        self.assertTrue(Notification.objects.filter(user=site_admin).exists())
        self.assertTrue(Notification.objects.filter(user=superuser).exists())
        self.assertFalse(Notification.objects.filter(user=regular).exists())

    def test_notification_content(self):
        site_admin = User.objects.create_user(
            username='siteadmin', password='p', is_site_admin=True,
        )
        group = Group.objects.create(name='Disbanded Group')
        notify_group_grace_period(group)
        notif = Notification.objects.get(user=site_admin)
        self.assertEqual(notif.notification_type, 'group_grace_period')
        self.assertIn('Disbanded Group', notif.message)
        self.assertIn('grace period', notif.message)


@tag("unit")
class NotifyGroupRestoredTest(TestCase):

    def test_notifies_site_admins_and_superusers_except_actor(self):
        site_admin = User.objects.create_user(
            username='siteadmin', password='p', is_site_admin=True,
        )
        superuser = User.objects.create_superuser(
            username='super', password='p', email='s@example.com',
        )
        group = Group.objects.create(name='G')
        notify_group_restored(group, site_admin)
        self.assertFalse(Notification.objects.filter(user=site_admin).exists())
        self.assertTrue(Notification.objects.filter(user=superuser).exists())

    def test_notification_content(self):
        site_admin = User.objects.create_user(
            username='siteadmin', password='p', is_site_admin=True,
        )
        actor = User.objects.create_user(
            username='actor', password='p', is_site_admin=True,
        )
        group = Group.objects.create(name='Restored Group')
        notify_group_restored(group, actor)
        notif = Notification.objects.get(user=site_admin)
        self.assertEqual(notif.notification_type, 'group_restored')
        self.assertIn('Restored Group', notif.message)
        self.assertIn('restored', notif.message)
        self.assertIn('actor', notif.message)


# ---------------------------------------------------------------------------
# Disbanded group guard
# ---------------------------------------------------------------------------

@tag("unit")
class DisbandedGroupNotificationGuardTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='p')
        self.member = User.objects.create_user(username='member', password='p')
        self.group = Group.objects.create(name='G')
        self.group.disbanded_at = timezone.now()
        self.group.save()
        _make_admin(self.admin, self.group)
        _make_member(self.member, self.group)

    def test_event_created_does_not_notify_disbanded_group(self):
        actor = User.objects.create_user(username='actor', password='p')
        event = Event.objects.create(
            title='Ev', date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=actor, group=self.group,
        )
        notify_group_event_created(self.group, event, actor)
        self.assertEqual(Notification.objects.count(), 0)

    def test_member_joined_does_not_notify_disbanded_group(self):
        joined = User.objects.create_user(username='joined', password='p')
        notify_group_member_joined(self.group, joined)
        self.assertEqual(Notification.objects.count(), 0)

    def test_member_left_does_not_notify_disbanded_group(self):
        notify_group_member_left(self.group, self.member)
        self.assertEqual(Notification.objects.count(), 0)

    def test_settings_changed_does_not_notify_disbanded_group(self):
        notify_group_settings_changed(self.group, self.admin)
        self.assertEqual(Notification.objects.count(), 0)

    def test_join_request_does_not_notify_disbanded_group(self):
        requester = User.objects.create_user(username='req', password='p')
        notify_group_join_request(self.group, requester)
        self.assertEqual(Notification.objects.count(), 0)

    def test_invite_created_does_not_notify_disbanded_group(self):
        notify_group_invite_created(self.group, self.admin)
        self.assertEqual(Notification.objects.count(), 0)

    def test_voting_ended_does_not_notify_disbanded_group(self):
        event = Event.objects.create(
            title='Ev', date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.admin, group=self.group,
        )
        notify_group_voting_ended(self.group, event, self.admin)
        self.assertEqual(Notification.objects.count(), 0)

    def test_voting_resumed_does_not_notify_disbanded_group(self):
        event = Event.objects.create(
            title='Ev', date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.admin, group=self.group,
        )
        notify_group_voting_resumed(self.group, event, self.admin)
        self.assertEqual(Notification.objects.count(), 0)

    def test_personal_notifications_still_fire_for_disbanded_group(self):
        actor = User.objects.create_user(username='actor', password='p')
        notify_group_removed(self.member, self.group, actor)
        self.assertEqual(Notification.objects.count(), 1)
