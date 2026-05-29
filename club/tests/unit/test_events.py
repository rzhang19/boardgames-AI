from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from club.forms import EventSettingsForm, EventInviteForm, PrivateEventForm
from club.game_pool import compute_game_pool
from club.models import (
    BoardGame,
    Event,
    EventAttendance,
    EventGameOverride,
    EventInvite,
    EventPresence,
    EventTag,
    Friendship,
    GameSession,
    GameTag,
    Group,
    GroupMembership,
    Notification,
    PrivateEventCreationLog,
    SiteSettings,
)
from club.notifications import (
    notify_event_invite_sent,
    notify_event_invite_accepted,
    notify_event_invite_declined,
    notify_event_organizer_designated,
)
from club.presence import is_presence_locked

User = get_user_model()


def _make_admin(user, group):
    GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='organizer')


def _make_member(user, group):
    GroupMembership.objects.create(user=user, group=group, role='member')


def _create_users(*usernames, password='testpass123'):
    return [User.objects.create_user(username=u, password=password) for u in usernames]


def _create_group(creator, name='Test Group'):
    group = Group.objects.create(name=name, created_by=creator)
    GroupMembership.objects.create(user=creator, group=group, role='admin')
    return group


# ---------------------------------------------------------------------------
# From test_event_duration.py
# ---------------------------------------------------------------------------

@tag("unit")
class EventDurationModelTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_site_admin=True
        )
        self.group = Group.objects.create(name='Duration Group')

    def test_end_time_auto_computed_on_create(self):
        event_date = timezone.now() + timedelta(hours=2)
        event = Event.objects.create(
            title='Timed Event',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        expected_end = event_date + timedelta(minutes=120)
        self.assertEqual(event.end_time, expected_end)

    def test_end_time_defaults_to_120_minutes(self):
        event_date = timezone.now() + timedelta(hours=2)
        event = Event.objects.create(
            title='Default Duration',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=event_date,
        )
        expected_end = event_date + timedelta(minutes=120)
        self.assertEqual(event.end_time, expected_end)

    def test_end_time_recomputed_when_date_changes(self):
        event_date = timezone.now() + timedelta(hours=2)
        event = Event.objects.create(
            title='Date Change',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=event_date,
            duration_minutes=90,
        )
        new_date = event_date + timedelta(days=1)
        event.date = new_date
        event.save()
        event.refresh_from_db()
        expected_end = new_date + timedelta(minutes=90)
        self.assertEqual(event.end_time, expected_end)

    def test_end_time_recomputed_when_duration_changes(self):
        event_date = timezone.now() + timedelta(hours=2)
        event = Event.objects.create(
            title='Duration Change',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=event_date,
            duration_minutes=60,
        )
        event.duration_minutes = 180
        event.save()
        event.refresh_from_db()
        expected_end = event_date + timedelta(minutes=180)
        self.assertEqual(event.end_time, expected_end)

    def test_phase_returns_upcoming_for_future_event(self):
        event = Event.objects.create(
            title='Future',
            date=timezone.now() + timedelta(days=1),
            created_by=self.admin,
            group=self.group,
            voting_deadline=timezone.now() + timedelta(days=1),
            duration_minutes=120,
        )
        self.assertEqual(event.phase, 'upcoming')

    def test_phase_returns_ongoing_when_within_duration(self):
        event_date = timezone.now() - timedelta(minutes=30)
        event = Event.objects.create(
            title='Ongoing',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        self.assertEqual(event.phase, 'ongoing')

    def test_phase_returns_completed_when_past_end_time(self):
        event_date = timezone.now() - timedelta(hours=3)
        event = Event.objects.create(
            title='Completed',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        self.assertEqual(event.phase, 'completed')

    def test_is_currently_active_true_before_event_starts(self):
        event = Event.objects.create(
            title='Future Active',
            date=timezone.now() + timedelta(days=1),
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_deadline=timezone.now() + timedelta(days=1),
            duration_minutes=120,
        )
        self.assertTrue(event.is_currently_active)

    def test_is_currently_active_true_during_ongoing(self):
        event_date = timezone.now() - timedelta(minutes=30)
        event = Event.objects.create(
            title='Mid Event',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        self.assertTrue(event.is_currently_active)

    def test_is_currently_active_false_when_past_end_time(self):
        event_date = timezone.now() - timedelta(hours=3)
        event = Event.objects.create(
            title='Past End',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        self.assertFalse(event.is_currently_active)

    def test_is_currently_active_false_when_is_active_false(self):
        event = Event.objects.create(
            title='Inactive',
            date=timezone.now() + timedelta(days=1),
            created_by=self.admin,
            group=self.group,
            is_active=False,
            voting_deadline=timezone.now() + timedelta(days=1),
            duration_minutes=120,
        )
        self.assertFalse(event.is_currently_active)

    def test_is_ongoing_true_when_within_duration(self):
        event_date = timezone.now() - timedelta(minutes=30)
        event = Event.objects.create(
            title='In Progress',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        self.assertTrue(event.is_ongoing)

    def test_is_ongoing_false_before_event_starts(self):
        event = Event.objects.create(
            title='Not Started',
            date=timezone.now() + timedelta(days=1),
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_deadline=timezone.now() + timedelta(days=1),
            duration_minutes=120,
        )
        self.assertFalse(event.is_ongoing)

    def test_is_ongoing_false_after_event_ends(self):
        event_date = timezone.now() - timedelta(hours=3)
        event = Event.objects.create(
            title='Ended',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        self.assertFalse(event.is_ongoing)

    def test_is_ongoing_false_when_ended_early(self):
        event_date = timezone.now() - timedelta(minutes=30)
        event = Event.objects.create(
            title='Ended Early',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        event.ended_early_at = timezone.now() - timedelta(minutes=15)
        event.end_time = event.ended_early_at
        event.save()
        self.assertFalse(event.is_ongoing)

    def test_time_remaining_seconds_positive_when_ongoing(self):
        event_date = timezone.now() - timedelta(minutes=30)
        event = Event.objects.create(
            title='Remaining',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_deadline=event_date,
            duration_minutes=60,
        )
        remaining = event.time_remaining_seconds
        self.assertGreater(remaining, 0)
        self.assertLessEqual(remaining, 1800)

    def test_time_remaining_seconds_zero_when_completed(self):
        event_date = timezone.now() - timedelta(hours=3)
        event = Event.objects.create(
            title='Done',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            is_active=True,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        self.assertEqual(event.time_remaining_seconds, 0)

    def test_ended_early_at_is_none_by_default(self):
        event = Event.objects.create(
            title='No Early End',
            date=timezone.now() + timedelta(days=1),
            created_by=self.admin,
            group=self.group,
            voting_deadline=timezone.now() + timedelta(days=1),
        )
        self.assertIsNone(event.ended_early_at)


@tag("unit")
class EventExtendViewTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123'
        )
        self.group = Group.objects.create(name='Extend Group')
        _make_admin(self.admin, self.group)
        event_date = timezone.now() - timedelta(minutes=30)
        self.event = Event.objects.create(
            title='Ongoing Event',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        self.url = reverse('event_extend', kwargs={'pk': self.event.pk})

    def test_extend_adds_minutes_to_ongoing_event(self):
        original_end = self.event.end_time
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(self.url, {'additional_minutes': 30})
        self.event.refresh_from_db()
        self.assertEqual(self.event.duration_minutes, 150)
        expected_end = original_end + timedelta(minutes=30)
        self.assertEqual(self.event.end_time, expected_end)

    def test_extend_fails_for_non_organizer(self):
        user = User.objects.create_user(username='stranger', password='pass')
        _make_member(user, self.group)
        self.client.login(username='stranger', password='pass')
        response = self.client.post(self.url, {'additional_minutes': 30})
        self.assertEqual(response.status_code, 403)
        self.event.refresh_from_db()
        self.assertEqual(self.event.duration_minutes, 120)

    def test_extend_fails_for_completed_event(self):
        past_event_date = timezone.now() - timedelta(hours=5)
        past_event = Event.objects.create(
            title='Past Event',
            date=past_event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=past_event_date,
            duration_minutes=120,
        )
        url = reverse('event_extend', kwargs={'pk': past_event.pk})
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(url, {'additional_minutes': 30})
        past_event.refresh_from_db()
        self.assertEqual(past_event.duration_minutes, 120)

    def test_extend_fails_for_unauthenticated(self):
        response = self.client.post(self.url, {'additional_minutes': 30})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_extend_redirects_to_event_detail(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(self.url, {'additional_minutes': 15})
        self.assertRedirects(
            response,
            reverse('event_detail', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk,
            }),
        )


@tag("unit")
class EventEndEarlyViewTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123'
        )
        self.group = Group.objects.create(name='End Group')
        _make_admin(self.admin, self.group)
        event_date = timezone.now() - timedelta(minutes=30)
        self.event = Event.objects.create(
            title='Ongoing Event',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        self.url = reverse('event_end_early', kwargs={'pk': self.event.pk})

    def test_end_early_sets_ended_early_at_and_end_time(self):
        before = timezone.now()
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(self.url)
        after = timezone.now()
        self.event.refresh_from_db()
        self.assertIsNotNone(self.event.ended_early_at)
        self.assertGreaterEqual(self.event.ended_early_at, before)
        self.assertLessEqual(self.event.ended_early_at, after)
        self.assertEqual(self.event.end_time, self.event.ended_early_at)

    def test_end_early_makes_event_not_active(self):
        self.client.login(username='admin', password='testpass123')
        self.client.post(self.url)
        self.event.refresh_from_db()
        self.assertFalse(self.event.is_currently_active)
        self.assertFalse(self.event.is_ongoing)

    def test_end_early_fails_for_non_organizer(self):
        user = User.objects.create_user(username='stranger', password='pass')
        _make_member(user, self.group)
        self.client.login(username='stranger', password='pass')
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.ended_early_at)

    def test_end_early_fails_for_already_ended_event(self):
        past_date = timezone.now() - timedelta(hours=5)
        past_event = Event.objects.create(
            title='Past',
            date=past_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=past_date,
            duration_minutes=120,
        )
        url = reverse('event_end_early', kwargs={'pk': past_event.pk})
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(url)
        past_event.refresh_from_db()
        self.assertIsNone(past_event.ended_early_at)

    def test_end_early_redirects_to_event_detail(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(self.url)
        self.assertRedirects(
            response,
            reverse('event_detail', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk,
            }),
        )


@tag("unit")
class EventTimerStatusViewTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123'
        )
        self.group = Group.objects.create(name='Timer Group')
        _make_admin(self.admin, self.group)
        event_date = timezone.now() - timedelta(minutes=30)
        self.event = Event.objects.create(
            title='Timer Event',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=event_date,
            duration_minutes=120,
        )

    def test_returns_json_with_end_time(self):
        self.client.login(username='admin', password='testpass123')
        url = reverse('event_timer_status', kwargs={'pk': self.event.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('end_time', data)
        self.assertIn('is_active', data)
        self.assertTrue(data['is_active'])

    def test_returns_ended_early_at_when_set(self):
        now = timezone.now()
        self.event.ended_early_at = now
        self.event.end_time = now
        self.event.save()
        self.client.login(username='admin', password='testpass123')
        url = reverse('event_timer_status', kwargs={'pk': self.event.pk})
        response = self.client.get(url)
        data = response.json()
        self.assertIsNotNone(data['ended_early_at'])

    def test_unauthenticated_user_redirected_to_login(self):
        url = reverse('event_timer_status', kwargs={'pk': self.event.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_non_member_denied_for_non_discoverable_group(self):
        self.group.discoverable = False
        self.group.save()
        outsider = User.objects.create_user(username='outsider', password='testpass123')
        self.client.login(username='outsider', password='testpass123')
        url = reverse('event_timer_status', kwargs={'pk': self.event.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_group_member_can_access(self):
        member = User.objects.create_user(username='member', password='testpass123')
        _make_member(member, self.group)
        self.client.login(username='member', password='testpass123')
        url = reverse('event_timer_status', kwargs={'pk': self.event.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


@tag("unit")
class EventTimerStatusPrivateEventTest(TestCase):

    def setUp(self):
        self.creator = User.objects.create_user(
            username='creator', password='testpass123'
        )
        event_date = timezone.now() - timedelta(minutes=30)
        self.event = Event.objects.create(
            title='Private Timer Event',
            date=event_date,
            created_by=self.creator,
            group=None,
            privacy='private',
            voting_deadline=event_date,
            duration_minutes=120,
        )

    def test_unauthenticated_user_redirected_to_login(self):
        url = reverse('event_timer_status', kwargs={'pk': self.event.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_unauthorized_user_denied_for_private_event(self):
        outsider = User.objects.create_user(username='outsider', password='testpass123')
        self.client.login(username='outsider', password='testpass123')
        url = reverse('event_timer_status', kwargs={'pk': self.event.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_creator_can_access_private_event(self):
        self.client.login(username='creator', password='testpass123')
        url = reverse('event_timer_status', kwargs={'pk': self.event.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_attendee_can_access_private_event(self):
        attendee = User.objects.create_user(username='attendee', password='testpass123')
        EventAttendance.objects.create(user=attendee, event=self.event)
        self.client.login(username='attendee', password='testpass123')
        url = reverse('event_timer_status', kwargs={'pk': self.event.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


@tag("unit")
class GameSessionGatingTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123'
        )
        self.group = Group.objects.create(name='Gate Group')
        _make_admin(self.admin, self.group)
        self.game = BoardGame.objects.create(name='Catan', owner=self.admin)

    def test_can_record_game_during_ongoing_event(self):
        event_date = timezone.now() - timedelta(minutes=30)
        event = Event.objects.create(
            title='Ongoing',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        self.client.login(username='admin', password='testpass123')
        url = reverse('event_play_game', kwargs={'pk': event.pk})
        response = self.client.post(url, {
            'board_game': self.game.pk,
            'selection_method': 'manual',
        })
        self.assertEqual(GameSession.objects.filter(event=event).count(), 1)

    def test_cannot_record_game_after_event_ends(self):
        event_date = timezone.now() - timedelta(hours=3)
        event = Event.objects.create(
            title='Ended',
            date=event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        self.client.login(username='admin', password='testpass123')
        url = reverse('event_play_game', kwargs={'pk': event.pk})
        response = self.client.post(url, {
            'board_game': self.game.pk,
            'selection_method': 'manual',
        })
        self.assertEqual(GameSession.objects.filter(event=event).count(), 0)


@tag("unit")
class PrivateEventExtendViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='host', password='testpass123', email_verified=True
        )
        event_date = timezone.now() - timedelta(minutes=30)
        self.event = Event.objects.create(
            title='Private Ongoing',
            date=event_date,
            created_by=self.user,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        PrivateEventCreationLog.objects.create(user=self.user, event=self.event)
        self.url = reverse('event_extend', kwargs={'pk': self.event.pk})

    def test_extend_private_event(self):
        original_end = self.event.end_time
        self.client.login(username='host', password='testpass123')
        response = self.client.post(self.url, {'additional_minutes': 30})
        self.event.refresh_from_db()
        self.assertEqual(self.event.duration_minutes, 150)

    def test_end_early_private_event(self):
        url = reverse('event_end_early', kwargs={'pk': self.event.pk})
        self.client.login(username='host', password='testpass123')
        response = self.client.post(url)
        self.event.refresh_from_db()
        self.assertIsNotNone(self.event.ended_early_at)


@tag("unit")
class GroupDefaultDurationTest(TestCase):

    def test_new_group_gets_site_default_duration(self):
        site = SiteSettings.load()
        site.default_event_duration_minutes = 90
        site.save()
        group = Group.objects.create(name='New Group')
        self.assertEqual(group.default_event_duration_minutes, 90)

    def test_changing_site_default_does_not_affect_existing_group(self):
        group = Group.objects.create(name='Existing Group')
        original = group.default_event_duration_minutes
        site = SiteSettings.load()
        site.default_event_duration_minutes = 999
        site.save()
        group.refresh_from_db()
        self.assertEqual(group.default_event_duration_minutes, original)

    def test_changing_group_default_does_not_affect_existing_events(self):
        group = Group.objects.create(name='G1')
        admin = User.objects.create_user(username='a', password='p')
        event_date = timezone.now() + timedelta(days=1)
        event = Event.objects.create(
            title='E1',
            date=event_date,
            created_by=admin,
            group=group,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        group.default_event_duration_minutes = 60
        group.save()
        event.refresh_from_db()
        self.assertEqual(event.duration_minutes, 120)


@tag("unit")
class SiteDefaultDurationTest(TestCase):

    def test_site_settings_has_default_duration(self):
        site = SiteSettings.load()
        self.assertEqual(site.default_event_duration_minutes, 120)

    def test_changing_site_default_does_not_affect_existing_events(self):
        admin = User.objects.create_user(username='a', password='p')
        group = Group.objects.create(name='G')
        event_date = timezone.now() + timedelta(days=1)
        event = Event.objects.create(
            title='E',
            date=event_date,
            created_by=admin,
            group=group,
            voting_deadline=event_date,
            duration_minutes=120,
        )
        site = SiteSettings.load()
        site.default_event_duration_minutes = 60
        site.save()
        event.refresh_from_db()
        self.assertEqual(event.duration_minutes, 120)


@tag("unit")
class RecurringEventDurationTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123'
        )
        self.group = Group.objects.create(name='Recur Dur Group')
        _make_admin(self.admin, self.group)

    def test_recurring_events_get_same_duration(self):
        start = timezone.now() + timedelta(days=1)
        self.client.login(username='admin', password='testpass123')
        session = self.client.session

        from django.test import Client
        client = Client()
        client.login(username='admin', password='testpass123')

        url = reverse('event_add_recurring_preview', kwargs={
            'slug': self.group.slug,
        })

        dates_data = [
            {
                'date': start.strftime('%Y-%m-%d'),
                'time': start.strftime('%H:%M'),
                'datetime': start.isoformat(),
                'checked': True,
            },
            {
                'date': (start + timedelta(days=7)).strftime('%Y-%m-%d'),
                'time': start.strftime('%H:%M'),
                'datetime': (start + timedelta(days=7)).isoformat(),
                'checked': True,
            },
        ]
        form_data = {
            'title': 'Recur Event',
            'description': '',
            'location': '',
            'time': start.strftime('%H:%M'),
            'voting_deadline_offset_minutes': 0,
            'voting_deadline_date': '',
            'voting_deadline_time': '',
            'duration_minutes': 90,
        }

        session = client.session
        session['recurring_event_form_data'] = form_data
        session['recurring_event_dates'] = dates_data
        session.save()

        response = client.post(url, {
            'selected_dates': ['0', '1'],
        })

        events = Event.objects.filter(title='Recur Event').order_by('date')
        self.assertEqual(events.count(), 2)
        for event in events:
            self.assertEqual(event.duration_minutes, 90)
            expected_end = event.date + timedelta(minutes=90)
            self.assertEqual(event.end_time, expected_end)


# ---------------------------------------------------------------------------
# From test_event_presence.py
# ---------------------------------------------------------------------------

FUTURE_DATE = timezone.now() + timedelta(days=30)


@tag("unit")
class EventPresenceModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='user', password='pass')
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.group = Group.objects.create(name='Presence Group')
        _make_admin(self.admin, self.group)
        self.event = Event.objects.create(
            title='Presence Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.admin,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.user, event=self.event)

    def test_create_presence(self):
        presence = EventPresence.objects.create(
            event=self.event, user=self.user, marked_by=self.admin
        )
        self.assertEqual(presence.event, self.event)
        self.assertEqual(presence.user, self.user)
        self.assertEqual(presence.marked_by, self.admin)
        self.assertIsNotNone(presence.marked_at)

    def test_unique_constraint(self):
        EventPresence.objects.create(
            event=self.event, user=self.user, marked_by=self.admin
        )
        with self.assertRaises(IntegrityError):
            EventPresence.objects.create(
                event=self.event, user=self.user, marked_by=self.admin
            )

    def test_string_representation(self):
        presence = EventPresence.objects.create(
            event=self.event, user=self.user, marked_by=self.admin
        )
        self.assertIn('user', str(presence))
        self.assertIn('Presence Event', str(presence))


@tag("unit")
class PresenceLockTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.group = Group.objects.create(name='Lock Group')
        _make_admin(self.admin, self.group)

    def test_not_locked_before_12h(self):
        event = Event.objects.create(
            title='Future Event',
            date=timezone.now() + timezone.timedelta(hours=24),
            voting_deadline=timezone.now() + timezone.timedelta(hours=24),
            created_by=self.admin,
            group=self.group,
        )
        locked, lock_time = is_presence_locked(event)
        self.assertFalse(locked)
        self.assertEqual(lock_time, event.date + timezone.timedelta(hours=12))

    def test_locked_after_12h(self):
        event = Event.objects.create(
            title='Past Event',
            date=timezone.now() - timezone.timedelta(hours=24),
            voting_deadline=timezone.now() - timezone.timedelta(hours=24),
            created_by=self.admin,
            group=self.group,
        )
        locked, lock_time = is_presence_locked(event)
        self.assertTrue(locked)

    def test_locked_exactly_at_12h(self):
        event = Event.objects.create(
            title='Exact Event',
            date=timezone.now() - timezone.timedelta(hours=12),
            voting_deadline=timezone.now() - timezone.timedelta(hours=12),
            created_by=self.admin,
            group=self.group,
        )
        locked, lock_time = is_presence_locked(event)
        self.assertTrue(locked)


# ---------------------------------------------------------------------------
# From test_private_events.py
# ---------------------------------------------------------------------------

@tag("unit")
class EventNullableGroupTest(TestCase):

    def test_event_can_be_created_without_group(self):
        user = _create_users('alice')[0]
        event = Event.objects.create(
            title='Private Game Night',
            date=timezone.now() + timedelta(days=7),
            created_by=user,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        self.assertIsNone(event.group)

    def test_event_can_still_have_group(self):
        alice = _create_users('alice')[0]
        group = _create_group(alice)
        event = Event.objects.create(
            title='Group Event',
            date=timezone.now() + timedelta(days=7),
            created_by=alice,
            group=group,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        self.assertEqual(event.group, group)

    def test_event_without_group_defaults(self):
        user = _create_users('alice')[0]
        event = Event.objects.create(
            title='Private Event',
            date=timezone.now() + timedelta(days=7),
            created_by=user,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        self.assertEqual(event.privacy, 'public')
        self.assertTrue(event.show_description_publicly)
        self.assertTrue(event.show_location_publicly)
        self.assertTrue(event.show_datetime_publicly)
        self.assertTrue(event.show_attendees_publicly)
        self.assertEqual(event.allow_invite_others, 'nobody')
        self.assertTrue(event.organizers_can_edit_title)
        self.assertTrue(event.organizers_can_edit_description)
        self.assertTrue(event.organizers_can_edit_datetime)


@tag("unit")
class EventPrivacyTest(TestCase):

    def test_privacy_choices_valid(self):
        user = _create_users('alice')[0]
        for privacy in ('private', 'invite_only_public', 'public'):
            event = Event.objects.create(
                title=f'Event {privacy}',
                date=timezone.now() + timedelta(days=7),
                created_by=user,
                voting_deadline=timezone.now() + timedelta(days=6),
                privacy=privacy,
            )
            self.assertEqual(event.privacy, privacy)

    def test_invalid_privacy_raises_error(self):
        user = _create_users('alice')[0]
        event = Event(
            title='Bad Event',
            date=timezone.now() + timedelta(days=7),
            created_by=user,
            voting_deadline=timezone.now() + timedelta(days=6),
            privacy='invalid',
        )
        with self.assertRaises(Exception):
            event.full_clean()


@tag("unit")
class EventOrganizerTest(TestCase):

    def test_creator_is_organizer(self):
        alice = _create_users('alice')[0]
        event = Event.objects.create(
            title='My Event',
            date=timezone.now() + timedelta(days=7),
            created_by=alice,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        self.assertTrue(event.is_organizer(alice))

    def test_additional_organizer_is_organizer(self):
        alice, bob = _create_users('alice', 'bob')
        event = Event.objects.create(
            title='Our Event',
            date=timezone.now() + timedelta(days=7),
            created_by=alice,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        event.additional_organizers.add(bob)
        self.assertTrue(event.is_organizer(bob))

    def test_non_organizer_is_not_organizer(self):
        alice, bob = _create_users('alice', 'bob')
        event = Event.objects.create(
            title='Alice Event',
            date=timezone.now() + timedelta(days=7),
            created_by=alice,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        self.assertFalse(event.is_organizer(bob))

    def test_unauthenticated_user_is_not_organizer(self):
        alice = _create_users('alice')[0]
        event = Event.objects.create(
            title='Event',
            date=timezone.now() + timedelta(days=7),
            created_by=alice,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(event.is_organizer(AnonymousUser()))


@tag("unit")
class EventInviteModelTest(TestCase):

    def setUp(self):
        self.alice, self.bob = _create_users('alice', 'bob')
        self.event = Event.objects.create(
            title='Private Night',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
            privacy='private',
        )

    def test_create_invite(self):
        invite = EventInvite.objects.create(
            event=self.event,
            user=self.bob,
            invited_by=self.alice,
        )
        self.assertEqual(invite.status, 'pending')
        self.assertEqual(str(invite), 'bob invited to Private Night (pending)')

    def test_unique_constraint_event_user(self):
        EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        with self.assertRaises(IntegrityError):
            EventInvite.objects.create(
                event=self.event, user=self.bob, invited_by=self.alice,
            )

    def test_accept_creates_attendance(self):
        invite = EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        invite.accept()
        invite.refresh_from_db()
        self.assertEqual(invite.status, 'accepted')
        self.assertTrue(
            EventAttendance.objects.filter(
                user=self.bob, event=self.event,
            ).exists()
        )

    def test_accept_already_accepted_is_idempotent(self):
        invite = EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        invite.accept()
        invite.accept()
        self.assertEqual(
            EventAttendance.objects.filter(
                user=self.bob, event=self.event,
            ).count(),
            1,
        )

    def test_decline_invite(self):
        invite = EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        invite.decline()
        invite.refresh_from_db()
        self.assertEqual(invite.status, 'declined')
        self.assertFalse(
            EventAttendance.objects.filter(
                user=self.bob, event=self.event,
            ).exists()
        )

    def test_decline_non_pending_raises(self):
        invite = EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
            status='declined',
        )
        with self.assertRaises(ValueError):
            invite.decline()

    def test_accept_declined_invite_raises(self):
        invite = EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
            status='declined',
        )
        with self.assertRaises(ValueError):
            invite.accept()

    def test_is_expired_for_past_event(self):
        event = Event.objects.create(
            title='Past Event',
            date=timezone.now() - timedelta(days=1),
            created_by=self.alice,
            voting_deadline=timezone.now() - timedelta(days=2),
        )
        invite = EventInvite.objects.create(
            event=event, user=self.bob, invited_by=self.alice,
        )
        self.assertTrue(invite.is_expired)

    def test_is_not_expired_for_future_event(self):
        invite = EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        self.assertFalse(invite.is_expired)

    def test_cascade_on_event_delete(self):
        EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        self.event.delete()
        self.assertEqual(EventInvite.objects.count(), 0)

    def test_cascade_on_user_delete(self):
        EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        self.bob.delete()
        self.assertEqual(EventInvite.objects.count(), 0)


@tag("unit")
class PrivateEventCreationLogTest(TestCase):

    def test_create_log(self):
        user = _create_users('alice')[0]
        event = Event.objects.create(
            title='My Event',
            date=timezone.now() + timedelta(days=7),
            created_by=user,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        log = PrivateEventCreationLog.objects.create(
            user=user, event=event,
        )
        self.assertEqual(log.user, user)
        self.assertEqual(log.event, event)
        self.assertIsNotNone(log.created_at)

    def test_can_query_rate_limit(self):
        user = _create_users('alice')[0]
        cutoff = timezone.now() - timedelta(hours=168)
        count = PrivateEventCreationLog.objects.filter(
            user=user, created_at__gte=cutoff,
        ).count()
        self.assertEqual(count, 0)

    def test_log_null_event(self):
        user = _create_users('alice')[0]
        log = PrivateEventCreationLog.objects.create(user=user)
        self.assertIsNone(log.event)

    def test_str_representation(self):
        user = _create_users('alice')[0]
        log = PrivateEventCreationLog.objects.create(user=user)
        self.assertIn('alice', str(log))


@tag("unit")
class PrivateEventFormTest(TestCase):

    def test_valid_form(self):
        future = (timezone.now() + timedelta(days=7)).date()
        form = PrivateEventForm(data={
            'title': 'Game Night',
            'description': 'Fun times',
            'location': 'My house',
            'date': future.strftime('%Y-%m-%d'),
            'privacy': 'public',
            'allow_invite_others': 'nobody',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_past_date_invalid(self):
        past = (timezone.now() - timedelta(days=1)).date()
        form = PrivateEventForm(data={
            'title': 'Past Event',
            'date': past.strftime('%Y-%m-%d'),
            'privacy': 'public',
            'allow_invite_others': 'nobody',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('date', form.errors)

    def test_privacy_defaults_to_public(self):
        future = (timezone.now() + timedelta(days=7)).date()
        form = PrivateEventForm(data={
            'title': 'Event',
            'date': future.strftime('%Y-%m-%d'),
            'privacy': 'public',
            'allow_invite_others': 'nobody',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['privacy'], 'public')

    def test_form_saves_without_group(self):
        user = _create_users('alice')[0]
        future = (timezone.now() + timedelta(days=7)).date()
        form = PrivateEventForm(data={
            'title': 'No Group Event',
            'date': future.strftime('%Y-%m-%d'),
            'privacy': 'private',
            'allow_invite_others': 'friends_only',
        })
        self.assertTrue(form.is_valid(), form.errors)
        event = form.save(commit=False)
        event.created_by = user
        event.date = form.cleaned_data['date']
        event.voting_deadline = event.date - timedelta(days=1)
        event.save()
        self.assertIsNone(event.group)
        self.assertEqual(event.privacy, 'private')


@tag("unit")
class EventSettingsFormTest(TestCase):

    def test_valid_settings_form(self):
        user = _create_users('alice')[0]
        event = Event.objects.create(
            title='Test',
            date=timezone.now() + timedelta(days=7),
            created_by=user,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        form = EventSettingsForm(data={
            'privacy': 'private',
            'show_description_publicly': False,
            'show_location_publicly': True,
            'show_datetime_publicly': True,
            'show_attendees_publicly': False,
            'allow_invite_others': 'friends_only',
            'organizers_can_edit_title': True,
            'organizers_can_edit_description': False,
            'organizers_can_edit_datetime': True,
        }, instance=event)
        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()
        self.assertEqual(updated.privacy, 'private')
        self.assertFalse(updated.show_description_publicly)


@tag("unit")
class EventInviteFormTest(TestCase):

    def test_valid_user_ids(self):
        alice, bob = _create_users('alice', 'bob')
        form = EventInviteForm(data={'user_ids': str(bob.pk)})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['user_ids'], [bob.pk])

    def test_multiple_user_ids(self):
        alice, bob, carol = _create_users('alice', 'bob', 'carol')
        form = EventInviteForm(data={'user_ids': f'{bob.pk},{carol.pk}'})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['user_ids'], [bob.pk, carol.pk])

    def test_empty_user_ids_invalid(self):
        form = EventInviteForm(data={'user_ids': ''})
        self.assertFalse(form.is_valid())


@tag("unit")
class EventInviteNotificationTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='testpass123')
        self.bob = User.objects.create_user(username='bob', password='testpass123')
        self.event = Event.objects.create(
            title='Game Night',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
            privacy='private',
        )

    def test_invite_sent_creates_notification(self):
        notify_event_invite_sent(self.bob, self.alice, self.event)
        notif = Notification.objects.get(
            user=self.bob, notification_type='event_invite',
        )
        self.assertIn('alice', notif.message)
        self.assertIn('Game Night', notif.message)
        self.assertIn(f'/events/{self.event.pk}/', notif.url)

    def test_invite_accepted_creates_notification(self):
        notify_event_invite_accepted(self.alice, self.bob, self.event)
        notif = Notification.objects.get(
            user=self.alice, notification_type='event_invite_accepted',
        )
        self.assertIn('bob', notif.message)
        self.assertIn('Game Night', notif.message)

    def test_invite_declined_creates_notification(self):
        notify_event_invite_declined(self.alice, self.bob, self.event)
        notif = Notification.objects.get(
            user=self.alice, notification_type='event_invite_declined',
        )
        self.assertIn('bob', notif.message)
        self.assertIn('Game Night', notif.message)

    def test_organizer_designated_creates_notification(self):
        notify_event_organizer_designated(self.bob, self.event)
        notif = Notification.objects.get(
            user=self.bob, notification_type='event_organizer_designated',
        )
        self.assertIn('Game Night', notif.message)
        self.assertIn(f'/events/{self.event.pk}/', notif.url)


@tag("unit")
class EventGamePoolTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='testpass123')
        self.bob = User.objects.create_user(username='bob', password='testpass123')
        self.carol = User.objects.create_user(username='carol', password='testpass123')
        self.event = Event.objects.create(
            title='Game Night',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
            privacy='private',
        )

    def test_includes_creator_games(self):
        BoardGame.objects.create(name='Catan', owner=self.alice)
        pool = self.event.get_game_pool()
        self.assertEqual(pool.count(), 1)
        self.assertEqual(pool.first().name, 'Catan')

    def test_includes_attendee_games(self):
        BoardGame.objects.create(name='Catan', owner=self.alice)
        BoardGame.objects.create(name='Ticket to Ride', owner=self.bob)
        EventAttendance.objects.create(user=self.bob, event=self.event)
        pool = self.event.get_game_pool()
        self.assertEqual(pool.count(), 2)

    def test_excludes_non_attendee_games(self):
        BoardGame.objects.create(name='Catan', owner=self.carol)
        pool = self.event.get_game_pool()
        self.assertEqual(pool.count(), 0)

    def test_no_duplicate_games(self):
        BoardGame.objects.create(name='Catan', owner=self.alice)
        BoardGame.objects.create(name='Catan', owner=self.bob)
        EventAttendance.objects.create(user=self.bob, event=self.event)
        pool = self.event.get_game_pool()
        self.assertEqual(pool.count(), 2)

    def test_group_event_delegates_to_group_games(self):
        group = Group.objects.create(name='Test Group', slug='test-group')
        group_event = Event.objects.create(
            title='Group Night',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
            group=group,
        )
        BoardGame.objects.create(name='Catan', owner=self.alice)
        GroupMembership.objects.create(
            user=self.alice, group=group, role='member',
        )
        pool = group_event.get_game_pool()
        self.assertEqual(pool.count(), 1)

    def test_auto_add_false_still_returns_pool(self):
        self.event.save()
        BoardGame.objects.create(name='Catan', owner=self.alice)
        pool = self.event.get_game_pool()
        self.assertEqual(pool.count(), 1)

    def test_includes_additional_organizer_games(self):
        self.event.additional_organizers.add(self.bob)
        BoardGame.objects.create(name='Wingspan', owner=self.bob)
        pool = self.event.get_game_pool()
        self.assertEqual(pool.count(), 1)

    def test_group_owned_games_included_via_attendee_membership(self):
        group = Group.objects.create(name='Test Group', slug='test-group')
        BoardGame.objects.create(name='Pandemic', group=group)
        GroupMembership.objects.create(user=self.bob, group=group, role='member')
        EventAttendance.objects.create(user=self.bob, event=self.event)
        pool = self.event.get_game_pool()
        names = list(pool.values_list('name', flat=True))
        self.assertIn('Pandemic', names)


@tag("unit")
class EventTagRelationTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='eventadmin', password='testpass123', is_site_admin=True
        )
        self.group = Group.objects.create(name='Tag Test Group')

    def _create_event(self, title='Test Event'):
        from django.utils import timezone
        date = timezone.now() + timezone.timedelta(days=7)
        return Event.objects.create(
            title=title, date=date, voting_deadline=date,
            created_by=self.admin, group=self.group,
        )

    def test_event_can_have_tags(self):
        event = self._create_event()
        tag1 = EventTag.objects.create(name='tournament')
        tag2 = EventTag.objects.create(name='casual')
        event.tags.add(tag1, tag2)
        self.assertEqual(event.tags.count(), 2)

    def test_event_can_have_no_tags(self):
        event = self._create_event()
        self.assertEqual(event.tags.count(), 0)

    def test_event_tags_are_event_tags_not_game_tags(self):
        event = self._create_event()
        event_tag = EventTag.objects.create(name='tournament')
        game_tag = GameTag.objects.create(name='racing')
        event.tags.add(event_tag)
        self.assertIn(event_tag, event.tags.all())
        self.assertNotIn(game_tag, event.tags.all())

    def test_event_tag_reverse_relation(self):
        event = self._create_event()
        tag = EventTag.objects.create(name='tournament')
        event.tags.add(tag)
        self.assertIn(event, tag.tagged_events.all())

    def test_filter_events_by_tag(self):
        event1 = self._create_event('Party Night')
        event2 = self._create_event('Tournament')
        tag = EventTag.objects.create(name='tournament')
        event1.tags.add(tag)
        tagged_events = Event.objects.filter(tags=tag)
        self.assertIn(event1, tagged_events)
        self.assertNotIn(event2, tagged_events)


def _make_event_admin(user, group):
    return GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_event_member(user, group):
    return GroupMembership.objects.create(user=user, group=group, role='member')


@tag("unit")
class EventGameOverrideModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='user', password='pass')
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.group = Group.objects.create(name='Override Group')
        _make_event_admin(self.admin, self.group)
        self.event = Event.objects.create(
            title='Override Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.admin,
            group=self.group,
        )
        self.game = BoardGame.objects.create(name='Catan', owner=self.admin)

    def test_create_override(self):
        override = EventGameOverride.objects.create(
            event=self.event,
            board_game=self.game,
            is_available=True,
            modified_by=self.admin,
        )
        self.assertTrue(override.is_available)
        self.assertEqual(override.event, self.event)
        self.assertEqual(override.board_game, self.game)

    def test_unique_constraint(self):
        EventGameOverride.objects.create(
            event=self.event, board_game=self.game,
            is_available=True, modified_by=self.admin,
        )
        with self.assertRaises(IntegrityError):
            EventGameOverride.objects.create(
                event=self.event, board_game=self.game,
                is_available=False, modified_by=self.admin,
            )


@tag("unit")
class GamePoolAvailabilityTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='pass')
        self.bob = User.objects.create_user(username='bob', password='pass')
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.group = Group.objects.create(name='Avail Group')
        _make_event_admin(self.admin, self.group)
        _make_event_member(self.alice, self.group)
        _make_event_member(self.bob, self.group)
        self.event = Event.objects.create(
            title='Avail Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.admin,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.alice, event=self.event)
        EventAttendance.objects.create(user=self.bob, event=self.event)
        self.game_alice = BoardGame.objects.create(
            name='Catan', owner=self.alice, bgg_id=13
        )
        self.game_bob = BoardGame.objects.create(
            name='Wingspan', owner=self.bob, bgg_id=300
        )

    def test_game_unavailable_when_no_owners_present(self):
        pool = compute_game_pool(self.event)
        for entry in pool.values():
            self.assertFalse(entry['is_available'])

    def test_game_available_when_owner_present(self):
        EventPresence.objects.create(
            event=self.event, user=self.alice, marked_by=self.admin
        )
        pool = compute_game_pool(self.event)
        catan = [v for v in pool.values() if v['name'] == 'Catan'][0]
        self.assertTrue(catan['is_available'])

    def test_deduplicated_game_available_if_any_copy_owner_present(self):
        BoardGame.objects.create(name='Catan', owner=self.bob, bgg_id=13)
        EventPresence.objects.create(
            event=self.event, user=self.bob, marked_by=self.admin
        )
        pool = compute_game_pool(self.event)
        catan = [v for v in pool.values() if v['name'] == 'Catan'][0]
        self.assertTrue(catan['is_available'])

    def test_override_forces_available(self):
        EventGameOverride.objects.create(
            event=self.event, board_game=self.game_alice,
            is_available=True, modified_by=self.admin,
        )
        pool = compute_game_pool(self.event)
        catan = [v for v in pool.values() if v['name'] == 'Catan'][0]
        self.assertTrue(catan['is_available'])
        self.assertTrue(catan['overridden'])

    def test_override_forces_unavailable(self):
        EventPresence.objects.create(
            event=self.event, user=self.alice, marked_by=self.admin
        )
        EventGameOverride.objects.create(
            event=self.event, board_game=self.game_alice,
            is_available=False, modified_by=self.admin,
        )
        pool = compute_game_pool(self.event)
        catan = [v for v in pool.values() if v['name'] == 'Catan'][0]
        self.assertFalse(catan['is_available'])
        self.assertTrue(catan['overridden'])


@tag("unit")
class EventModelTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='adminuser', password='testpass123', is_site_admin=True
        )
        self.group = Group.objects.create(name='Test Group')

    def test_create_event_with_all_fields(self):
        event_date = timezone.now() + timezone.timedelta(days=7)
        event = Event.objects.create(
            title='Friday Game Night', date=event_date,
            voting_deadline=event_date, location='Community Center',
            description='Weekly game night', created_by=self.admin,
            group=self.group,
        )
        self.assertEqual(event.title, 'Friday Game Night')
        self.assertEqual(event.date, event_date)
        self.assertEqual(event.location, 'Community Center')
        self.assertEqual(event.description, 'Weekly game night')
        self.assertEqual(event.created_by, self.admin)

    def test_create_event_with_only_required_fields(self):
        event_date = timezone.now() + timezone.timedelta(days=7)
        event = Event.objects.create(
            title='Quick Event', date=event_date,
            voting_deadline=event_date, created_by=self.admin,
            group=self.group,
        )
        self.assertEqual(event.location, '')
        self.assertEqual(event.description, '')

    def test_event_string_representation(self):
        event = Event.objects.create(
            title='Board Game Bash', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE, created_by=self.admin,
            group=self.group,
        )
        self.assertEqual(str(event), 'Board Game Bash')

    def test_show_individual_votes_defaults_to_false(self):
        event = Event.objects.create(
            title='Test Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE, created_by=self.admin,
            group=self.group,
        )
        self.assertFalse(event.show_individual_votes)

    def test_is_active_defaults_to_true(self):
        event = Event.objects.create(
            title='Test Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE, created_by=self.admin,
            group=self.group,
        )
        self.assertTrue(event.is_active)


@tag("unit")
class EventAttendanceModelTest(TestCase):

    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='testpass123')
        self.user2 = User.objects.create_user(username='user2', password='testpass123')
        self.admin = User.objects.create_user(
            username='eventadmin', password='testpass123', is_site_admin=True
        )
        self.group = Group.objects.create(name='Attendance Group')
        self.event = Event.objects.create(
            title='Test Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE, created_by=self.admin,
            group=self.group,
        )

    def test_create_event_attendance(self):
        attendance = EventAttendance.objects.create(user=self.user1, event=self.event)
        self.assertEqual(attendance.user, self.user1)
        self.assertEqual(attendance.event, self.event)
        self.assertIsNotNone(attendance.joined_at)

    def test_unique_constraint_prevents_duplicate_attendance(self):
        EventAttendance.objects.create(user=self.user1, event=self.event)
        with self.assertRaises(IntegrityError):
            EventAttendance.objects.create(user=self.user1, event=self.event)

    def test_user_can_attend_multiple_events(self):
        event2 = Event.objects.create(
            title='Second Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE, created_by=self.admin,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.user1, event=self.event)
        attendance2 = EventAttendance.objects.create(user=self.user1, event=event2)
        self.assertEqual(EventAttendance.objects.filter(user=self.user1).count(), 2)

    def test_multiple_users_can_attend_same_event(self):
        EventAttendance.objects.create(user=self.user1, event=self.event)
        EventAttendance.objects.create(user=self.user2, event=self.event)
        self.assertEqual(EventAttendance.objects.filter(event=self.event).count(), 2)


@tag("unit")
class SiteSettingsMaxCoCreatorsTest(TestCase):

    def test_default_max_co_creators(self):
        settings = SiteSettings.load()
        self.assertEqual(settings.max_co_creators, 3)

    def test_can_update_max_co_creators(self):
        settings = SiteSettings.load()
        settings.max_co_creators = 5
        settings.save()
        settings.refresh_from_db()
        self.assertEqual(settings.max_co_creators, 5)


@tag("unit")
class EventCoCreatorOrganizerTest(TestCase):

    def setUp(self):
        self.alice, self.bob, self.carol = _create_users('alice', 'bob', 'carol')

    def test_co_creator_is_organizer(self):
        event = Event.objects.create(
            title='Co-Created',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        event.co_creators.add(self.bob)
        self.assertTrue(event.is_organizer(self.bob))

    def test_creator_is_still_organizer_with_co_creators(self):
        event = Event.objects.create(
            title='Co-Created',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        event.co_creators.add(self.bob)
        self.assertTrue(event.is_organizer(self.alice))

    def test_non_co_creator_non_creator_is_not_organizer(self):
        event = Event.objects.create(
            title='Co-Created',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        event.co_creators.add(self.bob)
        self.assertFalse(event.is_organizer(self.carol))

    def test_additional_organizer_still_works_alongside_co_creator(self):
        event = Event.objects.create(
            title='Mixed Orgs',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        event.co_creators.add(self.bob)
        event.additional_organizers.add(self.carol)
        self.assertTrue(event.is_organizer(self.bob))
        self.assertTrue(event.is_organizer(self.carol))
        self.assertTrue(event.is_organizer(self.alice))

    def test_co_creator_games_in_game_pool(self):
        event = Event.objects.create(
            title='Pool Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        event.co_creators.add(self.bob)
        game = BoardGame.objects.create(name='Catan', owner=self.bob)
        pool = event.get_game_pool()
        self.assertIn(game, pool)

    def test_co_creator_games_not_in_pool_if_not_co_creator(self):
        event = Event.objects.create(
            title='Pool Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        game = BoardGame.objects.create(name='Catan', owner=self.bob)
        pool = event.get_game_pool()
        self.assertNotIn(game, pool)


@tag("unit")
class PrivateEventFormCoCreatorTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(
            username='alice', password='testpass123', email_verified=True,
        )
        self.bob = User.objects.create_user(
            username='bob', password='testpass123', email_verified=True,
        )
        self.carol = User.objects.create_user(
            username='carol', password='testpass123', email_verified=True,
        )
        Friendship.objects.create(
            requester=self.alice, receiver=self.bob, status='accepted',
        )
        Friendship.objects.create(
            requester=self.alice, receiver=self.carol, status='accepted',
        )

    def _valid_form_data(self, **overrides):
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        data = {
            'title': 'Test Event',
            'date': future,
            'privacy': 'public',
            'allow_invite_others': 'nobody',
            'co_creator_ids': '',
            'duration_minutes': 120,
        }
        data.update(overrides)
        return data

    def test_valid_form_with_co_creator_friends(self):
        form = PrivateEventForm(
            data=self._valid_form_data(co_creator_ids=str(self.bob.pk)),
            creator=self.alice,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_valid_form_with_multiple_co_creator_friends(self):
        ids = f'{self.bob.pk},{self.carol.pk}'
        form = PrivateEventForm(
            data=self._valid_form_data(co_creator_ids=ids),
            creator=self.alice,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_reject_non_friend_as_co_creator(self):
        dave = User.objects.create_user(username='dave', password='testpass123')
        form = PrivateEventForm(
            data=self._valid_form_data(co_creator_ids=str(dave.pk)),
            creator=self.alice,
        )
        self.assertFalse(form.is_valid())

    def test_reject_exceeding_max_co_creators(self):
        dave = User.objects.create_user(
            username='dave', password='testpass123', email_verified=True,
        )
        eve = User.objects.create_user(
            username='eve', password='testpass123', email_verified=True,
        )
        Friendship.objects.create(
            requester=self.alice, receiver=dave, status='accepted',
        )
        Friendship.objects.create(
            requester=self.alice, receiver=eve, status='accepted',
        )
        ids = f'{self.bob.pk},{self.carol.pk},{dave.pk},{eve.pk}'
        form = PrivateEventForm(
            data=self._valid_form_data(co_creator_ids=ids),
            creator=self.alice,
        )
        self.assertFalse(form.is_valid())

    def test_reject_self_as_co_creator(self):
        form = PrivateEventForm(
            data=self._valid_form_data(co_creator_ids=str(self.alice.pk)),
            creator=self.alice,
        )
        self.assertFalse(form.is_valid())

    def test_empty_co_creator_ids_is_valid(self):
        form = PrivateEventForm(
            data=self._valid_form_data(co_creator_ids=''),
            creator=self.alice,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_co_creator_ids_cleaned_properly(self):
        form = PrivateEventForm(
            data=self._valid_form_data(co_creator_ids=f'{self.bob.pk}, {self.carol.pk}'),
            creator=self.alice,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['co_creator_id_list'],
            [self.bob.pk, self.carol.pk],
        )

    def test_invalid_co_creator_id_format_rejected(self):
        form = PrivateEventForm(
            data=self._valid_form_data(co_creator_ids='abc'),
            creator=self.alice,
        )
        self.assertFalse(form.is_valid())
