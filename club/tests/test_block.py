from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from club.models import Block, Event, EventAttendance, EventInvite, Friendship, Group, GroupMembership, Notification

User = get_user_model()


def _create_users(*usernames, password='testpass123'):
    return [User.objects.create_user(username=u, password=password) for u in usernames]


def _create_group(name, created_by, members=None):
    group = Group.objects.create(name=name, created_by=created_by)
    GroupMembership.objects.create(user=created_by, group=group, role='admin')
    for m in (members or []):
        if m != created_by:
            GroupMembership.objects.create(user=m, group=group, role='member')
    return group


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

@tag("unit")
class BlockModelTest(TestCase):

    def test_create_block(self):
        a, b = _create_users('alice', 'bob')
        block = Block.objects.create(blocker=a, blocked=b)
        self.assertEqual(block.blocker, a)
        self.assertEqual(block.blocked, b)
        self.assertEqual(str(block), 'alice blocked bob')

    def test_unique_constraint_prevents_duplicate(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        with self.assertRaises(IntegrityError):
            Block.objects.create(blocker=a, blocked=b)

    def test_reverse_block_is_allowed(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        block2 = Block.objects.create(blocker=b, blocked=a)
        self.assertIsNotNone(block2)

    def test_is_blocked_returns_true_when_block_exists(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        self.assertTrue(Block.is_blocked(a, b))

    def test_is_blocked_returns_true_in_reverse_direction(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        self.assertTrue(Block.is_blocked(b, a))

    def test_is_blocked_returns_false_when_no_block(self):
        a, b = _create_users('alice', 'bob')
        self.assertFalse(Block.is_blocked(a, b))

    def test_is_blocked_returns_false_for_same_user(self):
        a = _create_users('alice')[0]
        self.assertFalse(Block.is_blocked(a, a))

    def test_get_blocked_user_ids_includes_blocked(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        self.assertIn(b.pk, Block.get_blocked_user_ids(a))

    def test_get_blocked_user_ids_includes_blocker(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        self.assertIn(a.pk, Block.get_blocked_user_ids(b))

    def test_get_blocked_user_ids_returns_empty_for_no_blocks(self):
        a = _create_users('alice')[0]
        self.assertEqual(Block.get_blocked_user_ids(a), set())

    def test_get_blocked_user_ids_returns_multiple(self):
        a, b, c = _create_users('alice', 'bob', 'carol')
        Block.objects.create(blocker=a, blocked=b)
        Block.objects.create(blocker=c, blocked=a)
        ids = Block.get_blocked_user_ids(a)
        self.assertEqual(ids, {b.pk, c.pk})


# ---------------------------------------------------------------------------
# Block view tests
# ---------------------------------------------------------------------------

@tag("system")
class BlockUserViewTest(TestCase):

    def test_block_user_success(self):
        a, b = _create_users('alice', 'bob')
        self.client.force_login(a)
        resp = self.client.post(reverse('block_user', args=['bob']))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Block.objects.filter(blocker=a, blocked=b).exists())

    def test_block_user_requires_login(self):
        _create_users('alice', 'bob')
        resp = self.client.post(reverse('block_user', args=['bob']))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_block_user_nonexistent_returns_404(self):
        a = _create_users('alice')[0]
        self.client.force_login(a)
        resp = self.client.post(reverse('block_user', args=['nobody']))
        self.assertEqual(resp.status_code, 404)

    def test_block_self_fails(self):
        a = _create_users('alice')[0]
        self.client.force_login(a)
        resp = self.client.post(reverse('block_user', args=['alice']))
        self.assertEqual(resp.status_code, 403)

    def test_block_duplicate_is_idempotent(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(a)
        resp = self.client.post(reverse('block_user', args=['bob']))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Block.objects.filter(blocker=a, blocked=b).count(), 1)

    def test_block_requires_post(self):
        a, b = _create_users('alice', 'bob')
        self.client.force_login(a)
        resp = self.client.get(reverse('block_user', args=['bob']))
        self.assertEqual(resp.status_code, 405)

    def test_block_auto_removes_friendship(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b, status='accepted')
        self.client.force_login(a)
        self.client.post(reverse('block_user', args=['bob']))
        self.assertFalse(Friendship.objects.filter(
            requester=a, receiver=b,
        ).exists())

    def test_block_auto_removes_pending_request_sent(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b, status='pending')
        self.client.force_login(a)
        self.client.post(reverse('block_user', args=['bob']))
        self.assertFalse(Friendship.objects.filter(
            requester=a, receiver=b,
        ).exists())

    def test_block_auto_removes_pending_request_received(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=b, receiver=a, status='pending')
        self.client.force_login(a)
        self.client.post(reverse('block_user', args=['bob']))
        self.assertFalse(Friendship.objects.filter(
            requester=b, receiver=a,
        ).exists())

    def test_block_auto_removes_friend_request_notifications(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=b, receiver=a, status='pending')
        Notification.objects.create(
            user=a, message='bob sent you a friend request',
            url=f'/profile/bob/', notification_type='friend_request',
        )
        self.client.force_login(a)
        self.client.post(reverse('block_user', args=['bob']))
        self.assertFalse(Notification.objects.filter(
            user=a, notification_type='friend_request',
        ).exists())

    def test_block_auto_removes_declined_friendship(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b, status='declined')
        self.client.force_login(a)
        self.client.post(reverse('block_user', args=['bob']))
        self.assertFalse(Friendship.objects.filter(
            requester=a, receiver=b,
        ).exists())


# ---------------------------------------------------------------------------
# Unblock view tests
# ---------------------------------------------------------------------------

@tag("system")
class UnblockUserViewTest(TestCase):

    def test_unblock_user_success(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(a)
        resp = self.client.post(reverse('unblock_user', args=['bob']))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Block.objects.filter(blocker=a, blocked=b).exists())

    def test_unblock_user_requires_login(self):
        _create_users('alice', 'bob')
        resp = self.client.post(reverse('unblock_user', args=['bob']))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_unblock_nonexistent_user_returns_404(self):
        a = _create_users('alice')[0]
        self.client.force_login(a)
        resp = self.client.post(reverse('unblock_user', args=['nobody']))
        self.assertEqual(resp.status_code, 404)

    def test_unblock_when_no_block_exists(self):
        a, b = _create_users('alice', 'bob')
        self.client.force_login(a)
        resp = self.client.post(reverse('unblock_user', args=['bob']))
        self.assertEqual(resp.status_code, 302)

    def test_unblock_requires_post(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(a)
        resp = self.client.get(reverse('unblock_user', args=['bob']))
        self.assertEqual(resp.status_code, 405)

    def test_unblock_does_not_remove_reverse_block(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        Block.objects.create(blocker=b, blocked=a)
        self.client.force_login(a)
        self.client.post(reverse('unblock_user', args=['bob']))
        self.assertFalse(Block.objects.filter(blocker=a, blocked=b).exists())
        self.assertTrue(Block.objects.filter(blocker=b, blocked=a).exists())


# ---------------------------------------------------------------------------
# Profile visibility tests
# ---------------------------------------------------------------------------

@tag("system")
class BlockProfileVisibilityTest(TestCase):

    def test_blocked_user_sees_minimal_profile(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(b)
        resp = self.client.get(reverse('public_profile', args=['alice']))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context.get('is_blocked', False))

    def test_blocker_sees_minimal_profile(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(a)
        resp = self.client.get(reverse('public_profile', args=['bob']))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context.get('is_blocked', False))

    def test_blocked_profile_does_not_show_games(self):
        a, b = _create_users('alice', 'bob')
        a.show_games = True
        a.save()
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(b)
        resp = self.client.get(reverse('public_profile', args=['alice']))
        self.assertNotIn('games', resp.context)

    def test_blocked_profile_does_not_show_events(self):
        a, b = _create_users('alice', 'bob')
        a.show_events = True
        a.save()
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(b)
        resp = self.client.get(reverse('public_profile', args=['alice']))
        self.assertNotIn('attendances', resp.context)

    def test_unblocked_profile_shows_normal_info(self):
        a, b = _create_users('alice', 'bob')
        a.show_games = True
        a.show_events = True
        a.save()
        self.client.force_login(b)
        resp = self.client.get(reverse('public_profile', args=['alice']))
        self.assertFalse(resp.context.get('is_blocked', False))
        self.assertIn('games', resp.context)
        self.assertIn('attendances', resp.context)


# ---------------------------------------------------------------------------
# Friend request blocking tests
# ---------------------------------------------------------------------------

@tag("system")
class BlockFriendRequestTest(TestCase):

    def test_blocked_user_cannot_send_friend_request(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(b)
        resp = self.client.post(reverse('send_friend_request', args=['alice']))
        self.assertEqual(resp.status_code, 403)

    def test_blocker_cannot_send_friend_request(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(a)
        resp = self.client.post(reverse('send_friend_request', args=['bob']))
        self.assertEqual(resp.status_code, 403)

    def test_blocked_user_cannot_accept_friend_request(self):
        a, b = _create_users('alice', 'bob')
        f = Friendship.objects.create(requester=a, receiver=b, status='pending')
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(b)
        resp = self.client.post(reverse('accept_friend_request', args=[f.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_blocked_user_cannot_decline_friend_request(self):
        a, b = _create_users('alice', 'bob')
        f = Friendship.objects.create(requester=a, receiver=b, status='pending')
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(b)
        resp = self.client.post(reverse('decline_friend_request', args=[f.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_blocked_user_cannot_cancel_friend_request(self):
        a, b = _create_users('alice', 'bob')
        f = Friendship.objects.create(requester=b, receiver=a, status='pending')
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(b)
        resp = self.client.post(reverse('cancel_friend_request', args=[f.pk]))
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# User search filtering tests
# ---------------------------------------------------------------------------

@tag("system")
class BlockUserSearchTest(TestCase):

    def test_blocked_users_excluded_from_search(self):
        a, b, c = _create_users('alice', 'bob', 'carol')
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(a)
        resp = self.client.get(reverse('user_search') + '?q=bo')
        usernames = [u.username for u in resp.context['results']]
        self.assertNotIn('bob', usernames)

    def test_blocking_users_excluded_from_search(self):
        a, b, c = _create_users('alice', 'bob', 'carol')
        Block.objects.create(blocker=b, blocked=a)
        self.client.force_login(a)
        resp = self.client.get(reverse('user_search') + '?q=bo')
        usernames = [u.username for u in resp.context['results']]
        self.assertNotIn('bob', usernames)

    def test_unblocked_users_appear_in_search(self):
        a, b = _create_users('alice', 'bob')
        self.client.force_login(a)
        resp = self.client.get(reverse('user_search') + '?q=bo')
        usernames = [u.username for u in resp.context['results']]
        self.assertIn('bob', usernames)


# ---------------------------------------------------------------------------
# Friends list filtering tests
# ---------------------------------------------------------------------------

@tag("system")
class BlockFriendsListTest(TestCase):

    def test_blocked_users_excluded_from_friends_list(self):
        a, b, c = _create_users('alice', 'bob', 'carol')
        Friendship.objects.create(requester=a, receiver=b, status='accepted')
        Friendship.objects.create(requester=a, receiver=c, status='accepted')
        Block.objects.create(blocker=a, blocked=c)
        self.client.force_login(a)
        resp = self.client.get(reverse('friends_list', args=['alice']))
        friends = resp.context['friends']
        usernames = [f.username for f in friends]
        self.assertIn('bob', usernames)
        self.assertNotIn('carol', usernames)


# ---------------------------------------------------------------------------
# Event invite filtering tests
# ---------------------------------------------------------------------------

@tag("system")
class BlockEventInviteTest(TestCase):

    def setUp(self):
        self.a, self.b, self.c = _create_users('alice', 'bob', 'carol')
        Friendship.objects.create(requester=self.a, receiver=self.b, status='accepted')
        Friendship.objects.create(requester=self.a, receiver=self.c, status='accepted')
        self.event = Event.objects.create(
            title='Test Event',
            date=timezone.now() + timedelta(days=30),
            voting_deadline=timezone.now() + timedelta(days=29),
            created_by=self.a,
            allow_invite_others='anyone',
        )
        EventAttendance.objects.create(user=self.a, event=self.event)

    def test_blocked_users_excluded_from_invite_friends_list(self):
        Block.objects.create(blocker=self.a, blocked=self.c)
        self.client.force_login(self.a)
        resp = self.client.get(reverse('event_invite', args=[self.event.pk]))
        friends = resp.context['friends']
        usernames = [f.username for f in friends]
        self.assertIn('bob', usernames)
        self.assertNotIn('carol', usernames)

    def test_cannot_invite_blocked_user(self):
        Block.objects.create(blocker=self.a, blocked=self.c)
        self.client.force_login(self.a)
        resp = self.client.post(
            reverse('event_invite', args=[self.event.pk]),
            {'user_ids': str(self.c.pk)},
        )
        self.assertFalse(EventInvite.objects.filter(
            event=self.event, user=self.c,
        ).exists())


# ---------------------------------------------------------------------------
# Notification filtering tests
# ---------------------------------------------------------------------------

@tag("system")
class BlockNotificationFilterTest(TestCase):

    def test_notifications_from_blocked_user_are_hidden(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        Notification.objects.create(
            user=a, message='bob sent you a friend request',
            url=f'/profile/bob/', notification_type='friend_request',
        )
        Notification.objects.create(
            user=a, message='some other notification',
            notification_type='general',
        )
        self.client.force_login(a)
        resp = self.client.get(reverse('notification_list'))
        notif_messages = [n.message for n in resp.context['notifications']]
        self.assertNotIn('bob sent you a friend request', notif_messages)
        self.assertIn('some other notification', notif_messages)

    def test_notifications_about_blocking_user_are_hidden(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=b, blocked=a)
        Notification.objects.create(
            user=a, message='bob sent you a friend request',
            url=f'/profile/bob/', notification_type='friend_request',
        )
        self.client.force_login(a)
        resp = self.client.get(reverse('notification_list'))
        notif_messages = [n.message for n in resp.context['notifications']]
        self.assertNotIn('bob sent you a friend request', notif_messages)

    def test_group_notifications_not_filtered(self):
        a, b = _create_users('alice', 'bob')
        group = _create_group('TestGroup', b, members=[a])
        Block.objects.create(blocker=a, blocked=b)
        Notification.objects.create(
            user=a, message='New event in "TestGroup": "Game Night"',
            url=f'/groups/{group.slug}/', notification_type='group_event_created',
        )
        self.client.force_login(a)
        resp = self.client.get(reverse('notification_list'))
        notif_messages = [n.message for n in resp.context['notifications']]
        self.assertIn('New event in "TestGroup": "Game Night"', notif_messages)


# ---------------------------------------------------------------------------
# Profile block/unblock button tests
# ---------------------------------------------------------------------------

@tag("system")
class ProfileBlockButtonTest(TestCase):

    def test_own_profile_shows_no_block_button(self):
        a = _create_users('alice')[0]
        self.client.force_login(a)
        resp = self.client.get(reverse('public_profile', args=['alice']))
        self.assertNotContains(resp, 'block_user')

    def test_other_profile_shows_block_button(self):
        a, b = _create_users('alice', 'bob')
        self.client.force_login(a)
        resp = self.client.get(reverse('public_profile', args=['bob']))
        self.assertContains(resp, '/block/bob/')

    def test_blocked_profile_shows_unblock_button(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(a)
        resp = self.client.get(reverse('public_profile', args=['bob']))
        self.assertContains(resp, '/unblock/bob/')

    def test_blocked_profile_does_not_show_friend_buttons(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b, status='accepted')
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(a)
        resp = self.client.get(reverse('public_profile', args=['bob']))
        self.assertNotContains(resp, 'remove_friend')
        self.assertNotContains(resp, 'send_friend_request')


# ---------------------------------------------------------------------------
# Settings blocked users list tests
# ---------------------------------------------------------------------------

@tag("system")
class SettingsBlockedUsersTest(TestCase):

    def test_settings_shows_blocked_users(self):
        a, b, c = _create_users('alice', 'bob', 'carol')
        Block.objects.create(blocker=a, blocked=b)
        Block.objects.create(blocker=a, blocked=c)
        self.client.force_login(a)
        resp = self.client.get(reverse('user_settings'))
        blocked_usernames = [u.username for u in resp.context.get('blocked_users', [])]
        self.assertIn('bob', blocked_usernames)
        self.assertIn('carol', blocked_usernames)

    def test_settings_does_not_show_received_blocks(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=b, blocked=a)
        self.client.force_login(a)
        resp = self.client.get(reverse('user_settings'))
        blocked_usernames = [u.username for u in resp.context.get('blocked_users', [])]
        self.assertNotIn('bob', blocked_usernames)

    def test_settings_unblock_from_list(self):
        a, b = _create_users('alice', 'bob')
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(a)
        self.client.post(reverse('unblock_user', args=['bob']))
        self.assertFalse(Block.objects.filter(blocker=a, blocked=b).exists())


# ---------------------------------------------------------------------------
# Soft block in groups tests
# ---------------------------------------------------------------------------

@tag("system")
class BlockGroupInteractionTest(TestCase):

    def test_blocked_user_still_visible_in_group_members(self):
        a, b = _create_users('alice', 'bob')
        group = _create_group('TestGroup', a, members=[b])
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(a)
        resp = self.client.get(reverse('group_members', args=[group.slug]))
        member_usernames = [m.user.username for m in resp.context['members']]
        self.assertIn('bob', member_usernames)

    def test_blocked_user_can_attend_same_event(self):
        a, b = _create_users('alice', 'bob')
        group = _create_group('TestGroup', a, members=[b])
        event = Event.objects.create(
            title='Test Event',
            date=timezone.now() + timedelta(days=30),
            voting_deadline=timezone.now() + timedelta(days=29),
            created_by=a,
            group=group,
        )
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(b)
        resp = self.client.post(reverse('event_rsvp', args=[group.slug, event.pk]))
        self.assertTrue(EventAttendance.objects.filter(user=b, event=event).exists())

    def test_blocked_user_can_vote_on_same_event(self):
        a, b = _create_users('alice', 'bob')
        group = _create_group('TestGroup', a, members=[b])
        event = Event.objects.create(
            title='Test Event',
            date='2099-01-01T00:00:00Z',
            voting_deadline='2099-01-01T00:00:00Z',
            created_by=a,
            group=group,
        )
        EventAttendance.objects.create(user=b, event=event)
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(b)
        resp = self.client.get(reverse('event_vote', args=[group.slug, event.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context.get('voting_closed', True))

    def test_blocked_user_appears_in_event_attendees(self):
        a, b = _create_users('alice', 'bob')
        group = _create_group('TestGroup', a, members=[b])
        event = Event.objects.create(
            title='Test Event',
            date=timezone.now() + timedelta(days=30),
            voting_deadline=timezone.now() + timedelta(days=29),
            created_by=a,
            group=group,
        )
        EventAttendance.objects.create(user=b, event=event)
        Block.objects.create(blocker=a, blocked=b)
        self.client.force_login(a)
        resp = self.client.get(reverse('event_detail', args=[group.slug, event.pk]))
        attendee_usernames = [att.user.username for att in resp.context['attendees']]
        self.assertIn('bob', attendee_usernames)
