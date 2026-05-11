from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, tag
from django.utils import timezone

from club.models import BoardGame, Block, Friendship, Notification

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


@tag("unit")
class CleanupNotificationsTest(TestCase):

    def test_deletes_read_notifications_older_than_30_days(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        old = Notification.objects.create(user=user, message='Old', is_read=True)
        Notification.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=31)
        )
        from club.management.commands.cleanup_notifications import Command
        Command().handle()
        self.assertFalse(Notification.objects.filter(pk=old.pk).exists())

    def test_keeps_read_notifications_within_30_days(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        recent = Notification.objects.create(user=user, message='Recent', is_read=True)
        Notification.objects.filter(pk=recent.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=15)
        )
        from club.management.commands.cleanup_notifications import Command
        Command().handle()
        self.assertTrue(Notification.objects.filter(pk=recent.pk).exists())

    def test_keeps_unread_notifications_regardless_of_age(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        old_unread = Notification.objects.create(user=user, message='Old unread', is_read=False)
        Notification.objects.filter(pk=old_unread.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=60)
        )
        from club.management.commands.cleanup_notifications import Command
        Command().handle()
        self.assertTrue(Notification.objects.filter(pk=old_unread.pk).exists())


@tag("unit")
class MissingComplexityNotificationTest(TestCase):

    def test_generates_notification_for_game_without_complexity(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        game = BoardGame.objects.create(name='Catan', owner=user)
        from club.notifications import generate_missing_complexity_notifications
        generate_missing_complexity_notifications(user)
        notifs = Notification.objects.filter(user=user, notification_type='missing_complexity')
        self.assertEqual(notifs.count(), 1)
        self.assertIn('Catan', notifs.first().message)

    def test_does_not_generate_for_game_with_unknown_complexity(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        BoardGame.objects.create(name='Catan', owner=user, complexity='unknown')
        from club.notifications import generate_missing_complexity_notifications
        generate_missing_complexity_notifications(user)
        notifs = Notification.objects.filter(user=user, notification_type='missing_complexity')
        self.assertEqual(notifs.count(), 0)

    def test_does_not_generate_for_game_with_complexity(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        BoardGame.objects.create(name='Catan', owner=user, complexity='medium')
        from club.notifications import generate_missing_complexity_notifications
        generate_missing_complexity_notifications(user)
        notifs = Notification.objects.filter(user=user, notification_type='missing_complexity')
        self.assertEqual(notifs.count(), 0)

    def test_skips_if_notification_already_exists(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        game = BoardGame.objects.create(name='Catan', owner=user)
        from club.notifications import generate_missing_complexity_notifications
        generate_missing_complexity_notifications(user)
        generate_missing_complexity_notifications(user)
        notifs = Notification.objects.filter(user=user, notification_type='missing_complexity')
        self.assertEqual(notifs.count(), 1)

    def test_generates_one_notification_per_game(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        BoardGame.objects.create(name='Catan', owner=user)
        BoardGame.objects.create(name='Ticket to Ride', owner=user)
        from club.notifications import generate_missing_complexity_notifications
        generate_missing_complexity_notifications(user)
        notifs = Notification.objects.filter(user=user, notification_type='missing_complexity')
        self.assertEqual(notifs.count(), 2)

    def test_does_not_generate_for_other_users_games(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        other = User.objects.create_user(username='otheruser', password='testpass123')
        BoardGame.objects.create(name='Catan', owner=other)
        from club.notifications import generate_missing_complexity_notifications
        generate_missing_complexity_notifications(user)
        notifs = Notification.objects.filter(user=user, notification_type='missing_complexity')
        self.assertEqual(notifs.count(), 0)

    def test_notification_url_points_to_game_edit(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        game = BoardGame.objects.create(name='Catan', owner=user)
        from club.notifications import generate_missing_complexity_notifications
        generate_missing_complexity_notifications(user)
        notif = Notification.objects.filter(user=user, notification_type='missing_complexity').first()
        self.assertIn(f'/games/{game.pk}/edit/', notif.url)
        self.assertEqual(notif.url_label, 'Edit Game')

    def test_no_notifications_for_user_with_no_games(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        from club.notifications import generate_missing_complexity_notifications
        generate_missing_complexity_notifications(user)
        notifs = Notification.objects.filter(user=user, notification_type='missing_complexity')
        self.assertEqual(notifs.count(), 0)

    def test_complexity_added_auto_dismisses_notification(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        game = BoardGame.objects.create(name='Catan', owner=user)
        from club.notifications import generate_missing_complexity_notifications
        generate_missing_complexity_notifications(user)
        notif = Notification.objects.filter(user=user, notification_type='missing_complexity', is_read=False).first()
        self.assertIsNotNone(notif)
        self.client.login(username='testuser', password='testpass123')
        from django.urls import reverse
        self.client.post(reverse('game_edit', kwargs={'pk': game.pk}), {
            'name': 'Catan', 'description': '', 'min_players': 3,
            'max_players': 4, 'complexity': 'medium', 'bgg_id': '',
        })
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)


@tag("unit")
class MissingMaxPlayersNotificationTest(TestCase):

    def test_generates_notification_for_game_without_max_players(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        game = BoardGame.objects.create(name='Catan', owner=user)
        from club.notifications import generate_missing_max_players_notifications
        generate_missing_max_players_notifications(user)
        notifs = Notification.objects.filter(user=user, notification_type='missing_max_players')
        self.assertEqual(notifs.count(), 1)
        self.assertIn('Catan', notifs.first().message)

    def test_does_not_generate_for_game_with_max_players(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        BoardGame.objects.create(name='Catan', owner=user, max_players=4)
        from club.notifications import generate_missing_max_players_notifications
        generate_missing_max_players_notifications(user)
        notifs = Notification.objects.filter(user=user, notification_type='missing_max_players')
        self.assertEqual(notifs.count(), 0)

    def test_does_not_generate_for_game_with_unlimited(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        BoardGame.objects.create(name='Catan', owner=user, max_players=0)
        from club.notifications import generate_missing_max_players_notifications
        generate_missing_max_players_notifications(user)
        notifs = Notification.objects.filter(user=user, notification_type='missing_max_players')
        self.assertEqual(notifs.count(), 0)

    def test_skips_if_notification_already_exists(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        BoardGame.objects.create(name='Catan', owner=user)
        from club.notifications import generate_missing_max_players_notifications
        generate_missing_max_players_notifications(user)
        generate_missing_max_players_notifications(user)
        notifs = Notification.objects.filter(user=user, notification_type='missing_max_players')
        self.assertEqual(notifs.count(), 1)


@tag("unit")
class UnverifiedFriendRequestRateLimitTest(TestCase):

    def setUp(self):
        self.unverified = User.objects.create_user(
            username='unverified', password='testpass123',
        )

    def _create_users(self, *usernames, password='testpass123'):
        return [User.objects.create_user(username=u, password=password) for u in usernames]

    def test_unverified_can_send_up_to_3_pending(self):
        targets = self._create_users('target1', 'target2', 'target3')
        for t in targets:
            from club.models import Friendship
            self.assertTrue(Friendship.can_send_request(self.unverified, t))
            Friendship.objects.create(requester=self.unverified, receiver=t, status='pending')

    def test_unverified_blocked_on_4th_pending(self):
        from club.models import Friendship
        targets = self._create_users('target1', 'target2', 'target3', 'target4')
        for t in targets[:3]:
            Friendship.objects.create(requester=self.unverified, receiver=t, status='pending')
        self.assertFalse(Friendship.can_send_request(self.unverified, targets[3]))

    def test_verified_user_not_limited(self):
        from club.models import Friendship
        verified = User.objects.create_user(
            username='verified', password='testpass123',
            email_verified=True, email='verified@test.com',
        )
        targets = self._create_users('target1', 'target2', 'target3', 'target4')
        for t in targets[:3]:
            Friendship.objects.create(requester=verified, receiver=t, status='pending')
        self.assertTrue(Friendship.can_send_request(verified, targets[3]))

    def test_accepting_frees_up_slot(self):
        from club.models import Friendship
        targets = self._create_users('target1', 'target2', 'target3', 'target4')
        for t in targets[:3]:
            Friendship.objects.create(requester=self.unverified, receiver=t, status='pending')
        Friendship.objects.filter(requester=self.unverified, receiver=targets[0]).update(status='accepted')
        self.assertTrue(Friendship.can_send_request(self.unverified, targets[3]))

    def test_declining_frees_up_slot(self):
        from club.models import Friendship
        targets = self._create_users('target1', 'target2', 'target3', 'target4')
        for t in targets[:3]:
            Friendship.objects.create(requester=self.unverified, receiver=t, status='pending')
        Friendship.objects.filter(requester=self.unverified, receiver=targets[0]).update(status='declined')
        self.assertTrue(Friendship.can_send_request(self.unverified, targets[3]))

    def test_unverified_still_subject_to_decline_cooldown(self):
        from club.models import Friendship
        from django.utils import timezone
        target = self._create_users('target1')[0]
        Friendship.objects.create(
            requester=self.unverified, receiver=target,
            status='declined', decline_count=2, last_declined_at=timezone.now(),
        )
        self.assertFalse(Friendship.can_send_request(self.unverified, target))
