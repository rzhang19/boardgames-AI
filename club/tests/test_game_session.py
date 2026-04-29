from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from club.models import (
    BoardGame, Event, EventAttendance,
    GameSession, GameSessionPlayer,
    Group, GroupMembership,
)

User = get_user_model()


def _make_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_member(user, group):
    GroupMembership.objects.create(user=user, group=group, role='member')


@tag("unit")
class GameSessionModelTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.user = User.objects.create_user(username='user', password='pass')
        self.group = Group.objects.create(name='Session Group')
        _make_organizer(self.admin, self.group)
        self.event = Event.objects.create(
            title='Session Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.admin,
            group=self.group,
        )
        self.game = BoardGame.objects.create(name='Catan', owner=self.admin)

    def test_create_session(self):
        session = GameSession.objects.create(
            event=self.event,
            board_game=self.game,
            selection_method='manual',
            created_by=self.admin,
        )
        self.assertEqual(session.event, self.event)
        self.assertEqual(session.board_game, self.game)
        self.assertEqual(session.selection_method, 'manual')
        self.assertIsNotNone(session.played_at)

    def test_multiple_sessions_per_event(self):
        GameSession.objects.create(
            event=self.event, board_game=self.game,
            selection_method='random', created_by=self.admin,
        )
        GameSession.objects.create(
            event=self.event, board_game=self.game,
            selection_method='manual', created_by=self.admin,
        )
        self.assertEqual(GameSession.objects.filter(event=self.event).count(), 2)


@tag("unit")
class GameSessionPlayerModelTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.user = User.objects.create_user(username='user', password='pass')
        self.group = Group.objects.create(name='Player Group')
        _make_organizer(self.admin, self.group)
        self.event = Event.objects.create(
            title='Player Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.admin,
            group=self.group,
        )
        self.game = BoardGame.objects.create(name='Catan', owner=self.admin)
        self.session = GameSession.objects.create(
            event=self.event, board_game=self.game,
            selection_method='manual', created_by=self.admin,
        )

    def test_add_registered_player(self):
        player = GameSessionPlayer.objects.create(
            game_session=self.session, user=self.user,
        )
        self.assertEqual(player.user, self.user)
        self.assertEqual(player.guest_name, '')

    def test_add_guest_player(self):
        player = GameSessionPlayer.objects.create(
            game_session=self.session, guest_name='Guest1',
        )
        self.assertIsNone(player.user_id)
        self.assertEqual(player.guest_name, 'Guest1')

    def test_clean_validates_exactly_one_of_user_or_guest(self):
        from django.core.exceptions import ValidationError
        player = GameSessionPlayer(
            game_session=self.session,
            user=self.user,
            guest_name='Guest1',
        )
        with self.assertRaises(ValidationError):
            player.clean()

    def test_clean_validates_neither_user_nor_guest(self):
        from django.core.exceptions import ValidationError
        player = GameSessionPlayer(
            game_session=self.session,
        )
        with self.assertRaises(ValidationError):
            player.clean()

    def test_unique_constraint_registered_player(self):
        GameSessionPlayer.objects.create(
            game_session=self.session, user=self.user,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            GameSessionPlayer.objects.create(
                game_session=self.session, user=self.user,
            )

    def test_guest_names_not_unique(self):
        GameSessionPlayer.objects.create(
            game_session=self.session, guest_name='Guest',
        )
        player2 = GameSessionPlayer.objects.create(
            game_session=self.session, guest_name='Guest',
        )
        self.assertIsNotNone(player2.pk)


@tag("integration")
class PlayGameViewTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        self.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        self.group = Group.objects.create(name='Play Group')
        _make_organizer(self.organizer, self.group)
        _make_member(self.member, self.group)
        self.event = Event.objects.create(
            title='Play Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.member, event=self.event)
        self.game = BoardGame.objects.create(name='Catan', owner=self.organizer)

    def test_organizer_can_view_play_form(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_play_game', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_member_cannot_view_play_form(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('event_play_game', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_organizer_can_record_session(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_play_game', kwargs={'pk': self.event.pk}),
            {
                'board_game': self.game.pk,
                'selection_method': 'manual',
                'players': str(self.member.pk),
                'guest_names': '',
            }
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            GameSession.objects.filter(
                event=self.event, board_game=self.game
            ).exists()
        )
        session = GameSession.objects.get(event=self.event)
        self.assertTrue(
            GameSessionPlayer.objects.filter(
                game_session=session, user=self.member
            ).exists()
        )

    def test_organizer_can_record_session_with_guest(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_play_game', kwargs={'pk': self.event.pk}),
            {
                'board_game': self.game.pk,
                'selection_method': 'manual',
                'players': '',
                'guest_names': 'Guest1,Guest2',
            }
        )
        self.assertEqual(response.status_code, 302)
        session = GameSession.objects.get(event=self.event)
        self.assertEqual(
            GameSessionPlayer.objects.filter(
                game_session=session
            ).exclude(guest_name='').count(), 2
        )

    def test_unauthenticated_redirected(self):
        response = self.client.get(
            reverse('event_play_game', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)


@tag("integration")
class GameSessionDetailViewTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        self.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        self.group = Group.objects.create(name='Detail Group')
        _make_organizer(self.organizer, self.group)
        _make_member(self.member, self.group)
        self.event = Event.objects.create(
            title='Detail Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.member, event=self.event)
        self.game = BoardGame.objects.create(name='Catan', owner=self.organizer)
        self.session = GameSession.objects.create(
            event=self.event, board_game=self.game,
            selection_method='manual', created_by=self.organizer,
        )
        GameSessionPlayer.objects.create(
            game_session=self.session, user=self.member,
        )

    def test_authenticated_user_can_view_session(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('game_session_detail', kwargs={
                'event_pk': self.event.pk, 'pk': self.session.pk
            })
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Catan')

    def test_unauthenticated_redirected(self):
        response = self.client.get(
            reverse('game_session_detail', kwargs={
                'event_pk': self.event.pk, 'pk': self.session.pk
            })
        )
        self.assertEqual(response.status_code, 302)


@tag("integration")
class GameSessionDeleteTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        self.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        self.group = Group.objects.create(name='Delete Group')
        _make_organizer(self.organizer, self.group)
        _make_member(self.member, self.group)
        self.event = Event.objects.create(
            title='Delete Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
        )
        self.game = BoardGame.objects.create(name='Catan', owner=self.organizer)
        self.session = GameSession.objects.create(
            event=self.event, board_game=self.game,
            selection_method='manual', created_by=self.organizer,
        )

    def test_organizer_can_delete_session(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('game_session_delete', kwargs={
                'event_pk': self.event.pk, 'pk': self.session.pk
            })
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(GameSession.objects.filter(pk=self.session.pk).exists())

    def test_member_cannot_delete_session(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.post(
            reverse('game_session_delete', kwargs={
                'event_pk': self.event.pk, 'pk': self.session.pk
            })
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_shows_confirmation_on_get(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('game_session_delete', kwargs={
                'event_pk': self.event.pk, 'pk': self.session.pk
            })
        )
        self.assertEqual(response.status_code, 200)
