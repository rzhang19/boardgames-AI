from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from club.models import BoardGame, Event, EventAttendance, Vote
from club.borda import calculate_borda_scores

User = get_user_model()


class VoteViewAccessTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_organizer=True
        )
        self.attendee = User.objects.create_user(
            username='attendee', password='testpass123'
        )
        self.non_attendee = User.objects.create_user(
            username='outsider', password='testpass123'
        )
        self.event = Event.objects.create(
            title='Vote Event', date='2026-05-01T18:00:00Z',
            created_by=self.admin
        )
        EventAttendance.objects.create(user=self.attendee, event=self.event)
        self.game1 = BoardGame.objects.create(name='Catan', owner=self.admin)
        self.game2 = BoardGame.objects.create(name='Chess', owner=self.admin)

    def test_vote_page_requires_login(self):
        response = self.client.get(reverse('event_vote', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_non_attendee_cannot_vote(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(reverse('event_vote', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 403)

    def test_attendee_can_access_vote_page(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(reverse('event_vote', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)


class VoteSubmissionTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_organizer=True
        )
        self.attendee = User.objects.create_user(
            username='attendee', password='testpass123'
        )
        self.event = Event.objects.create(
            title='Vote Event', date='2026-05-01T18:00:00Z',
            created_by=self.admin
        )
        EventAttendance.objects.create(user=self.attendee, event=self.event)
        self.game1 = BoardGame.objects.create(name='Catan', owner=self.admin)
        self.game2 = BoardGame.objects.create(name='Chess', owner=self.admin)

    def test_attendee_can_submit_votes(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(reverse('event_vote', kwargs={'pk': self.event.pk}), {
            'form-TOTAL_FORMS': '2',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-board_game': str(self.game1.pk),
            'form-0-rank': '1',
            'form-1-board_game': str(self.game2.pk),
            'form-1-rank': '2',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Vote.objects.filter(user=self.attendee, event=self.event).count(), 2)

    def test_submit_zero_votes_is_allowed(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(reverse('event_vote', kwargs={'pk': self.event.pk}), {
            'form-TOTAL_FORMS': '0',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Vote.objects.filter(user=self.attendee, event=self.event).count(), 0)

    def test_submit_votes_replaces_existing_votes(self):
        Vote.objects.create(user=self.attendee, event=self.event,
                            board_game=self.game1, rank=1)
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(reverse('event_vote', kwargs={'pk': self.event.pk}), {
            'form-TOTAL_FORMS': '1',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-board_game': str(self.game2.pk),
            'form-0-rank': '1',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Vote.objects.filter(
            user=self.attendee, event=self.event, board_game=self.game1
        ).exists())
        self.assertTrue(Vote.objects.filter(
            user=self.attendee, event=self.event, board_game=self.game2
        ).exists())

    def test_vote_redirects_to_event_detail(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(reverse('event_vote', kwargs={'pk': self.event.pk}), {
            'form-TOTAL_FORMS': '0',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
        })
        self.assertEqual(response.url, reverse('event_detail', kwargs={'pk': self.event.pk}))

    def test_non_attendee_cannot_submit_votes(self):
        non_attendee = User.objects.create_user(username='outsider', password='testpass123')
        self.client.login(username='outsider', password='testpass123')
        response = self.client.post(reverse('event_vote', kwargs={'pk': self.event.pk}), {
            'form-TOTAL_FORMS': '1',
            'form-INITIAL_FORMS': '0',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-board_game': str(self.game1.pk),
            'form-0-rank': '1',
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Vote.objects.count(), 0)


class BordaCountTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_organizer=True
        )
        self.event = Event.objects.create(
            title='Borda Event', date='2026-05-01T18:00:00Z',
            created_by=self.admin
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


class EventResultsViewTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_organizer=True
        )
        self.user = User.objects.create_user(
            username='voter', password='testpass123'
        )
        self.event = Event.objects.create(
            title='Results Event', date='2026-05-01T18:00:00Z',
            created_by=self.admin
        )
        EventAttendance.objects.create(user=self.user, event=self.event)
        self.game1 = BoardGame.objects.create(name='Catan', owner=self.admin)
        self.game2 = BoardGame.objects.create(name='Chess', owner=self.admin)

    def test_results_page_loads(self):
        response = self.client.get(reverse('event_results', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)

    def test_results_displays_scores(self):
        Vote.objects.create(user=self.user, event=self.event,
                            board_game=self.game1, rank=1)
        Vote.objects.create(user=self.user, event=self.event,
                            board_game=self.game2, rank=2)
        response = self.client.get(reverse('event_results', kwargs={'pk': self.event.pk}))
        self.assertContains(response, 'Catan')
        self.assertContains(response, 'Chess')

    def test_results_nonexistent_event_returns_404(self):
        response = self.client.get(reverse('event_results', kwargs={'pk': 9999}))
        self.assertEqual(response.status_code, 404)


class VoteVisibilityToggleTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_organizer=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )
        self.event = Event.objects.create(
            title='Toggle Event', date='2026-05-01T18:00:00Z',
            created_by=self.admin
        )

    def test_toggle_requires_admin(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_visibility', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_toggle_requires_login(self):
        response = self.client.post(
            reverse('event_toggle_visibility', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_admin_can_toggle_visibility(self):
        self.client.login(username='admin', password='testpass123')
        self.assertFalse(self.event.show_individual_votes)
        response = self.client.post(
            reverse('event_toggle_visibility', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertTrue(self.event.show_individual_votes)

    def test_toggle_back_to_hidden(self):
        self.event.show_individual_votes = True
        self.event.save()
        self.client.login(username='admin', password='testpass123')
        self.client.post(
            reverse('event_toggle_visibility', kwargs={'pk': self.event.pk})
        )
        self.event.refresh_from_db()
        self.assertFalse(self.event.show_individual_votes)

    def test_results_show_individual_votes_when_enabled(self):
        self.event.show_individual_votes = True
        self.event.save()
        EventAttendance.objects.create(user=self.regular, event=self.event)
        game = BoardGame.objects.create(name='Catan', owner=self.admin)
        Vote.objects.create(user=self.regular, event=self.event,
                            board_game=game, rank=1)
        response = self.client.get(reverse('event_results', kwargs={'pk': self.event.pk}))
        self.assertContains(response, 'regular')

    def test_results_hide_individual_votes_when_disabled(self):
        self.assertFalse(self.event.show_individual_votes)
        EventAttendance.objects.create(user=self.regular, event=self.event)
        game = BoardGame.objects.create(name='Catan', owner=self.admin)
        Vote.objects.create(user=self.regular, event=self.event,
                            board_game=game, rank=1)
        response = self.client.get(reverse('event_results', kwargs={'pk': self.event.pk}))
        self.assertNotContains(response, 'regular')

    def test_toggle_redirects_to_event_detail(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_visibility', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.url, reverse('event_detail', kwargs={'pk': self.event.pk}))
