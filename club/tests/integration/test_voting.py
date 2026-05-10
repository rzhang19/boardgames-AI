import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from club.borda import calculate_borda_scores
from club.models import (
    BoardGame,
    Event,
    EventAttendance,
    EventPresence,
    Group,
    GroupMembership,
    Notification,
    Vote,
)

FUTURE_DATE = timezone.now() + timedelta(days=30)

User = get_user_model()


def _make_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_group_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='organizer')


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


@tag("integration")
class VoteViewAccessTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_site_admin=True
        )
        self.attendee = User.objects.create_user(
            username='attendee', password='testpass123'
        )
        self.non_attendee = User.objects.create_user(
            username='outsider', password='testpass123'
        )
        self.group = Group.objects.create(name='Vote Group')
        _make_organizer(self.admin, self.group)
        _make_member(self.attendee, self.group)
        self.event = Event.objects.create(
            title='Vote Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.admin, group=self.group
        )
        EventAttendance.objects.create(user=self.attendee, event=self.event)
        self.game1 = BoardGame.objects.create(name='Catan', owner=self.admin)
        self.game2 = BoardGame.objects.create(name='Chess', owner=self.admin)

    def test_vote_page_requires_login(self):
        response = self.client.get(reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_non_attendee_cannot_vote(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 403)

    def test_attendee_can_access_vote_page(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)


@tag("integration")
class VoteSubmissionTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_site_admin=True
        )
        self.attendee = User.objects.create_user(
            username='attendee', password='testpass123'
        )
        self.group = Group.objects.create(name='Submit Group')
        _make_organizer(self.admin, self.group)
        _make_member(self.attendee, self.group)
        self.event = Event.objects.create(
            title='Vote Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.admin, group=self.group
        )
        EventAttendance.objects.create(user=self.attendee, event=self.event)
        self.game1 = BoardGame.objects.create(name='Catan', owner=self.admin)
        self.game2 = BoardGame.objects.create(name='Chess', owner=self.admin)

    def test_attendee_can_submit_votes(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}), {
            'form-TOTAL_FORMS': '2',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-board_game': str(self.game1.pk),
            'form-1-board_game': str(self.game2.pk),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Vote.objects.filter(user=self.attendee, event=self.event).count(), 2)

    def test_submit_zero_votes_is_rejected(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}), {
            'form-TOTAL_FORMS': '0',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Vote.objects.filter(user=self.attendee, event=self.event).count(), 0)

    def test_submit_votes_replaces_existing_votes(self):
        Vote.objects.create(user=self.attendee, event=self.event,
                            board_game=self.game1, rank=1)
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}), {
            'form-TOTAL_FORMS': '1',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-board_game': str(self.game2.pk),
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event, board_game=self.game1
        ).exists())
        self.assertTrue(Vote.objects.filter(
            user=self.attendee, event=self.event, board_game=self.game2
        ).exists())

    def test_non_attendee_cannot_submit_votes(self):
        non_attendee = User.objects.create_user(username='outsider', password='testpass123')
        self.client.login(username='outsider', password='testpass123')
        response = self.client.post(reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}), {
            'form-TOTAL_FORMS': '1',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-board_game': str(self.game1.pk),
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Vote.objects.count(), 0)


@tag("integration")
class EventResultsViewTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_site_admin=True
        )
        self.user = User.objects.create_user(
            username='voter', password='testpass123'
        )
        self.group = Group.objects.create(name='Results Group')
        _make_organizer(self.admin, self.group)
        _make_member(self.user, self.group)
        self.event = Event.objects.create(
            title='Results Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.admin, group=self.group
        )
        EventAttendance.objects.create(user=self.user, event=self.event)
        self.game1 = BoardGame.objects.create(name='Catan', owner=self.admin)
        self.game2 = BoardGame.objects.create(name='Chess', owner=self.admin)

    def test_results_page_loads(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('event_results', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)

    def test_results_displays_scores(self):
        self.client.login(username='admin', password='testpass123')
        Vote.objects.create(user=self.user, event=self.event,
                            board_game=self.game1, rank=1)
        Vote.objects.create(user=self.user, event=self.event,
                            board_game=self.game2, rank=2)
        response = self.client.get(reverse('event_results', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertContains(response, 'Catan')
        self.assertContains(response, 'Chess')

    def test_results_nonexistent_event_returns_404(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('event_results', kwargs={'slug': self.group.slug, 'pk': 9999}))
        self.assertEqual(response.status_code, 404)


@tag("integration")
class VotePageNoGamesTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_site_admin=True
        )
        self.attendee = User.objects.create_user(
            username='attendee', password='testpass123'
        )
        self.group = Group.objects.create(name='No Games Group')
        _make_organizer(self.admin, self.group)
        _make_member(self.attendee, self.group)
        self.event = Event.objects.create(
            title='No Games Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.admin, group=self.group
        )
        EventAttendance.objects.create(user=self.attendee, event=self.event)

    def test_vote_page_shows_no_games_message_when_zero_games(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(
            reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No games available to vote on')
        self.assertNotContains(response, 'add-row-btn')

    def test_vote_page_shows_add_game_link_when_zero_games(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(
            reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.assertContains(response, reverse('game_add'))
        self.assertContains(response, 'Add Game')

    def test_vote_page_shows_back_link_when_zero_games(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(
            reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.assertContains(
            response,
            reverse('event_detail', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )

    def test_vote_page_shows_voting_form_when_games_exist(self):
        BoardGame.objects.create(name='Catan', owner=self.admin)
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(
            reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'No games available to vote on')
        self.assertContains(response, 'add-row-btn')


@tag("integration")
class VoteVisibilityToggleTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_site_admin=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )
        self.group = Group.objects.create(name='Toggle Group')
        _make_organizer(self.admin, self.group)
        self.event = Event.objects.create(
            title='Toggle Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.admin, group=self.group
        )

    def test_toggle_requires_admin(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_visibility', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_toggle_requires_login(self):
        response = self.client.post(
            reverse('event_toggle_visibility', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_admin_can_toggle_visibility(self):
        self.client.login(username='admin', password='testpass123')
        self.assertFalse(self.event.show_individual_votes)
        response = self.client.post(
            reverse('event_toggle_visibility', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('event_detail', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.event.refresh_from_db()
        self.assertTrue(self.event.show_individual_votes)

    def test_toggle_back_to_hidden(self):
        self.event.show_individual_votes = True
        self.event.save()
        self.client.login(username='admin', password='testpass123')
        self.client.post(
            reverse('event_toggle_visibility', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.event.refresh_from_db()
        self.assertFalse(self.event.show_individual_votes)

    def test_results_show_individual_votes_when_enabled(self):
        self.client.login(username='admin', password='testpass123')
        self.event.show_individual_votes = True
        self.event.save()
        EventAttendance.objects.create(user=self.regular, event=self.event)
        game = BoardGame.objects.create(name='Catan', owner=self.admin)
        Vote.objects.create(user=self.regular, event=self.event,
                            board_game=game, rank=1)
        response = self.client.get(reverse('event_results', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertContains(response, 'regular')

    def test_results_hide_individual_votes_when_disabled(self):
        self.client.login(username='admin', password='testpass123')
        self.assertFalse(self.event.show_individual_votes)
        EventAttendance.objects.create(user=self.regular, event=self.event)
        game = BoardGame.objects.create(name='Catan', owner=self.admin)
        Vote.objects.create(user=self.regular, event=self.event,
                            board_game=game, rank=1)
        response = self.client.get(reverse('event_results', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertNotContains(response, 'regular')


@tag("integration")
class ToggleVotingViewTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_site_admin=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )
        self.site_admin_only = User.objects.create_user(
            username='siteadminonly', password='testpass123',
            is_site_admin=True,
        )
        self.group = Group.objects.create(name='Toggle View Group')
        _make_organizer(self.organizer, self.group)
        _make_organizer(self.site_admin_only, self.group)
        self.event = Event.objects.create(
            title='Toggle Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
            is_active=True,
            voting_open=True,
            voting_deadline=timezone.now() + timedelta(days=7),
        )

    def test_organizer_can_end_voting(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_voting', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertFalse(self.event.voting_open)

    def test_organizer_can_resume_voting(self):
        self.event.voting_open = False
        self.event.save()
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_voting', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertTrue(self.event.voting_open)

    def test_regular_user_cannot_toggle_voting(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_voting', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_toggle_voting_requires_login(self):
        response = self.client.post(
            reverse('event_toggle_voting', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_cannot_resume_voting_after_deadline(self):
        self.event.voting_open = False
        self.event.voting_deadline = timezone.now() - timedelta(hours=1)
        self.event.save()
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_voting', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.event.refresh_from_db()
        self.assertFalse(self.event.voting_open)

    def test_cannot_resume_voting_when_event_inactive(self):
        self.event.voting_open = False
        self.event.is_active = False
        self.event.save()
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_voting', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.event.refresh_from_db()
        self.assertFalse(self.event.voting_open)

    def test_toggle_redirects_to_event_detail(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_voting', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.assertRedirects(
            response,
            reverse('event_detail', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )

    def test_toggle_on_completed_event_noop(self):
        past_event = Event.objects.create(
            title='Past Event',
            date=timezone.now() - timedelta(days=1),
            created_by=self.organizer,
            group=self.group,
            is_active=True,
            voting_open=False,
            voting_deadline=timezone.now() - timedelta(days=1),
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_voting', kwargs={'slug': past_event.group.slug, 'pk': past_event.pk})
        )
        past_event.refresh_from_db()
        self.assertFalse(past_event.voting_open)

    def test_site_admin_who_is_organizer_can_toggle_voting(self):
        self.client.login(username='siteadminonly', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_voting', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertFalse(self.event.voting_open)


@tag("integration")
class VoteViewWhenVotingClosedTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_site_admin=True
        )
        self.attendee = User.objects.create_user(
            username='attendee', password='testpass123'
        )
        self.group = Group.objects.create(name='Closed Group')
        _make_organizer(self.organizer, self.group)
        _make_member(self.attendee, self.group)
        self.event = Event.objects.create(
            title='Closed Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
            is_active=True,
            voting_open=False,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        EventAttendance.objects.create(user=self.attendee, event=self.event)
        self.game1 = BoardGame.objects.create(name='Catan', owner=self.organizer)

    def test_vote_page_shows_readonly_when_voting_paused(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(
            reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Voting is currently paused')

    def test_vote_page_shows_existing_votes_readonly(self):
        Vote.objects.create(
            user=self.attendee, event=self.event,
            board_game=self.game1, rank=1
        )
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(
            reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Catan')

    def test_submit_vote_rejected_when_voting_paused(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(
            reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}),
            {
                'form-TOTAL_FORMS': '1',
                'form-INITIAL_FORMS': '0',
                'form-MIN_NUM_FORMS': '0',
                'form-MAX_NUM_FORMS': '1000',
                'form-0-board_game': str(self.game1.pk),
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event
        ).exists())

    def test_existing_votes_preserved_when_submission_rejected(self):
        Vote.objects.create(
            user=self.attendee, event=self.event,
            board_game=self.game1, rank=1
        )
        self.client.login(username='attendee', password='testpass123')
        self.client.post(
            reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}),
            {
                'form-TOTAL_FORMS': '0',
                'form-INITIAL_FORMS': '0',
                'form-MIN_NUM_FORMS': '0',
                'form-MAX_NUM_FORMS': '1000',
            }
        )
        self.assertTrue(Vote.objects.filter(
            user=self.attendee, event=self.event, board_game=self.game1
        ).exists())

    def test_vote_page_shows_closed_message_for_past_event(self):
        past_event = Event.objects.create(
            title='Past Event',
            date=timezone.now() - timedelta(days=1),
            created_by=self.organizer,
            group=self.group,
            is_active=True,
            voting_open=True,
            voting_deadline=timezone.now() - timedelta(days=1),
        )
        EventAttendance.objects.create(user=self.attendee, event=past_event)
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(
            reverse('event_vote', kwargs={'slug': past_event.group.slug, 'pk': past_event.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Voting is currently closed')

    def test_mid_submit_rejection_preserves_existing_votes(self):
        Vote.objects.create(
            user=self.attendee, event=self.event,
            board_game=self.game1, rank=1
        )
        self.client.login(username='attendee', password='testpass123')
        self.client.get(reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))

        self.event.voting_open = True
        self.event.save()

        self.event.voting_open = False
        self.event.save()

        self.client.post(
            reverse('event_vote', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}),
            {
                'form-TOTAL_FORMS': '1',
                'form-INITIAL_FORMS': '0',
                'form-MIN_NUM_FORMS': '0',
                'form-MAX_NUM_FORMS': '1000',
                'form-0-board_game': str(self.game1.pk),
            }
        )
        self.assertTrue(Vote.objects.filter(
            user=self.attendee, event=self.event, board_game=self.game1, rank=1
        ).exists())


@tag("integration")
class EventDetailVotingStatusTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_site_admin=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )
        self.group = Group.objects.create(name='Status Group')
        _make_organizer(self.organizer, self.group)
        _make_member(self.regular, self.group)

    def test_organizer_sees_end_voting_button(self):
        event = Event.objects.create(
            title='Open Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
            is_active=True,
            voting_open=True,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk})
        )
        self.assertContains(response, 'End Voting')

    def test_organizer_sees_resume_voting_button(self):
        event = Event.objects.create(
            title='Paused Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
            is_active=True,
            voting_open=False,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk})
        )
        self.assertContains(response, 'Resume Voting')

    def test_regular_user_does_not_see_voting_buttons(self):
        event = Event.objects.create(
            title='Open Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
            is_active=True,
            voting_open=True,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(
            reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk})
        )
        self.assertNotContains(response, 'End Voting')
        self.assertNotContains(response, 'Resume Voting')

    def test_vote_link_hidden_when_voting_closed(self):
        event = Event.objects.create(
            title='Paused Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
            is_active=True,
            voting_open=False,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        EventAttendance.objects.create(user=self.regular, event=event)
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(
            reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk})
        )
        self.assertNotContains(response, 'Vote for Games')

    def test_voting_status_badge_shows_open(self):
        event = Event.objects.create(
            title='Open Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
            is_active=True,
            voting_open=True,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(
            reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk})
        )
        self.assertContains(response, 'Voting Open')

    def test_voting_status_badge_shows_paused(self):
        event = Event.objects.create(
            title='Paused Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
            is_active=True,
            voting_open=False,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(
            reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk})
        )
        self.assertContains(response, 'Voting Paused')

    def test_voting_status_badge_shows_closed(self):
        event = Event.objects.create(
            title='Past Event',
            date=timezone.now() - timedelta(days=1),
            created_by=self.organizer,
            group=self.group,
            is_active=True,
            voting_open=True,
            voting_deadline=timezone.now() - timedelta(days=1),
        )
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(
            reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk})
        )
        self.assertContains(response, 'Voting Closed')


@tag("integration")
class VotingDeadlineValidationTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_site_admin=True
        )
        self.group = Group.objects.create(name='Deadline Group')
        _make_organizer(self.organizer, self.group)

    def test_create_event_sets_voting_deadline_to_event_date(self):
        event_date = timezone.now() + timedelta(days=7)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Deadline Test',
            'date': event_date.strftime('%Y-%m-%d'),
            'time': event_date.strftime('%H:%M'),
        })
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title='Deadline Test')
        self.assertEqual(event.voting_deadline.date(), event.date.date())
        self.assertEqual(event.voting_deadline.hour, event.date.hour)
        self.assertEqual(event.voting_deadline.minute, event.date.minute)

    def test_can_set_custom_voting_deadline_before_event(self):
        event_date = timezone.now() + timedelta(days=7)
        deadline = timezone.now() + timedelta(days=5)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Custom Deadline',
            'date': event_date.strftime('%Y-%m-%d'),
            'time': event_date.strftime('%H:%M'),
            'voting_deadline_date': deadline.strftime('%Y-%m-%d'),
            'voting_deadline_time': deadline.strftime('%H:%M'),
        })
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title='Custom Deadline')
        self.assertEqual(event.voting_deadline.date(), deadline.date())

    def test_deadline_after_event_date_rejected(self):
        event_date = timezone.now() + timedelta(days=7)
        deadline = timezone.now() + timedelta(days=10)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Bad Deadline',
            'date': event_date.strftime('%Y-%m-%d'),
            'time': event_date.strftime('%H:%M'),
            'voting_deadline_date': deadline.strftime('%Y-%m-%d'),
            'voting_deadline_time': deadline.strftime('%H:%M'),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Bad Deadline').exists())

    def test_deadline_before_current_time_rejected(self):
        event_date = timezone.now() + timedelta(days=7)
        deadline = timezone.now() - timedelta(hours=1)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Past Deadline',
            'date': event_date.strftime('%Y-%m-%d'),
            'time': event_date.strftime('%H:%M'),
            'voting_deadline_date': deadline.strftime('%Y-%m-%d'),
            'voting_deadline_time': deadline.strftime('%H:%M'),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Past Deadline').exists())

    def test_edit_preserves_gap_when_event_date_changes(self):
        event_date = timezone.now() + timedelta(days=7, hours=19)
        event = Event.objects.create(
            title='Gap Event',
            date=event_date,
            created_by=self.organizer,
            group=self.group,
            voting_deadline=event_date - timedelta(hours=2),
            voting_deadline_offset_minutes=120,
        )
        new_date = timezone.now() + timedelta(days=14, hours=19)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_edit', kwargs={'slug': event.group.slug, 'pk': event.pk}),
            {
                'title': 'Gap Event',
                'date': new_date.strftime('%Y-%m-%d'),
                'time': new_date.strftime('%H:%M'),
                'location': '',
                'description': '',
                'voting_deadline_offset_minutes': '120',
            }
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        gap = event.date - event.voting_deadline
        self.assertEqual(gap, timedelta(hours=2))

    def test_edit_no_warning_when_deadline_equals_event_date(self):
        event_date = timezone.now() + timedelta(days=7, hours=19)
        event = Event.objects.create(
            title='Same Date Event',
            date=event_date,
            created_by=self.organizer,
            group=self.group,
            voting_deadline=event_date,
        )
        new_date = timezone.now() + timedelta(days=14, hours=19)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_edit', kwargs={'slug': event.group.slug, 'pk': event.pk}),
            {
                'title': 'Same Date Event',
                'date': new_date.strftime('%Y-%m-%d'),
                'time': new_date.strftime('%H:%M'),
                'location': '',
                'description': '',
            }
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.voting_deadline.date(), new_date.date())
        self.assertEqual(event.voting_deadline.hour, new_date.hour)

    def test_edit_warning_when_deadline_auto_adjusted(self):
        event_date = timezone.now() + timedelta(days=7, hours=19)
        event = Event.objects.create(
            title='Warn Event',
            date=event_date,
            created_by=self.organizer,
            group=self.group,
            voting_deadline=event_date - timedelta(hours=2),
            voting_deadline_offset_minutes=120,
        )
        new_date = timezone.now() + timedelta(days=14, hours=20)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_edit', kwargs={'slug': event.group.slug, 'pk': event.pk}),
            {
                'title': 'Warn Event',
                'date': new_date.strftime('%Y-%m-%d'),
                'time': new_date.strftime('%H:%M'),
                'location': '',
                'description': '',
                'voting_deadline_offset_minutes': '120',
            }
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        expected_deadline_minute = (new_date - timedelta(hours=2)).replace(second=0, microsecond=0)
        actual_deadline_minute = event.voting_deadline.replace(second=0, microsecond=0)
        self.assertEqual(actual_deadline_minute, expected_deadline_minute)

    def test_edit_can_change_deadline_explicitly(self):
        event_date = timezone.now() + timedelta(days=7, hours=19)
        event = Event.objects.create(
            title='Change Deadline',
            date=event_date,
            created_by=self.organizer,
            group=self.group,
            voting_deadline=event_date,
        )
        new_deadline = timezone.now() + timedelta(days=5, hours=12)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_edit', kwargs={'slug': event.group.slug, 'pk': event.pk}),
            {
                'title': 'Change Deadline',
                'date': event_date.strftime('%Y-%m-%d'),
                'time': event_date.strftime('%H:%M'),
                'location': '',
                'description': '',
                'voting_deadline_date': new_deadline.strftime('%Y-%m-%d'),
                'voting_deadline_time': new_deadline.strftime('%H:%M'),
            }
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.voting_deadline.date(), new_deadline.date())

    def test_deadline_field_prepopulated_on_edit(self):
        event_date = timezone.now() + timedelta(days=7, hours=19)
        deadline = timezone.now() + timedelta(days=5, hours=12)
        event = Event.objects.create(
            title='Prepopulate',
            date=event_date,
            created_by=self.organizer,
            group=self.group,
            voting_deadline=deadline,
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_edit', kwargs={'slug': event.group.slug, 'pk': event.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="date"')


@tag("integration")
class VotingToggleNotificationTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_site_admin=True
        )
        self.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        self.group = Group.objects.create(name='Notif Group')
        _make_organizer(self.organizer, self.group)
        _make_member(self.member, self.group)
        self.event = Event.objects.create(
            title='Toggle Notif Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
            is_active=True,
            voting_open=True,
            voting_deadline=timezone.now() + timedelta(days=7),
        )

    def test_end_voting_sends_notification(self):
        self.client.login(username='organizer', password='testpass123')
        self.client.post(reverse('event_toggle_voting', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertTrue(Notification.objects.filter(
            user=self.member,
            notification_type='group_voting_ended',
        ).exists())

    def test_resume_voting_sends_notification(self):
        self.event.voting_open = False
        self.event.save()
        self.client.login(username='organizer', password='testpass123')
        self.client.post(reverse('event_toggle_voting', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertTrue(Notification.objects.filter(
            user=self.member,
            notification_type='group_voting_resumed',
        ).exists())


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


@tag("integration")
class GroupEventResultsGatingTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        self.group_org = User.objects.create_user(
            username='group_org', password='testpass123'
        )
        self.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        self.outsider = User.objects.create_user(
            username='outsider', password='testpass123'
        )
        self.group = Group.objects.create(name='Results Gate Group')
        _make_organizer(self.organizer, self.group)
        _make_group_organizer(self.group_org, self.group)
        _make_member(self.member, self.group)
        self.event = Event.objects.create(
            title='Gated Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.organizer, group=self.group
        )
        EventAttendance.objects.create(user=self.member, event=self.event)
        self.game = BoardGame.objects.create(name='Catan', owner=self.organizer)
        Vote.objects.create(
            user=self.member, event=self.event, board_game=self.game, rank=1
        )

    def test_organizer_can_view_results(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk
            })
        )
        self.assertEqual(response.status_code, 200)

    def test_group_organizer_can_view_results(self):
        self.client.login(username='group_org', password='testpass123')
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk
            })
        )
        self.assertEqual(response.status_code, 200)

    def test_regular_member_cannot_view_results(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk
            })
        )
        self.assertEqual(response.status_code, 403)

    def test_outsider_cannot_view_results(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk
            })
        )
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_cannot_view_results(self):
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk
            })
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_site_admin_can_view_results(self):
        site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True
        )
        _make_member(site_admin, self.group)
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk
            })
        )
        self.assertEqual(response.status_code, 200)


@tag("integration")
class PrivateEventResultsGatingTest(TestCase):

    def setUp(self):
        self.creator = User.objects.create_user(
            username='creator', password='testpass123'
        )
        self.attendee = User.objects.create_user(
            username='attendee', password='testpass123'
        )
        self.other_user = User.objects.create_user(
            username='other', password='testpass123'
        )
        self.event = Event.objects.create(
            title='Private Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.creator,
            privacy='public',
        )
        EventAttendance.objects.create(user=self.attendee, event=self.event)
        self.game = BoardGame.objects.create(name='Wingspan', owner=self.creator)
        Vote.objects.create(
            user=self.attendee, event=self.event, board_game=self.game, rank=1
        )

    def test_creator_can_view_results(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.get(
            reverse('private_event_results', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_attendee_cannot_view_results(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(
            reverse('private_event_results', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_other_user_cannot_view_results(self):
        self.client.login(username='other', password='testpass123')
        response = self.client.get(
            reverse('private_event_results', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_cannot_view_results(self):
        response = self.client.get(
            reverse('private_event_results', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_additional_organizer_can_view_results(self):
        add_org = User.objects.create_user(
            username='addorg', password='testpass123'
        )
        EventAttendance.objects.create(user=add_org, event=self.event)
        self.event.additional_organizers.add(add_org)
        self.client.login(username='addorg', password='testpass123')
        response = self.client.get(
            reverse('private_event_results', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_group_event_redirects_from_private_url(self):
        group = Group.objects.create(name='Redirect Group')
        GroupMembership.objects.create(
            user=self.creator, group=group, role='admin'
        )
        group_event = Event.objects.create(
            title='Group Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.creator, group=group,
        )
        self.client.login(username='creator', password='testpass123')
        response = self.client.get(
            reverse('private_event_results', kwargs={'pk': group_event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse('event_results', kwargs={
                'slug': group.slug, 'pk': group_event.pk
            })
        )


@tag("integration")
class EventResultsTemplateTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        self.member = User.objects.create_user(
            username='member', password='testpass123'
        )

    def test_group_event_results_back_link_uses_group_url(self):
        group = Group.objects.create(name='Template Group')
        _make_organizer(self.organizer, group)
        event = Event.objects.create(
            title='Template Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.organizer, group=group,
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': group.slug, 'pk': event.pk
            })
        )
        self.assertContains(
            response,
            reverse('event_detail', kwargs={
                'slug': group.slug, 'pk': event.pk
            })
        )

    def test_private_event_results_back_link_uses_private_url(self):
        event = Event.objects.create(
            title='Private Template Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.organizer,
            privacy='public',
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('private_event_results', kwargs={'pk': event.pk})
        )
        self.assertContains(
            response,
            reverse('private_event_detail', kwargs={'pk': event.pk})
        )

    def test_group_event_detail_hides_results_link_from_member(self):
        group = Group.objects.create(name='Hide Results Group')
        _make_organizer(self.organizer, group)
        _make_member(self.member, group)
        event = Event.objects.create(
            title='Hide Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.organizer, group=group,
        )
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('event_detail', kwargs={
                'slug': group.slug, 'pk': event.pk
            })
        )
        self.assertNotContains(response, 'View Results')

    def test_group_event_detail_shows_results_link_to_organizer(self):
        group = Group.objects.create(name='Show Results Group')
        _make_organizer(self.organizer, group)
        event = Event.objects.create(
            title='Show Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.organizer, group=group,
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_detail', kwargs={
                'slug': group.slug, 'pk': event.pk
            })
        )
        self.assertContains(response, 'View Results')

    def test_private_event_detail_hides_results_link_from_attendee(self):
        event = Event.objects.create(
            title='Private Hide', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.organizer,
            privacy='public',
        )
        EventAttendance.objects.create(user=self.member, event=event)
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('private_event_detail', kwargs={'pk': event.pk})
        )
        self.assertNotContains(response, 'Results')

    def test_private_event_detail_shows_results_link_to_creator(self):
        event = Event.objects.create(
            title='Private Show', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.organizer,
            privacy='public',
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('private_event_detail', kwargs={'pk': event.pk})
        )
        self.assertContains(response, 'Results')


@tag("integration")
class EventVoteBackLinkTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        self.attendee = User.objects.create_user(
            username='attendee', password='testpass123'
        )

    def test_group_event_vote_back_link_uses_group_url(self):
        group = Group.objects.create(name='Vote Link Group')
        _make_organizer(self.organizer, group)
        _make_member(self.attendee, group)
        event = Event.objects.create(
            title='Vote Link Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.organizer, group=group,
        )
        EventAttendance.objects.create(user=self.attendee, event=event)
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(
            reverse('event_vote', kwargs={
                'slug': group.slug, 'pk': event.pk
            })
        )
        self.assertContains(
            response,
            reverse('event_detail', kwargs={
                'slug': group.slug, 'pk': event.pk
            })
        )

    def test_private_event_vote_back_link_uses_private_url(self):
        event = Event.objects.create(
            title='Private Vote Link', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.organizer,
            privacy='public',
        )
        EventAttendance.objects.create(user=self.attendee, event=event)
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(
            reverse('private_event_vote', kwargs={'pk': event.pk})
        )
        self.assertContains(
            response,
            reverse('private_event_detail', kwargs={'pk': event.pk})
        )


@tag("integration")
class RandomSelectTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        self.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        self.group = Group.objects.create(name='Random Group')
        _make_organizer(self.organizer, self.group)
        _make_member(self.member, self.group)
        self.event = Event.objects.create(
            title='Random Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.member, event=self.event)

    def test_random_select_from_pool(self):
        EventPresence.objects.create(
            event=self.event, user=self.member, marked_by=self.organizer
        )
        game1 = BoardGame.objects.create(name='Catan', owner=self.member, bgg_id=13)
        game2 = BoardGame.objects.create(name='Wingspan', owner=self.member, bgg_id=300)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(data['name'], ['Catan', 'Wingspan'])

    def test_random_select_deduplicated(self):
        EventPresence.objects.create(
            event=self.event, user=self.member, marked_by=self.organizer
        )
        BoardGame.objects.create(name='Catan', owner=self.organizer, bgg_id=13)
        BoardGame.objects.create(name='Catan', owner=self.member, bgg_id=13)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['name'], 'Catan')

    def test_random_select_empty_pool(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('error', data)

    def test_random_select_single_game(self):
        EventPresence.objects.create(
            event=self.event, user=self.member, marked_by=self.organizer
        )
        BoardGame.objects.create(name='Only Game', owner=self.member, bgg_id=13)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['name'], 'Only Game')

    def test_random_select_requires_organizer(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.post(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_random_select_requires_login(self):
        response = self.client.post(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_random_select_get_not_allowed(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 405)

    def test_random_select_includes_owners(self):
        EventPresence.objects.create(
            event=self.event, user=self.member, marked_by=self.organizer
        )
        BoardGame.objects.create(name='Catan', owner=self.organizer, bgg_id=13)
        BoardGame.objects.create(name='Catan', owner=self.member, bgg_id=13)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        data = response.json()
        self.assertIn('organizer', data['owners'])
        self.assertIn('member', data['owners'])
