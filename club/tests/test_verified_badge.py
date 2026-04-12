from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from club.models import BoardGame, Event

User = get_user_model()


class VerifiedBadgeDashboardTest(TestCase):

    def test_verified_user_sees_blue_checkmark_on_dashboard(self):
        user = User.objects.create_user(
            username='verifieduser', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        self.client.login(username='verifieduser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'verified-badge')

    def test_unverified_user_does_not_see_checkmark_on_dashboard(self):
        user = User.objects.create_user(
            username='unverifieduser', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        self.client.login(username='unverifieduser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'verified-badge')


class VerifiedBadgeGameListTest(TestCase):

    def setUp(self):
        self.verified_owner = User.objects.create_user(
            username='verifiedowner', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        self.unverified_owner = User.objects.create_user(
            username='unverifiedowner', password='testpass123',
            email='unverified@example.com', email_verified=False
        )

    def test_verified_game_owner_shows_checkmark(self):
        BoardGame.objects.create(name='Catan', owner=self.verified_owner)
        self.client.login(username='verifiedowner', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'verified-badge')

    def test_unverified_game_owner_no_checkmark(self):
        BoardGame.objects.create(name='Risk', owner=self.unverified_owner)
        self.client.login(username='unverifiedowner', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertNotContains(response, 'verified-badge')


class VerifiedBadgeGameDetailTest(TestCase):

    def test_verified_owner_shows_checkmark_on_game_detail(self):
        owner = User.objects.create_user(
            username='verifiedowner', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        game = BoardGame.objects.create(name='Catan', owner=owner)
        self.client.login(username='verifiedowner', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(response, 'verified-badge')

    def test_unverified_owner_no_checkmark_on_game_detail(self):
        owner = User.objects.create_user(
            username='unverifiedowner', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        game = BoardGame.objects.create(name='Risk', owner=owner)
        self.client.login(username='unverifiedowner', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertNotContains(response, 'verified-badge')


class VerifiedBadgeEventListTest(TestCase):

    def test_verified_creator_shows_checkmark_in_event_list(self):
        creator = User.objects.create_user(
            username='verifiedcreator', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            created_by=creator
        )
        self.client.login(username='verifiedcreator', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, 'verified-badge')

    def test_unverified_creator_no_checkmark_in_event_list(self):
        creator = User.objects.create_user(
            username='unverifiedcreator', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            created_by=creator
        )
        self.client.login(username='unverifiedcreator', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertNotContains(response, 'verified-badge')


class VerifiedBadgeEventDetailTest(TestCase):

    def setUp(self):
        self.verified_user = User.objects.create_user(
            username='verifieduser', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        self.unverified_user = User.objects.create_user(
            username='unverifieduser', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        self.event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            created_by=self.verified_user
        )

    def test_verified_creator_shows_checkmark(self):
        self.client.login(username='verifieduser', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'pk': self.event.pk}))
        self.assertContains(response, 'verified-badge')

    def test_verified_attendee_shows_checkmark(self):
        from club.models import EventAttendance
        EventAttendance.objects.create(user=self.verified_user, event=self.event)
        self.client.login(username='verifieduser', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'pk': self.event.pk}))
        self.assertContains(response, 'verified-badge')

    def test_unverified_attendee_no_checkmark(self):
        from club.models import EventAttendance
        event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            created_by=self.unverified_user
        )
        EventAttendance.objects.create(user=self.unverified_user, event=event)
        self.client.login(username='unverifieduser', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'pk': event.pk}))
        self.assertNotContains(response, 'verified-badge')


class VerifiedBadgeEventResultsTest(TestCase):

    def setUp(self):
        self.verified_user = User.objects.create_user(
            username='verifiedvoter', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        self.unverified_user = User.objects.create_user(
            username='unverifiedvoter', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        self.event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            created_by=self.verified_user, show_individual_votes=True
        )
        self.game = BoardGame.objects.create(name='Catan', owner=self.verified_user)

    def test_verified_voter_shows_checkmark_in_individual_votes(self):
        from club.models import EventAttendance, Vote
        EventAttendance.objects.create(user=self.verified_user, event=self.event)
        Vote.objects.create(
            user=self.verified_user, event=self.event,
            board_game=self.game, rank=1
        )
        response = self.client.get(reverse('event_results', kwargs={'pk': self.event.pk}))
        self.assertContains(response, 'verified-badge')

    def test_unverified_voter_no_checkmark_in_individual_votes(self):
        from club.models import EventAttendance, Vote
        EventAttendance.objects.create(user=self.unverified_user, event=self.event)
        Vote.objects.create(
            user=self.unverified_user, event=self.event,
            board_game=self.game, rank=1
        )
        response = self.client.get(reverse('event_results', kwargs={'pk': self.event.pk}))
        self.assertNotContains(response, 'verified-badge')


class VerifiedBadgeManageUsersTest(TestCase):

    def test_verified_user_shows_checkmark_in_manage_users(self):
        admin = User.objects.create_user(
            username='admin', password='testpass123',
            is_site_admin=True, email='admin@example.com', email_verified=True
        )
        User.objects.create_user(
            username='verifieduser', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertContains(response, 'verified-badge')

    def test_unverified_user_no_checkmark_in_manage_users(self):
        admin = User.objects.create_user(
            username='admin', password='testpass123',
            is_site_admin=True, email='admin@example.com', email_verified=True
        )
        User.objects.create_user(
            username='unverifieduser', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertNotContains(response, 'verified-badge')
