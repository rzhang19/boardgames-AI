from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, tag
from django.utils import timezone

from club.models import Block, Friendship, Notification

User = get_user_model()


def _create_users(*usernames, password='testpass123'):
    return [User.objects.create_user(username=u, password=password) for u in usernames]


@tag("unit")
class FriendshipModelTest(TestCase):

    def test_create_pending_friendship(self):
        a, b = _create_users('alice', 'bob')
        f = Friendship.objects.create(requester=a, receiver=b)
        self.assertEqual(f.status, 'pending')
        self.assertEqual(str(f), 'alice -> bob (pending)')

    def test_unique_constraint_prevents_duplicate(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b)
        with self.assertRaises(IntegrityError):
            Friendship.objects.create(requester=a, receiver=b)

    def test_reverse_pair_is_allowed(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b)
        f2 = Friendship.objects.create(requester=b, receiver=a)
        self.assertEqual(f2.status, 'pending')

    def test_accept_sets_status(self):
        a, b = _create_users('alice', 'bob')
        f = Friendship.objects.create(requester=a, receiver=b)
        f.status = 'accepted'
        f.save()
        f.refresh_from_db()
        self.assertEqual(f.status, 'accepted')

    def test_decline_increments_counter(self):
        a, b = _create_users('alice', 'bob')
        f = Friendship.objects.create(requester=a, receiver=b)
        f.status = 'declined'
        f.decline_count = 1
        f.last_declined_at = timezone.now()
        f.save()
        f.refresh_from_db()
        self.assertEqual(f.status, 'declined')
        self.assertEqual(f.decline_count, 1)
        self.assertIsNotNone(f.last_declined_at)

    def test_cascade_on_user_delete(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b)
        a.delete()
        self.assertEqual(Friendship.objects.count(), 0)

    def test_are_friends_utility(self):
        a, b = _create_users('alice', 'bob')
        self.assertFalse(Friendship.are_friends(a, b))
        Friendship.objects.create(requester=a, receiver=b, status='accepted')
        self.assertTrue(Friendship.are_friends(a, b))
        self.assertTrue(Friendship.are_friends(b, a))

    def test_are_friends_returns_false_for_pending(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b, status='pending')
        self.assertFalse(Friendship.are_friends(a, b))

    def test_get_friendship_returns_correct_record(self):
        a, b = _create_users('alice', 'bob')
        f = Friendship.objects.create(requester=a, receiver=b)
        result = Friendship.get_friendship(a, b)
        self.assertEqual(result, f)
        result2 = Friendship.get_friendship(b, a)
        self.assertEqual(result2, f)

    def test_get_friendship_returns_none_when_none_exists(self):
        a, b = _create_users('alice', 'bob')
        self.assertIsNone(Friendship.get_friendship(a, b))

    def test_can_send_request_no_previous(self):
        a, b = _create_users('alice', 'bob')
        self.assertTrue(Friendship.can_send_request(a, b))

    def test_can_send_request_under_limit(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(
            requester=a, receiver=b, status='declined',
            decline_count=1, last_declined_at=timezone.now(),
        )
        self.assertTrue(Friendship.can_send_request(a, b))

    def test_can_send_request_at_limit(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(
            requester=a, receiver=b, status='declined',
            decline_count=2, last_declined_at=timezone.now(),
        )
        self.assertFalse(Friendship.can_send_request(a, b))

    def test_can_send_request_old_declines_expire(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(
            requester=a, receiver=b, status='declined',
            decline_count=2, last_declined_at=timezone.now() - timedelta(hours=169),
        )
        self.assertTrue(Friendship.can_send_request(a, b))

    def test_can_send_request_directional(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(
            requester=a, receiver=b, status='declined',
            decline_count=2, last_declined_at=timezone.now(),
        )
        self.assertTrue(Friendship.can_send_request(b, a))

    def test_can_send_request_accepted_blocks(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b, status='accepted')
        self.assertFalse(Friendship.can_send_request(a, b))

    def test_can_send_request_pending_blocks(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b, status='pending')
        self.assertFalse(Friendship.can_send_request(a, b))

    def test_can_send_request_self_blocked(self):
        a = _create_users('alice')[0]
        self.assertFalse(Friendship.can_send_request(a, a))

    def test_get_friends_of_user(self):
        a, b, c, d = _create_users('alice', 'bob', 'carol', 'dave')
        Friendship.objects.create(requester=a, receiver=b, status='accepted')
        Friendship.objects.create(requester=c, receiver=a, status='accepted')
        Friendship.objects.create(requester=c, receiver=d, status='accepted')
        friends = Friendship.get_friends_of(a)
        self.assertEqual(set(friends), {b, c})

    def test_get_friends_of_user_no_friends(self):
        a = _create_users('alice')[0]
        friends = Friendship.get_friends_of(a)
        self.assertEqual(list(friends), [])


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


@tag("unit")
class NotificationModelTest(TestCase):

    def test_create_notification(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(
            user=user,
            message='Test notification',
        )
        self.assertEqual(notif.user, user)
        self.assertEqual(notif.message, 'Test notification')
        self.assertFalse(notif.is_read)
        self.assertEqual(notif.notification_type, 'general')
        self.assertEqual(notif.url, '')
        self.assertEqual(notif.url_label, '')

    def test_notification_string_representation(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(
            user=user,
            message='A' * 100,
        )
        self.assertIn('testuser', str(notif))
        self.assertIn('A' * 50, str(notif))

    def test_notification_with_url_and_label(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(
            user=user,
            message='Edit your game',
            url='http://example.com/games/1/edit/',
            url_label='Edit Game',
            notification_type='missing_complexity',
        )
        self.assertEqual(notif.url, 'http://example.com/games/1/edit/')
        self.assertEqual(notif.url_label, 'Edit Game')
        self.assertEqual(notif.notification_type, 'missing_complexity')

    def test_notification_ordering_newest_first(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif1 = Notification.objects.create(user=user, message='First')
        notif2 = Notification.objects.create(user=user, message='Second')
        notifs = list(Notification.objects.all())
        self.assertEqual(notifs[0], notif2)
        self.assertEqual(notifs[1], notif1)

    def test_notification_defaults(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Test')
        self.assertFalse(notif.is_read)
        self.assertEqual(notif.notification_type, 'general')

    def test_notification_cascade_on_user_delete(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        Notification.objects.create(user=user, message='Test')
        self.assertEqual(Notification.objects.count(), 1)
        user.delete()
        self.assertEqual(Notification.objects.count(), 0)
