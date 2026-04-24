from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from club.models import BoardGame, Event, EventAttendance, Group, GroupMembership, Notification, Vote

User = get_user_model()


def _make_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_member(user, group):
    GroupMembership.objects.create(user=user, group=group, role='member')


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
            title='Future Event',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=event_date,
        )
        self.assertEqual(event.phase, 'upcoming')

    def test_phase_returns_completed_for_past_event(self):
        event_date = timezone.now() - timedelta(days=1)
        event = Event.objects.create(
            title='Past Event',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=event_date,
        )
        self.assertEqual(event.phase, 'completed')

    def test_is_currently_active_true_when_active_and_future(self):
        event = Event.objects.create(
            title='Active Future',
            date=timezone.now() + timedelta(days=7),
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        self.assertTrue(event.is_currently_active)

    def test_is_currently_active_false_when_inactive(self):
        event = Event.objects.create(
            title='Inactive Future',
            date=timezone.now() + timedelta(days=7),
            created_by=self.admin,
            group=self.group,
            is_active=False,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        self.assertFalse(event.is_currently_active)

    def test_is_currently_active_false_when_past(self):
        event = Event.objects.create(
            title='Active Past',
            date=timezone.now() - timedelta(days=1),
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_deadline=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(event.is_currently_active)

    def test_is_currently_active_false_when_inactive_and_past(self):
        event = Event.objects.create(
            title='Inactive Past',
            date=timezone.now() - timedelta(days=1),
            created_by=self.admin,
            group=self.group,
            is_active=False,
            voting_deadline=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(event.is_currently_active)

    def test_is_voting_open_true_when_all_conditions_met(self):
        event = Event.objects.create(
            title='Open Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_open=True,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        self.assertTrue(event.is_voting_open)

    def test_is_voting_open_false_when_is_active_false(self):
        event = Event.objects.create(
            title='Inactive Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.admin,
            group=self.group,
            is_active=False,
            voting_open=True,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        self.assertFalse(event.is_voting_open)

    def test_is_voting_open_false_when_voting_open_false(self):
        event = Event.objects.create(
            title='Paused Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_open=False,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        self.assertFalse(event.is_voting_open)

    def test_is_voting_open_false_when_past_voting_deadline(self):
        event = Event.objects.create(
            title='Deadline Passed',
            date=timezone.now() + timedelta(days=7),
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_open=True,
            voting_deadline=timezone.now() - timedelta(hours=1),
        )
        self.assertFalse(event.is_voting_open)

    def test_is_voting_open_true_when_before_voting_deadline(self):
        event = Event.objects.create(
            title='Before Deadline',
            date=timezone.now() + timedelta(days=7),
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_open=True,
            voting_deadline=timezone.now() + timedelta(hours=1),
        )
        self.assertTrue(event.is_voting_open)

    def test_is_voting_open_false_when_voting_open_false_and_past(self):
        event = Event.objects.create(
            title='Paused Past',
            date=timezone.now() - timedelta(days=1),
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_open=False,
            voting_deadline=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(event.is_voting_open)

    def test_voting_open_defaults_to_true(self):
        event_date = timezone.now() + timedelta(days=7)
        event = Event.objects.create(
            title='New Event',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=event_date,
        )
        self.assertTrue(event.voting_open)

    def test_voting_deadline_defaults_to_event_date(self):
        event_date = timezone.now() + timedelta(days=7)
        event = Event.objects.create(
            title='New Event',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=event_date,
        )
        self.assertEqual(event.voting_deadline, event.date)

    def test_sync_sets_voting_open_false_when_deadline_passed(self):
        event = Event.objects.create(
            title='Expired Deadline',
            date=timezone.now() + timedelta(days=7),
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_open=True,
            voting_deadline=timezone.now() - timedelta(hours=1),
        )
        event.sync_voting_status()
        event.refresh_from_db()
        self.assertFalse(event.voting_open)

    def test_sync_does_not_change_when_voting_still_open(self):
        event = Event.objects.create(
            title='Still Open',
            date=timezone.now() + timedelta(days=7),
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_open=True,
            voting_deadline=timezone.now() + timedelta(hours=1),
        )
        event.sync_voting_status()
        event.refresh_from_db()
        self.assertTrue(event.voting_open)

    def test_sync_does_not_change_when_already_false(self):
        event = Event.objects.create(
            title='Already Paused',
            date=timezone.now() + timedelta(days=7),
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_open=False,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        event.sync_voting_status()
        event.refresh_from_db()
        self.assertFalse(event.voting_open)

    def test_sync_sets_voting_open_false_when_event_inactive(self):
        event = Event.objects.create(
            title='Inactive',
            date=timezone.now() + timedelta(days=7),
            created_by=self.admin,
            group=self.group,
            is_active=False,
            voting_open=True,
            voting_deadline=timezone.now() + timedelta(days=7),
        )
        event.sync_voting_status()
        event.refresh_from_db()
        self.assertFalse(event.voting_open)


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
                'form-0-rank': '1',
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
                'form-0-rank': '2',
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
