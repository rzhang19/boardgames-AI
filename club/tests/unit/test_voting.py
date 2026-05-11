from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, tag
from django.utils import timezone

from club.borda import calculate_borda_scores
from club.models import BoardGame, Event, EventAttendance, Group, Vote

FUTURE_DATE = timezone.now() + timedelta(days=30)

User = get_user_model()


@tag("unit")
class VoteModelTest(TestCase):

    def setUp(self):
        self.user1 = User.objects.create_user(
            username='voter1', password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='voter2', password='testpass123'
        )
        self.admin = User.objects.create_user(
            username='voteadmin', password='testpass123', is_site_admin=True
        )
        self.group = Group.objects.create(name='Vote Group')
        self.event = Event.objects.create(
            title='Vote Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.admin,
            group=self.group,
        )
        self.event2 = Event.objects.create(
            title='Other Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.admin,
            group=self.group,
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


@tag("unit")
class BordaScoreCalculationTest(TestCase):

    def setUp(self):
        self.user1 = User.objects.create_user(
            username='voter1', password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='voter2', password='testpass123'
        )
        self.user3 = User.objects.create_user(
            username='voter3', password='testpass123'
        )
        self.admin = User.objects.create_user(
            username='eventadmin', password='testpass123', is_site_admin=True
        )
        self.group = Group.objects.create(name='Borda Group')
        self.event = Event.objects.create(
            title='Borda Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.admin,
            group=self.group,
        )
        self.game1 = BoardGame.objects.create(
            name='Catan', owner=self.admin
        )
        self.game2 = BoardGame.objects.create(
            name='Chess', owner=self.admin
        )
        self.game3 = BoardGame.objects.create(
            name='Azul', owner=self.admin
        )

    def test_single_user_ranks_n_games(self):
        """Given a user ranks 3 games, When calculating Borda scores, Then rank 1 gets 3 points, rank 2 gets 2, rank 3 gets 1"""
        Vote.objects.create(user=self.user1, event=self.event, board_game=self.game1, rank=1)
        Vote.objects.create(user=self.user1, event=self.event, board_game=self.game2, rank=2)
        Vote.objects.create(user=self.user1, event=self.event, board_game=self.game3, rank=3)

        scores = calculate_borda_scores(self.event)

        self.assertEqual(scores[self.game1.pk], 3)
        self.assertEqual(scores[self.game2.pk], 2)
        self.assertEqual(scores[self.game3.pk], 1)

    def test_multiple_users_scores_are_summed(self):
        """Given two users rank games, When calculating Borda scores, Then scores are summed across users"""
        Vote.objects.create(user=self.user1, event=self.event, board_game=self.game1, rank=1)
        Vote.objects.create(user=self.user1, event=self.event, board_game=self.game2, rank=2)

        Vote.objects.create(user=self.user2, event=self.event, board_game=self.game1, rank=1)
        Vote.objects.create(user=self.user2, event=self.event, board_game=self.game2, rank=2)

        scores = calculate_borda_scores(self.event)

        self.assertEqual(scores[self.game1.pk], 4)
        self.assertEqual(scores[self.game2.pk], 2)

    def test_no_votes_returns_empty_dict(self):
        """Given no votes exist, When calculating Borda scores, Then empty dict is returned"""
        scores = calculate_borda_scores(self.event)

        self.assertEqual(scores, {})

    def test_single_game_single_vote_gets_one_point(self):
        """Given a user votes for 1 game, When calculating Borda scores, Then that game gets 1 point"""
        Vote.objects.create(user=self.user1, event=self.event, board_game=self.game1, rank=1)

        scores = calculate_borda_scores(self.event)

        self.assertEqual(scores[self.game1.pk], 1)

    def test_attendees_only_filters_non_attending_voters(self):
        """Given attendees_only=True, When calculating Borda scores, Then only attending users' votes are counted"""
        EventAttendance.objects.create(user=self.user1, event=self.event)

        Vote.objects.create(user=self.user1, event=self.event, board_game=self.game1, rank=1)
        Vote.objects.create(user=self.user2, event=self.event, board_game=self.game1, rank=1)

        scores = calculate_borda_scores(self.event, attendees_only=True)

        self.assertEqual(scores[self.game1.pk], 1)

    def test_attendees_only_false_includes_all_voters(self):
        """Given attendees_only=False, When calculating Borda scores, Then all votes count regardless of attendance"""
        Vote.objects.create(user=self.user1, event=self.event, board_game=self.game1, rank=1)
        Vote.objects.create(user=self.user2, event=self.event, board_game=self.game1, rank=1)

        scores = calculate_borda_scores(self.event, attendees_only=False)

        self.assertEqual(scores[self.game1.pk], 2)

    def test_higher_ranked_game_has_more_points(self):
        """Given two games with different rankings, When calculating Borda scores, Then the top-ranked game has more points"""
        Vote.objects.create(user=self.user1, event=self.event, board_game=self.game1, rank=1)
        Vote.objects.create(user=self.user1, event=self.event, board_game=self.game2, rank=2)

        scores = calculate_borda_scores(self.event)

        self.assertGreater(scores[self.game1.pk], scores[self.game2.pk])

    def test_unranked_game_gets_zero_points(self):
        """Given a user ranks some games but not others, When calculating Borda scores, Then unranked games get 0 points"""
        Vote.objects.create(user=self.user1, event=self.event, board_game=self.game1, rank=1)
        Vote.objects.create(user=self.user1, event=self.event, board_game=self.game2, rank=2)

        scores = calculate_borda_scores(self.event)

        self.assertNotIn(self.game3.pk, scores)

    def test_three_users_mixed_rankings(self):
        """Given three users with mixed rankings, When calculating Borda scores, Then points are correctly summed"""
        Vote.objects.create(user=self.user1, event=self.event, board_game=self.game1, rank=1)
        Vote.objects.create(user=self.user1, event=self.event, board_game=self.game2, rank=2)
        Vote.objects.create(user=self.user1, event=self.event, board_game=self.game3, rank=3)

        Vote.objects.create(user=self.user2, event=self.event, board_game=self.game2, rank=1)
        Vote.objects.create(user=self.user2, event=self.event, board_game=self.game1, rank=2)

        Vote.objects.create(user=self.user3, event=self.event, board_game=self.game3, rank=1)

        scores = calculate_borda_scores(self.event)

        self.assertEqual(scores[self.game1.pk], 3 + 1)
        self.assertEqual(scores[self.game2.pk], 2 + 2)
        self.assertEqual(scores[self.game3.pk], 1 + 1)


@tag("unit")
class BordaCountTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_site_admin=True
        )
        self.group = Group.objects.create(name='Borda Group')
        self.event = Event.objects.create(
            title='Borda Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.admin, group=self.group
        )
        self.game1 = BoardGame.objects.create(name='Catan', owner=self.admin)
        self.game2 = BoardGame.objects.create(name='Chess', owner=self.admin)
        self.game3 = BoardGame.objects.create(name='Pandemic', owner=self.admin)

    def test_single_user_ranking(self):
        user = User.objects.create_user(username='voter1', password='testpass123')
        EventAttendance.objects.create(user=user, event=self.event)
        Vote.objects.create(user=user, event=self.event, board_game=self.game1, rank=1)
        Vote.objects.create(user=user, event=self.event, board_game=self.game2, rank=2)
        Vote.objects.create(user=user, event=self.event, board_game=self.game3, rank=3)
        scores = calculate_borda_scores(self.event)
        self.assertEqual(scores[self.game1.pk], 3)
        self.assertEqual(scores[self.game2.pk], 2)
        self.assertEqual(scores[self.game3.pk], 1)

    def test_multiple_users(self):
        user1 = User.objects.create_user(username='voter1', password='testpass123')
        user2 = User.objects.create_user(username='voter2', password='testpass123')
        EventAttendance.objects.create(user=user1, event=self.event)
        EventAttendance.objects.create(user=user2, event=self.event)
        Vote.objects.create(user=user1, event=self.event, board_game=self.game1, rank=1)
        Vote.objects.create(user=user1, event=self.event, board_game=self.game2, rank=2)
        Vote.objects.create(user=user2, event=self.event, board_game=self.game2, rank=1)
        Vote.objects.create(user=user2, event=self.event, board_game=self.game3, rank=2)
        scores = calculate_borda_scores(self.event)
        self.assertEqual(scores[self.game1.pk], 2)
        self.assertEqual(scores[self.game2.pk], 1 + 2)
        self.assertEqual(scores[self.game3.pk], 1)

    def test_unranked_game_gets_zero_points(self):
        user = User.objects.create_user(username='voter1', password='testpass123')
        EventAttendance.objects.create(user=user, event=self.event)
        Vote.objects.create(user=user, event=self.event, board_game=self.game1, rank=1)
        scores = calculate_borda_scores(self.event)
        self.assertEqual(scores.get(self.game2.pk, 0), 0)

    def test_no_votes_returns_empty(self):
        scores = calculate_borda_scores(self.event)
        self.assertEqual(scores, {})

    def test_borda_filters_by_attendance(self):
        attendee = User.objects.create_user(username='attendee', password='testpass123')
        non_attendee = User.objects.create_user(username='noattend', password='testpass123')
        EventAttendance.objects.create(user=attendee, event=self.event)
        Vote.objects.create(user=attendee, event=self.event, board_game=self.game1, rank=1)
        Vote.objects.create(user=non_attendee, event=self.event, board_game=self.game2, rank=1)
        scores = calculate_borda_scores(self.event, attendees_only=True)
        self.assertEqual(scores[self.game1.pk], 1)
        self.assertFalse(self.game2.pk in scores)

    def test_borda_without_attendance_filter_includes_all(self):
        attendee = User.objects.create_user(username='attendee', password='testpass123')
        non_attendee = User.objects.create_user(username='noattend', password='testpass123')
        EventAttendance.objects.create(user=attendee, event=self.event)
        Vote.objects.create(user=attendee, event=self.event, board_game=self.game1, rank=1)
        Vote.objects.create(user=non_attendee, event=self.event, board_game=self.game2, rank=1)
        scores = calculate_borda_scores(self.event, attendees_only=False)
        self.assertEqual(scores[self.game1.pk], 1)
        self.assertEqual(scores[self.game2.pk], 1)


@tag("unit")
class EventVotingModelTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_site_admin=True
        )
        self.group = Group.objects.create(name='Voting Model Group')

    def test_phase_returns_upcoming_for_future_event(self):
        event_date = timezone.now() + timedelta(days=7)
        event = Event.objects.create(
            title='Future Event', date=event_date, created_by=self.admin,
            group=self.group, voting_deadline=event_date,
        )
        self.assertEqual(event.phase, 'upcoming')

    def test_phase_returns_completed_for_past_event(self):
        event_date = timezone.now() - timedelta(days=1)
        event = Event.objects.create(
            title='Past Event', date=event_date, created_by=self.admin,
            group=self.group, voting_deadline=event_date,
        )
        self.assertEqual(event.phase, 'completed')

    def test_is_currently_active_true_when_active_and_future(self):
        event = Event.objects.create(
            title='Active Future', date=timezone.now() + timedelta(days=7),
            created_by=self.admin, group=self.group, is_active=True,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        self.assertTrue(event.is_currently_active)

    def test_is_currently_active_false_when_inactive(self):
        event = Event.objects.create(
            title='Inactive Future', date=timezone.now() + timedelta(days=7),
            created_by=self.admin, group=self.group, is_active=False,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        self.assertFalse(event.is_currently_active)

    def test_is_currently_active_false_when_past(self):
        event = Event.objects.create(
            title='Active Past', date=timezone.now() - timedelta(days=1),
            created_by=self.admin, group=self.group, is_active=True,
            voting_deadline=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(event.is_currently_active)

    def test_is_currently_active_false_when_inactive_and_past(self):
        event = Event.objects.create(
            title='Inactive Past', date=timezone.now() - timedelta(days=1),
            created_by=self.admin, group=self.group, is_active=False,
            voting_deadline=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(event.is_currently_active)

    def test_is_voting_open_true_when_all_conditions_met(self):
        event = Event.objects.create(
            title='Open Event', date=timezone.now() + timedelta(days=7),
            created_by=self.admin, group=self.group, is_active=True,
            voting_open=True, voting_deadline=timezone.now() + timedelta(days=7),
        )
        self.assertTrue(event.is_voting_open)

    def test_is_voting_open_false_when_is_active_false(self):
        event = Event.objects.create(
            title='Inactive Event', date=timezone.now() + timedelta(days=7),
            created_by=self.admin, group=self.group, is_active=False,
            voting_open=True, voting_deadline=timezone.now() + timedelta(days=7),
        )
        self.assertFalse(event.is_voting_open)

    def test_is_voting_open_false_when_voting_open_false(self):
        event = Event.objects.create(
            title='Paused Event', date=timezone.now() + timedelta(days=7),
            created_by=self.admin, group=self.group, is_active=True,
            voting_open=False, voting_deadline=timezone.now() + timedelta(days=7),
        )
        self.assertFalse(event.is_voting_open)

    def test_is_voting_open_false_when_past_voting_deadline(self):
        event = Event.objects.create(
            title='Deadline Passed', date=timezone.now() + timedelta(days=7),
            created_by=self.admin, group=self.group, is_active=True,
            voting_open=True, voting_deadline=timezone.now() - timedelta(hours=1),
        )
        self.assertFalse(event.is_voting_open)

    def test_is_voting_open_true_when_before_voting_deadline(self):
        event = Event.objects.create(
            title='Before Deadline', date=timezone.now() + timedelta(days=7),
            created_by=self.admin, group=self.group, is_active=True,
            voting_open=True, voting_deadline=timezone.now() + timedelta(hours=1),
        )
        self.assertTrue(event.is_voting_open)

    def test_is_voting_open_false_when_voting_open_false_and_past(self):
        event = Event.objects.create(
            title='Paused Past', date=timezone.now() - timedelta(days=1),
            created_by=self.admin, group=self.group, is_active=True,
            voting_open=False, voting_deadline=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(event.is_voting_open)

    def test_voting_open_defaults_to_true(self):
        event_date = timezone.now() + timedelta(days=7)
        event = Event.objects.create(
            title='New Event', date=event_date, created_by=self.admin,
            group=self.group, voting_deadline=event_date,
        )
        self.assertTrue(event.voting_open)

    def test_voting_deadline_defaults_to_event_date(self):
        event_date = timezone.now() + timedelta(days=7)
        event = Event.objects.create(
            title='New Event', date=event_date, created_by=self.admin,
            group=self.group, voting_deadline=event_date,
        )
        self.assertEqual(event.voting_deadline, event.date)

    def test_sync_sets_voting_open_false_when_deadline_passed(self):
        event = Event.objects.create(
            title='Expired Deadline', date=timezone.now() + timedelta(days=7),
            created_by=self.admin, group=self.group, is_active=True,
            voting_open=True, voting_deadline=timezone.now() - timedelta(hours=1),
        )
        event.sync_voting_status()
        event.refresh_from_db()
        self.assertFalse(event.voting_open)

    def test_sync_does_not_change_when_voting_still_open(self):
        event = Event.objects.create(
            title='Still Open', date=timezone.now() + timedelta(days=7),
            created_by=self.admin, group=self.group, is_active=True,
            voting_open=True, voting_deadline=timezone.now() + timedelta(hours=1),
        )
        event.sync_voting_status()
        event.refresh_from_db()
        self.assertTrue(event.voting_open)

    def test_sync_does_not_change_when_already_false(self):
        event = Event.objects.create(
            title='Already Paused', date=timezone.now() + timedelta(days=7),
            created_by=self.admin, group=self.group, is_active=True,
            voting_open=False, voting_deadline=timezone.now() + timedelta(days=7),
        )
        event.sync_voting_status()
        event.refresh_from_db()
        self.assertFalse(event.voting_open)

    def test_sync_sets_voting_open_false_when_event_inactive(self):
        event = Event.objects.create(
            title='Inactive', date=timezone.now() + timedelta(days=7),
            created_by=self.admin, group=self.group, is_active=False,
            voting_open=True, voting_deadline=timezone.now() + timedelta(days=7),
        )
        event.sync_voting_status()
        event.refresh_from_db()
        self.assertFalse(event.voting_open)


@tag("unit")
class GroupGameBordaScoreTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.group = Group.objects.create(name='Borda Group')
        cls.event = Event.objects.create(
            title='Borda Event',
            date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=cls.organizer,
            group=cls.group,
        )
        cls.group_game = BoardGame.objects.create(
            name='Group Catan', group=cls.group,
            min_players=3, max_players=4, complexity='medium',
        )
        cls.user_game = BoardGame.objects.create(
            name='User Chess', owner=cls.organizer,
            min_players=2, max_players=2, complexity='light',
        )

    def test_borda_score_for_group_owned_game(self):
        user = User.objects.create_user(username='voter', password='testpass123')
        EventAttendance.objects.create(user=user, event=self.event)
        Vote.objects.create(user=user, event=self.event, board_game=self.group_game, rank=1)
        Vote.objects.create(user=user, event=self.event, board_game=self.user_game, rank=2)
        scores = calculate_borda_scores(self.event)
        self.assertEqual(scores[self.group_game.pk], 2)
        self.assertEqual(scores[self.user_game.pk], 1)

    def test_borda_group_game_scores_equal_to_user_game_with_same_votes(self):
        user1 = User.objects.create_user(username='voter1', password='testpass123')
        EventAttendance.objects.create(user=user1, event=self.event)
        Vote.objects.create(user=user1, event=self.event, board_game=self.group_game, rank=1)
        Vote.objects.create(user=user1, event=self.event, board_game=self.user_game, rank=2)
        user2 = User.objects.create_user(username='voter2', password='testpass123')
        EventAttendance.objects.create(user=user2, event=self.event)
        Vote.objects.create(user=user2, event=self.event, board_game=self.group_game, rank=2)
        Vote.objects.create(user=user2, event=self.event, board_game=self.user_game, rank=1)
        scores = calculate_borda_scores(self.event)
        self.assertEqual(scores[self.group_game.pk], scores[self.user_game.pk])
