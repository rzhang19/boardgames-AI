from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from club.models import (
    BoardGame, Event, EventAttendance, GameSession,
    Group, GroupMembership, PrivateEventCreationLog,
    SiteSettings,
)

User = get_user_model()


def _make_admin(user, group):
    GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='organizer')


def _make_member(user, group):
    GroupMembership.objects.create(user=user, group=group, role='member')


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


@tag("integration")
class EventCreateViewDurationTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123'
        )
        self.group = Group.objects.create(name='Duration Create Group')
        _make_admin(self.admin, self.group)

    def test_group_event_pre_fills_group_default_duration(self):
        self.group.default_event_duration_minutes = 90
        self.group.save()
        self.client.login(username='admin', password='testpass123')
        url = reverse('event_add', kwargs={'slug': self.group.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(form.initial.get('duration_minutes'), 90)

    def test_private_event_pre_fills_site_default_duration(self):
        site_settings = SiteSettings.load()
        site_settings.default_event_duration_minutes = 60
        site_settings.save()
        self.admin.email_verified = True
        self.admin.save()
        self.client.login(username='admin', password='testpass123')
        url = reverse('private_event_create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(form.initial.get('duration_minutes'), 60)

    def test_create_event_saves_end_time(self):
        event_date = timezone.now() + timedelta(days=1)
        self.client.login(username='admin', password='testpass123')
        url = reverse('event_add', kwargs={'slug': self.group.slug})
        response = self.client.post(url, {
            'title': 'Duration Event',
            'date': event_date.strftime('%Y-%m-%d'),
            'time': event_date.strftime('%H:%M'),
            'duration_minutes': 90,
            'voting_deadline_offset_minutes': 0,
        })
        event = Event.objects.get(title='Duration Event')
        expected_end = event.date + timedelta(minutes=90)
        self.assertEqual(event.end_time, expected_end)
        self.assertEqual(event.duration_minutes, 90)


@tag("integration")
class EventEditDurationTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123'
        )
        self.group = Group.objects.create(name='Edit Duration Group')
        _make_admin(self.admin, self.group)
        self.event_date = timezone.now() + timedelta(days=1)
        self.event = Event.objects.create(
            title='Editable Event',
            date=self.event_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=self.event_date,
            duration_minutes=120,
        )

    def test_can_edit_duration_before_event_starts(self):
        self.client.login(username='admin', password='testpass123')
        url = reverse('event_edit', kwargs={
            'slug': self.group.slug, 'pk': self.event.pk,
        })
        response = self.client.post(url, {
            'title': 'Editable Event',
            'date': self.event_date.strftime('%Y-%m-%d'),
            'time': self.event_date.strftime('%H:%M'),
            'duration_minutes': 180,
            'voting_deadline_offset_minutes': 0,
        })
        self.event.refresh_from_db()
        self.assertEqual(self.event.duration_minutes, 180)

    def test_cannot_change_duration_after_event_starts(self):
        past_date = timezone.now() - timedelta(minutes=30)
        event = Event.objects.create(
            title='Started Event',
            date=past_date,
            created_by=self.admin,
            group=self.group,
            voting_deadline=past_date,
            duration_minutes=120,
        )
        self.client.login(username='admin', password='testpass123')
        url = reverse('event_edit', kwargs={
            'slug': self.group.slug, 'pk': event.pk,
        })
        response = self.client.post(url, {
            'title': 'Started Event',
            'date': past_date.strftime('%Y-%m-%d'),
            'time': past_date.strftime('%H:%M'),
            'duration_minutes': 999,
            'voting_deadline_offset_minutes': 0,
        })
        event.refresh_from_db()
        self.assertEqual(event.duration_minutes, 120)


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
