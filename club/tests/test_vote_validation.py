from datetime import timedelta

from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from club.models import BoardGame, Event, EventAttendance, Group, GroupMembership, Vote

FUTURE_DATE = timezone.now() + timedelta(days=30)

User = get_user_model()


def _make_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_member(user, group):
    GroupMembership.objects.create(user=user, group=group, role='member')


def _vote_post_data(game_ids):
    data = {
        'form-TOTAL_FORMS': str(len(game_ids)),
        'form-INITIAL_FORMS': '0',
        'form-MIN_NUM_FORMS': '0',
        'form-MAX_NUM_FORMS': '1000',
    }
    for i, game_id in enumerate(game_ids):
        data[f'form-{i}-board_game'] = str(game_id)
    return data


# ---------------------------------------------------------------------------
# Group event vote validation
# ---------------------------------------------------------------------------

@tag("integration")
class VoteValidationTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_site_admin=True,
        )
        self.attendee = User.objects.create_user(
            username='attendee', password='testpass123',
        )
        self.group = Group.objects.create(name='Validation Group')
        _make_organizer(self.admin, self.group)
        _make_member(self.attendee, self.group)
        self.event = Event.objects.create(
            title='Validation Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.admin, group=self.group,
        )
        EventAttendance.objects.create(user=self.attendee, event=self.event)
        self.game1 = BoardGame.objects.create(name='Catan', owner=self.admin)
        self.game2 = BoardGame.objects.create(name='Chess', owner=self.admin)
        self.game3 = BoardGame.objects.create(name='Pandemic', owner=self.admin)
        self.url = reverse('event_vote', kwargs={
            'slug': self.group.slug, 'pk': self.event.pk,
        })

    def test_game_not_in_pool_rejected(self):
        outsider = User.objects.create_user(username='stranger', password='testpass123')
        outside_game = BoardGame.objects.create(name='Monopoly', owner=outsider)

        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            outside_game.pk,
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_game_not_in_pool_preserves_existing_votes(self):
        outsider = User.objects.create_user(username='stranger', password='testpass123')
        outside_game = BoardGame.objects.create(name='Monopoly', owner=outsider)
        Vote.objects.create(
            user=self.attendee, event=self.event,
            board_game=self.game1, rank=1,
        )

        self.client.login(username='attendee', password='testpass123')
        self.client.post(self.url, _vote_post_data([
            outside_game.pk,
        ]))
        self.assertTrue(Vote.objects.filter(
            user=self.attendee, event=self.event, board_game=self.game1,
        ).exists())

    def test_non_numeric_game_id_no_500(self):
        self.client.login(username='attendee', password='testpass123')
        data = _vote_post_data([self.game1.pk])
        data['form-0-board_game'] = 'abc'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_duplicate_game_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            self.game1.pk,
            self.game1.pk,
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_valid_submission_rank_derived_from_position(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            self.game1.pk,
            self.game2.pk,
        ]))
        self.assertEqual(response.status_code, 302)
        votes = Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).order_by('rank')
        self.assertEqual(votes.count(), 2)
        self.assertEqual(votes[0].board_game, self.game1)
        self.assertEqual(votes[0].rank, 1)
        self.assertEqual(votes[1].board_game, self.game2)
        self.assertEqual(votes[1].rank, 2)

    def test_valid_submission_replaces_existing(self):
        Vote.objects.create(
            user=self.attendee, event=self.event,
            board_game=self.game1, rank=1,
        )
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            self.game2.pk,
        ]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event, board_game=self.game1,
        ).exists())
        self.assertTrue(Vote.objects.filter(
            user=self.attendee, event=self.event, board_game=self.game2, rank=1,
        ).exists())

    def test_invalid_total_forms_no_500(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, {
            'form-TOTAL_FORMS': 'abc',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-board_game': str(self.game1.pk),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_empty_game_in_row_is_error(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, {
            'form-TOTAL_FORMS': '2',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-board_game': '',
            'form-1-board_game': str(self.game1.pk),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_nonexistent_game_id_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            99999,
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_zero_total_forms_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, {
            'form-TOTAL_FORMS': '0',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_single_row_valid(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            self.game1.pk,
        ]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).count(), 1)
        vote = Vote.objects.get(user=self.attendee, event=self.event)
        self.assertEqual(vote.board_game, self.game1)
        self.assertEqual(vote.rank, 1)

    def test_three_games_ranked_in_position_order(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            self.game1.pk,
            self.game2.pk,
            self.game3.pk,
        ]))
        self.assertEqual(response.status_code, 302)
        votes = Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).order_by('rank')
        self.assertEqual(votes.count(), 3)
        self.assertEqual(votes[0].rank, 1)
        self.assertEqual(votes[0].board_game, self.game1)
        self.assertEqual(votes[1].rank, 2)
        self.assertEqual(votes[1].board_game, self.game2)
        self.assertEqual(votes[2].rank, 3)
        self.assertEqual(votes[2].board_game, self.game3)


# ---------------------------------------------------------------------------
# Private event vote validation
# ---------------------------------------------------------------------------

@tag("integration")
class PrivateVoteValidationTest(TestCase):

    def setUp(self):
        self.creator = User.objects.create_user(
            username='creator', password='testpass123', email_verified=True,
        )
        self.attendee = User.objects.create_user(
            username='attendee', password='testpass123',
        )
        self.event = Event.objects.create(
            title='Private Validation Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.creator, group=None, privacy='public',
        )
        EventAttendance.objects.create(user=self.attendee, event=self.event)
        self.game1 = BoardGame.objects.create(name='Catan', owner=self.creator)
        self.game2 = BoardGame.objects.create(name='Chess', owner=self.creator)
        self.game3 = BoardGame.objects.create(name='Pandemic', owner=self.creator)
        self.url = reverse('private_event_vote', kwargs={'pk': self.event.pk})

    def test_game_not_in_pool_rejected(self):
        outsider = User.objects.create_user(username='stranger', password='testpass123')
        outside_game = BoardGame.objects.create(name='Monopoly', owner=outsider)

        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            outside_game.pk,
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_game_not_in_pool_preserves_existing_votes(self):
        outsider = User.objects.create_user(username='stranger', password='testpass123')
        outside_game = BoardGame.objects.create(name='Monopoly', owner=outsider)
        Vote.objects.create(
            user=self.attendee, event=self.event,
            board_game=self.game1, rank=1,
        )

        self.client.login(username='attendee', password='testpass123')
        self.client.post(self.url, _vote_post_data([
            outside_game.pk,
        ]))
        self.assertTrue(Vote.objects.filter(
            user=self.attendee, event=self.event, board_game=self.game1,
        ).exists())

    def test_non_numeric_game_id_no_500(self):
        self.client.login(username='attendee', password='testpass123')
        data = _vote_post_data([self.game1.pk])
        data['form-0-board_game'] = 'abc'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_duplicate_game_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            self.game1.pk,
            self.game1.pk,
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_valid_submission_rank_derived_from_position(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            self.game1.pk,
            self.game2.pk,
        ]))
        self.assertEqual(response.status_code, 302)
        votes = Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).order_by('rank')
        self.assertEqual(votes.count(), 2)
        self.assertEqual(votes[0].board_game, self.game1)
        self.assertEqual(votes[0].rank, 1)
        self.assertEqual(votes[1].board_game, self.game2)
        self.assertEqual(votes[1].rank, 2)

    def test_valid_submission_replaces_existing(self):
        Vote.objects.create(
            user=self.attendee, event=self.event,
            board_game=self.game1, rank=1,
        )
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            self.game2.pk,
        ]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event, board_game=self.game1,
        ).exists())
        self.assertTrue(Vote.objects.filter(
            user=self.attendee, event=self.event, board_game=self.game2, rank=1,
        ).exists())

    def test_invalid_total_forms_no_500(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, {
            'form-TOTAL_FORMS': 'abc',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-board_game': str(self.game1.pk),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_empty_game_in_row_is_error(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, {
            'form-TOTAL_FORMS': '2',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-board_game': '',
            'form-1-board_game': str(self.game1.pk),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_nonexistent_game_id_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            99999,
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_zero_total_forms_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, {
            'form-TOTAL_FORMS': '0',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_single_row_valid(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            self.game1.pk,
        ]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).count(), 1)
        vote = Vote.objects.get(user=self.attendee, event=self.event)
        self.assertEqual(vote.board_game, self.game1)
        self.assertEqual(vote.rank, 1)

    def test_three_games_ranked_in_position_order(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            self.game1.pk,
            self.game2.pk,
            self.game3.pk,
        ]))
        self.assertEqual(response.status_code, 302)
        votes = Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).order_by('rank')
        self.assertEqual(votes.count(), 3)
        self.assertEqual(votes[0].rank, 1)
        self.assertEqual(votes[0].board_game, self.game1)
        self.assertEqual(votes[1].rank, 2)
        self.assertEqual(votes[1].board_game, self.game2)
        self.assertEqual(votes[2].rank, 3)
        self.assertEqual(votes[2].board_game, self.game3)
