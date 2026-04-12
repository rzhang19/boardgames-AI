from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from club.models import BoardGame, Event, EventAttendance, Vote

User = get_user_model()


class BoardGameModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='gameowner', password='testpass123'
        )

    def test_create_board_game_with_all_fields(self):
        game = BoardGame.objects.create(
            name='Catan',
            description='A classic resource management game',
            owner=self.user,
            min_players=3,
            max_players=4,
        )
        self.assertEqual(game.name, 'Catan')
        self.assertEqual(game.description, 'A classic resource management game')
        self.assertEqual(game.owner, self.user)
        self.assertEqual(game.min_players, 3)
        self.assertEqual(game.max_players, 4)
        self.assertIsNotNone(game.created_at)

    def test_create_board_game_with_only_required_fields(self):
        game = BoardGame.objects.create(
            name='Chess',
            owner=self.user,
        )
        self.assertEqual(game.name, 'Chess')
        self.assertEqual(game.description, '')
        self.assertIsNone(game.min_players)
        self.assertIsNone(game.max_players)

    def test_board_game_string_representation(self):
        game = BoardGame.objects.create(
            name='Ticket to Ride',
            owner=self.user,
        )
        self.assertEqual(str(game), 'Ticket to Ride')

    def test_board_game_owner_relationship(self):
        game = BoardGame.objects.create(
            name='Pandemic',
            owner=self.user,
        )
        self.assertIn(game, self.user.boardgame_set.all())

    def test_board_game_bgg_fields_default_to_none(self):
        game = BoardGame.objects.create(
            name='Chess',
            owner=self.user,
        )
        self.assertIsNone(game.bgg_id)
        self.assertEqual(game.bgg_link, '')
        self.assertEqual(game.image_url, '')
        self.assertIsNone(game.bgg_last_synced)

    def test_board_game_with_bgg_data(self):
        from django.utils import timezone
        synced = timezone.now()
        game = BoardGame.objects.create(
            name='Catan',
            owner=self.user,
            bgg_id=13,
            bgg_link='https://boardgamegeek.com/boardgame/13/catan',
            image_url='https://cf.geekdo-images.com/pic123.png',
            bgg_last_synced=synced,
        )
        self.assertEqual(game.bgg_id, 13)
        self.assertEqual(game.bgg_link, 'https://boardgamegeek.com/boardgame/13/catan')
        self.assertEqual(game.image_url, 'https://cf.geekdo-images.com/pic123.png')
        self.assertEqual(game.bgg_last_synced, synced)

    def test_board_game_bgg_fields_are_optional(self):
        game = BoardGame.objects.create(
            name='Azul',
            owner=self.user,
            min_players=2,
            max_players=4,
        )
        self.assertIsNone(game.bgg_id)
        self.assertIsNone(game.bgg_last_synced)


class EventModelTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='adminuser', password='testpass123', is_organizer=True
        )

    def test_create_event_with_all_fields(self):
        from django.utils import timezone
        event_date = timezone.now() + timezone.timedelta(days=7)
        event = Event.objects.create(
            title='Friday Game Night',
            date=event_date,
            location='Community Center',
            description='Weekly game night',
            created_by=self.admin,
        )
        self.assertEqual(event.title, 'Friday Game Night')
        self.assertEqual(event.date, event_date)
        self.assertEqual(event.location, 'Community Center')
        self.assertEqual(event.description, 'Weekly game night')
        self.assertEqual(event.created_by, self.admin)

    def test_create_event_with_only_required_fields(self):
        from django.utils import timezone
        event_date = timezone.now() + timezone.timedelta(days=7)
        event = Event.objects.create(
            title='Quick Event',
            date=event_date,
            created_by=self.admin,
        )
        self.assertEqual(event.location, '')
        self.assertEqual(event.description, '')

    def test_event_string_representation(self):
        event = Event.objects.create(
            title='Board Game Bash',
            date='2026-05-01T18:00:00Z',
            created_by=self.admin,
        )
        self.assertEqual(str(event), 'Board Game Bash')

    def test_show_individual_votes_defaults_to_false(self):
        event = Event.objects.create(
            title='Test Event',
            date='2026-05-01T18:00:00Z',
            created_by=self.admin,
        )
        self.assertFalse(event.show_individual_votes)

    def test_is_active_defaults_to_true(self):
        event = Event.objects.create(
            title='Test Event',
            date='2026-05-01T18:00:00Z',
            created_by=self.admin,
        )
        self.assertTrue(event.is_active)


class EventAttendanceModelTest(TestCase):

    def setUp(self):
        self.user1 = User.objects.create_user(
            username='user1', password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='user2', password='testpass123'
        )
        self.admin = User.objects.create_user(
            username='eventadmin', password='testpass123', is_organizer=True
        )
        self.event = Event.objects.create(
            title='Test Event',
            date='2026-05-01T18:00:00Z',
            created_by=self.admin,
        )

    def test_create_event_attendance(self):
        attendance = EventAttendance.objects.create(
            user=self.user1,
            event=self.event,
        )
        self.assertEqual(attendance.user, self.user1)
        self.assertEqual(attendance.event, self.event)
        self.assertIsNotNone(attendance.joined_at)

    def test_unique_constraint_prevents_duplicate_attendance(self):
        EventAttendance.objects.create(
            user=self.user1,
            event=self.event,
        )
        with self.assertRaises(IntegrityError):
            EventAttendance.objects.create(
                user=self.user1,
                event=self.event,
            )

    def test_user_can_attend_multiple_events(self):
        event2 = Event.objects.create(
            title='Second Event',
            date='2026-06-01T18:00:00Z',
            created_by=self.admin,
        )
        EventAttendance.objects.create(
            user=self.user1,
            event=self.event,
        )
        attendance2 = EventAttendance.objects.create(
            user=self.user1,
            event=event2,
        )
        self.assertEqual(EventAttendance.objects.filter(user=self.user1).count(), 2)

    def test_multiple_users_can_attend_same_event(self):
        EventAttendance.objects.create(
            user=self.user1,
            event=self.event,
        )
        EventAttendance.objects.create(
            user=self.user2,
            event=self.event,
        )
        self.assertEqual(EventAttendance.objects.filter(event=self.event).count(), 2)


class VoteModelTest(TestCase):

    def setUp(self):
        self.user1 = User.objects.create_user(
            username='voter1', password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='voter2', password='testpass123'
        )
        self.admin = User.objects.create_user(
            username='voteadmin', password='testpass123', is_organizer=True
        )
        self.event = Event.objects.create(
            title='Vote Event',
            date='2026-05-01T18:00:00Z',
            created_by=self.admin,
        )
        self.event2 = Event.objects.create(
            title='Other Event',
            date='2026-06-01T18:00:00Z',
            created_by=self.admin,
        )
        self.game1 = BoardGame.objects.create(
            name='Catan', owner=self.user1
        )
        self.game2 = BoardGame.objects.create(
            name='Chess', owner=self.user1
        )

    def test_create_vote(self):
        vote = Vote.objects.create(
            user=self.user1,
            event=self.event,
            board_game=self.game1,
            rank=1,
        )
        self.assertEqual(vote.user, self.user1)
        self.assertEqual(vote.event, self.event)
        self.assertEqual(vote.board_game, self.game1)
        self.assertEqual(vote.rank, 1)

    def test_unique_constraint_same_rank_same_event(self):
        Vote.objects.create(
            user=self.user1,
            event=self.event,
            board_game=self.game1,
            rank=1,
        )
        with self.assertRaises(IntegrityError):
            Vote.objects.create(
                user=self.user1,
                event=self.event,
                board_game=self.game2,
                rank=1,
            )

    def test_unique_constraint_same_game_same_event(self):
        Vote.objects.create(
            user=self.user1,
            event=self.event,
            board_game=self.game1,
            rank=1,
        )
        with self.assertRaises(IntegrityError):
            Vote.objects.create(
                user=self.user1,
                event=self.event,
                board_game=self.game1,
                rank=2,
            )

    def test_same_game_different_events_allowed(self):
        Vote.objects.create(
            user=self.user1,
            event=self.event,
            board_game=self.game1,
            rank=1,
        )
        vote2 = Vote.objects.create(
            user=self.user1,
            event=self.event2,
            board_game=self.game1,
            rank=1,
        )
        self.assertIsNotNone(vote2)

    def test_same_rank_different_users_allowed(self):
        Vote.objects.create(
            user=self.user1,
            event=self.event,
            board_game=self.game1,
            rank=1,
        )
        vote2 = Vote.objects.create(
            user=self.user2,
            event=self.event,
            board_game=self.game2,
            rank=1,
        )
        self.assertIsNotNone(vote2)
