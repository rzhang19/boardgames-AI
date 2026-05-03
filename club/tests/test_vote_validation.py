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


def _vote_post_data(entries):
    data = {
        'form-TOTAL_FORMS': str(len(entries)),
        'form-INITIAL_FORMS': '0',
        'form-MIN_NUM_FORMS': '0',
        'form-MAX_NUM_FORMS': '1000',
    }
    for i, (game_id, rank) in enumerate(entries):
        data[f'form-{i}-board_game'] = str(game_id)
        data[f'form-{i}-rank'] = str(rank)
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
        self.url = reverse('event_vote', kwargs={
            'slug': self.group.slug, 'pk': self.event.pk,
        })

    def test_game_not_in_pool_rejected(self):
        outsider = User.objects.create_user(username='stranger', password='testpass123')
        outside_game = BoardGame.objects.create(name='Monopoly', owner=outsider)

        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (outside_game.pk, 1),
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
            (outside_game.pk, 1),
        ]))
        self.assertTrue(Vote.objects.filter(
            user=self.attendee, event=self.event, board_game=self.game1,
        ).exists())

    def test_non_numeric_game_id_no_500(self):
        self.client.login(username='attendee', password='testpass123')
        data = _vote_post_data([('abc', 1)])
        data['form-0-board_game'] = 'abc'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_non_numeric_rank_no_500(self):
        self.client.login(username='attendee', password='testpass123')
        data = _vote_post_data([(self.game1.pk, 1)])
        data['form-0-rank'] = 'abc'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_rank_zero_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (self.game1.pk, 0),
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_negative_rank_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (self.game1.pk, -5),
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_duplicate_ranks_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (self.game1.pk, 1),
            (self.game2.pk, 1),
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_duplicate_game_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (self.game1.pk, 1),
            (self.game1.pk, 2),
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_valid_submission_still_works(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (self.game1.pk, 1),
            (self.game2.pk, 2),
        ]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).count(), 2)

    def test_valid_submission_replaces_existing(self):
        Vote.objects.create(
            user=self.attendee, event=self.event,
            board_game=self.game1, rank=1,
        )
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (self.game2.pk, 1),
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
            'form-0-rank': '1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_empty_rows_skipped_not_error(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, {
            'form-TOTAL_FORMS': '3',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-board_game': '',
            'form-0-rank': '',
            'form-1-board_game': str(self.game1.pk),
            'form-1-rank': '1',
            'form-2-board_game': '',
            'form-2-rank': '',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).count(), 1)

    def test_nonexistent_game_id_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (99999, 1),
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())


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
        self.url = reverse('private_event_vote', kwargs={'pk': self.event.pk})

    def test_game_not_in_pool_rejected(self):
        outsider = User.objects.create_user(username='stranger', password='testpass123')
        outside_game = BoardGame.objects.create(name='Monopoly', owner=outsider)

        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (outside_game.pk, 1),
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
            (outside_game.pk, 1),
        ]))
        self.assertTrue(Vote.objects.filter(
            user=self.attendee, event=self.event, board_game=self.game1,
        ).exists())

    def test_non_numeric_game_id_no_500(self):
        self.client.login(username='attendee', password='testpass123')
        data = _vote_post_data([('abc', 1)])
        data['form-0-board_game'] = 'abc'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_non_numeric_rank_no_500(self):
        self.client.login(username='attendee', password='testpass123')
        data = _vote_post_data([(self.game1.pk, 1)])
        data['form-0-rank'] = 'abc'
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_rank_zero_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (self.game1.pk, 0),
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_negative_rank_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (self.game1.pk, -5),
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_duplicate_ranks_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (self.game1.pk, 1),
            (self.game2.pk, 1),
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_duplicate_game_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (self.game1.pk, 1),
            (self.game1.pk, 2),
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_valid_submission_still_works(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (self.game1.pk, 1),
            (self.game2.pk, 2),
        ]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).count(), 2)

    def test_valid_submission_replaces_existing(self):
        Vote.objects.create(
            user=self.attendee, event=self.event,
            board_game=self.game1, rank=1,
        )
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (self.game2.pk, 1),
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
            'form-0-rank': '1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())

    def test_empty_rows_skipped_not_error(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, {
            'form-TOTAL_FORMS': '3',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-board_game': '',
            'form-0-rank': '',
            'form-1-board_game': str(self.game1.pk),
            'form-1-rank': '1',
            'form-2-board_game': '',
            'form-2-rank': '',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).count(), 1)

    def test_nonexistent_game_id_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(self.url, _vote_post_data([
            (99999, 1),
        ]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event,
        ).exists())
