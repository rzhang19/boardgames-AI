from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from club.models import BoardGame, Notification

User = get_user_model()


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


class NotificationContextProcessorTest(TestCase):

    def test_authenticated_user_sees_unread_count(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        Notification.objects.create(user=user, message='Unread 1')
        Notification.objects.create(user=user, message='Unread 2')
        Notification.objects.create(user=user, message='Read', is_read=True)
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['unread_notification_count'], 2)

    def test_anonymous_user_sees_zero_count(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['unread_notification_count'], 0)

    def test_badge_display_under_nine(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        for i in range(5):
            Notification.objects.create(user=user, message=f'Msg {i}')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['notification_badge_display'], '5')

    def test_badge_display_nine_plus(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        for i in range(12):
            Notification.objects.create(user=user, message=f'Msg {i}')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['notification_badge_display'], '9+')

    def test_badge_display_exactly_nine(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        for i in range(9):
            Notification.objects.create(user=user, message=f'Msg {i}')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['notification_badge_display'], '9')

    def test_badge_display_zero(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['notification_badge_display'], '0')


class NotificationListViewTest(TestCase):

    def test_notification_list_requires_login(self):
        response = self.client.get(reverse('notification_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_notification_list_shows_users_notifications(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        other = User.objects.create_user(username='otheruser', password='testpass123')
        Notification.objects.create(user=user, message='My notif')
        Notification.objects.create(user=other, message='Other notif')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('notification_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My notif')
        self.assertNotContains(response, 'Other notif')

    def test_notification_list_ordered_newest_first(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        Notification.objects.create(user=user, message='First')
        Notification.objects.create(user=user, message='Second')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('notification_list'))
        content = response.content.decode()
        self.assertGreater(content.index('Second'), 0)
        first_pos = content.index('First')
        second_pos = content.index('Second')
        self.assertLess(second_pos, first_pos)


class NotificationMarkReadTest(TestCase):

    def test_mark_read_requires_login(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Test')
        response = self.client.post(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_mark_read_marks_as_read(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Test')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_mark_read_redirects_to_notification_url(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(
            user=user, message='Test',
            url='/games/1/', url_label='Edit',
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/games/1/')

    def test_mark_read_redirects_to_list_when_no_url(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Test')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('notification_list'))

    def test_mark_read_requires_post(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Test')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, 405)

    def test_cannot_mark_other_users_notification(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        other = User.objects.create_user(username='otheruser', password='testpass123')
        notif = Notification.objects.create(user=other, message='Other notif')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, 404)

    def test_mark_read_already_read_is_idempotent(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Test', is_read=True)
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, 302)
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)


class NotificationMarkAllReadTest(TestCase):

    def test_mark_all_read_requires_login(self):
        response = self.client.post(reverse('notification_mark_all_read'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_mark_all_read_marks_all_as_read(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        Notification.objects.create(user=user, message='One')
        Notification.objects.create(user=user, message='Two')
        Notification.objects.create(user=user, message='Three')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_mark_all_read'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(user=user, is_read=False).count(), 0)
        self.assertEqual(Notification.objects.filter(user=user, is_read=True).count(), 3)

    def test_mark_all_read_does_not_affect_other_users(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        other = User.objects.create_user(username='otheruser', password='testpass123')
        Notification.objects.create(user=user, message='Mine')
        Notification.objects.create(user=other, message='Theirs')
        self.client.login(username='testuser', password='testpass123')
        self.client.post(reverse('notification_mark_all_read'))
        self.assertEqual(Notification.objects.filter(user=other, is_read=False).count(), 1)

    def test_mark_all_read_requires_post(self):
        User.objects.create_user(username='testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('notification_mark_all_read'))
        self.assertEqual(response.status_code, 405)


class NotificationDeleteSelectedTest(TestCase):

    def test_delete_selected_requires_login(self):
        response = self.client.post(reverse('notification_delete_selected'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_delete_selected_deletes_chosen_notifications(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif1 = Notification.objects.create(user=user, message='Read 1', is_read=True)
        notif2 = Notification.objects.create(user=user, message='Read 2', is_read=True)
        Notification.objects.create(user=user, message='Unread')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_delete_selected'), {
            'selected_notifications': [notif1.pk, notif2.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(user=user).count(), 1)

    def test_delete_selected_does_not_delete_other_users(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        other = User.objects.create_user(username='otheruser', password='testpass123')
        other_notif = Notification.objects.create(user=other, message='Other', is_read=True)
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_delete_selected'), {
            'selected_notifications': [other_notif.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(user=other).count(), 1)

    def test_delete_selected_does_not_delete_unread(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Unread', is_read=False)
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_delete_selected'), {
            'selected_notifications': [notif.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(user=user).count(), 1)

    def test_delete_selected_with_no_selection(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        Notification.objects.create(user=user, message='Keep', is_read=True)
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_delete_selected'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(user=user).count(), 1)

    def test_delete_selected_requires_post(self):
        User.objects.create_user(username='testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('notification_delete_selected'))
        self.assertEqual(response.status_code, 405)


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
        self.client.post(reverse('game_edit', kwargs={'pk': game.pk}), {
            'name': 'Catan',
            'description': '',
            'min_players': 3,
            'max_players': 4,
            'complexity': 'medium',
            'bgg_id': '',
        })
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)


class MissingComplexityNotificationOnLoginTest(TestCase):

    def test_notifications_generated_on_login(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        BoardGame.objects.create(name='Catan', owner=user)
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'testpass123',
        })
        notifs = Notification.objects.filter(user=user, notification_type='missing_complexity')
        self.assertEqual(notifs.count(), 1)

    def test_no_notifications_when_all_games_have_complexity(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        BoardGame.objects.create(name='Catan', owner=user, complexity='medium')
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'testpass123',
        })
        notifs = Notification.objects.filter(user=user, notification_type='missing_complexity')
        self.assertEqual(notifs.count(), 0)


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
