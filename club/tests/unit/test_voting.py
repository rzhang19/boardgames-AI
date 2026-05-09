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
