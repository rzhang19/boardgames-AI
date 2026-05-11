from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from club.models import (
    BoardGame, Event, EventAttendance, Group, GroupInvite, GroupJoinRequest,
    GroupMembership, Vote,
)

User = get_user_model()


def _make_admin(user, group):
    return GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_member(user, group):
    return GroupMembership.objects.create(user=user, group=group, role='member')


def _make_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='admin')


# ---------------------------------------------------------------------------
# Full group lifecycle test
# ---------------------------------------------------------------------------

@tag("system")
class FullGroupLifecycleTest(TestCase):

    def setUp(self):
        self.creator = User.objects.create_user(
            username='creator', password='testpass123',
        )
        self.joiner = User.objects.create_user(
            username='joiner', password='testpass123',
        )

    def test_full_open_group_lifecycle(self):
        # 1. Create group
        self.client.login(username='creator', password='testpass123')
        resp = self.client.post(reverse('group_create'), {
            'name': 'Lifecycle Group',
            'description': 'Testing the full lifecycle',
            'join_policy': 'open',
            'discoverable': True,
        })
        self.assertEqual(resp.status_code, 302)
        group = Group.objects.get(name='Lifecycle Group')
        self.assertTrue(GroupMembership.objects.filter(
            user=self.creator, group=group, role='admin',
        ).exists())

        # 2. Another user joins (open policy)
        self.client.login(username='joiner', password='testpass123')
        resp = self.client.post(reverse('group_join', kwargs={'slug': group.slug}))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(GroupMembership.objects.filter(
            user=self.joiner, group=group, role='member',
        ).exists(), 'Joiner should be a member after joining')

        # 3. Creator adds an event
        self.client.login(username='creator', password='testpass123')
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        resp = self.client.post(reverse('event_add', kwargs={'slug': group.slug}), {
            'title': 'Lifecycle Event',
            'date': future,
            'time': '19:00',
            'location': 'Test Location',
        })
        self.assertEqual(resp.status_code, 302)
        event = Event.objects.get(title='Lifecycle Event')
        self.assertEqual(event.group, group)

        # 4. Both RSVP
        for user in [self.creator, self.joiner]:
            self.client.login(username=user.username, password='testpass123')
            resp = self.client.post(reverse('event_rsvp', kwargs={'slug': event.group.slug, 'pk': event.pk}))
            self.assertEqual(resp.status_code, 302)
        self.assertTrue(EventAttendance.objects.filter(
            user=self.joiner, event=event,
        ).exists())
        self.assertTrue(EventAttendance.objects.filter(
            user=self.creator, event=event,
        ).exists())

        # 5. Both users vote
        game1 = BoardGame.objects.create(name='Catan', owner=self.creator)
        game2 = BoardGame.objects.create(name='Chess', owner=self.creator)
        event.is_active = True
        event.voting_open = True
        event.save()

        for user, game in [(self.creator, game1), (self.joiner, game2)]:
            self.client.login(username=user.username, password='testpass123')
            resp = self.client.post(reverse('event_vote', kwargs={'slug': event.group.slug, 'pk': event.pk}), {
                'form-TOTAL_FORMS': '1',
                'form-INITIAL_FORMS': '0',
                'form-MIN_NUM_FORMS': '0',
                'form-MAX_NUM_FORMS': '1000',
                'form-0-board_game': str(game.pk),
            })
            self.assertEqual(resp.status_code, 302)
        self.assertEqual(Vote.objects.filter(event=event).count(), 2)

        # 6. View results
        self.client.login(username='creator', password='testpass123')
        resp = self.client.get(reverse('event_results', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Catan')
        self.assertContains(resp, 'Chess')

        # 7. Joiner leaves
        self.client.login(username='joiner', password='testpass123')
        resp = self.client.post(reverse('group_leave', kwargs={'slug': group.slug}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(GroupMembership.objects.filter(
            user=self.joiner, group=group,
        ).exists())
        self.assertFalse(EventAttendance.objects.filter(
            user=self.joiner, event=event,
        ).exists())

        # 8. Creator leaves (last member) -> disbands
        self.client.login(username='creator', password='testpass123')
        resp = self.client.post(reverse('group_leave', kwargs={'slug': group.slug}))
        self.assertEqual(resp.status_code, 302)
        group.refresh_from_db()
        self.assertTrue(group.is_disbanded)

    def test_request_join_lifecycle(self):
        group = Group.objects.create(
            name='Request Group', join_policy='request',
            discoverable=True,
        )
        _make_admin(self.creator, group)

        # Joiner submits request
        self.client.login(username='joiner', password='testpass123')
        resp = self.client.post(reverse('group_join', kwargs={'slug': group.slug}))
        self.assertEqual(resp.status_code, 200)
        req = GroupJoinRequest.objects.get(user=self.joiner, group=group)
        self.assertEqual(req.status, 'pending')

        # Creator approves
        self.client.login(username='creator', password='testpass123')
        resp = self.client.post(reverse('group_join_request_manage', kwargs={'slug': group.slug}), {
            'request_id': str(req.pk),
            'action': 'approve',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(GroupMembership.objects.filter(
            user=self.joiner, group=group, role='member',
        ).exists())

    def test_invite_lifecycle(self):
        group = Group.objects.create(
            name='Invite Group', join_policy='invite_only',
            discoverable=False,
        )
        _make_admin(self.creator, group)

        # Creator generates invite
        self.client.login(username='creator', password='testpass123')
        resp = self.client.post(reverse('group_invite_create', kwargs={'slug': group.slug}))
        self.assertEqual(resp.status_code, 200)
        invite = GroupInvite.objects.get(group=group)

        # Joiner accepts invite
        self.client.login(username='joiner', password='testpass123')
        resp = self.client.get(reverse('group_invite_accept', kwargs={'token': invite.token}))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(GroupMembership.objects.filter(
            user=self.joiner, group=group, role='member',
        ).exists())


# ---------------------------------------------------------------------------
# Recurring event preview lifecycle test
# ---------------------------------------------------------------------------

@tag("system")
class RecurringEventPreviewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_site_admin=True
        )
        cls.group = Group.objects.create(name='Preview Group')
        _make_organizer(cls.organizer, cls.group)

    def setUp(self):
        self.client.login(username='organizer', password='testpass123')

    def _post_valid_form(self, **kwargs):
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        defaults = {
            'title': 'Weekly Game Night',
            'start_date': future,
            'time': '18:00',
            'location': 'The Den',
            'description': 'Weekly meetup',
            'end_type': 'count',
            'occurrence_count': '4',
            'voting_deadline_offset_minutes': '60',
        }
        defaults.update(kwargs)
        return self.client.post(reverse('event_add_recurring', kwargs={'slug': self.group.slug}), defaults)

    def test_preview_shows_all_computed_dates(self):
        self._post_valid_form()
        response = self.client.get(reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 200)
        dates = response.context['dates']
        self.assertEqual(len(dates), 4)
        for d in dates:
            self.assertTrue(d['checked'])

    def test_preview_shows_event_details(self):
        self._post_valid_form()
        response = self.client.get(reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}))
        self.assertContains(response, 'Weekly Game Night')
        self.assertContains(response, 'The Den')

    def test_preview_without_session_redirects_to_form(self):
        response = self.client.get(reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('event_add_recurring', kwargs={'slug': self.group.slug}))

    def test_preview_with_skip_dates_creates_only_checked_events(self):
        self._post_valid_form(occurrence_count='4')
        response = self.client.post(reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}), {
            'submit': 'Create Events',
            'selected_dates': ['0', '2'],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Event.objects.filter(title='Weekly Game Night').count(), 2)

    def test_preview_creates_events_with_correct_fields(self):
        self._post_valid_form()
        response = self.client.post(reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}), {
            'submit': 'Create Events',
            'selected_dates': ['0', '1', '2', '3'],
        })
        self.assertEqual(response.status_code, 302)
        events = Event.objects.filter(title='Weekly Game Night').order_by('date')
        self.assertEqual(events.count(), 4)
        for event in events:
            self.assertEqual(event.location, 'The Den')
            self.assertEqual(event.description, 'Weekly meetup')
            self.assertEqual(event.created_by, self.organizer)
            self.assertEqual(event.date.hour, 18)
            self.assertEqual(event.date.minute, 0)
            self.assertEqual(event.voting_deadline_offset_minutes, 60)
            expected_deadline = event.date - timedelta(minutes=60)
            self.assertEqual(event.voting_deadline, expected_deadline)

    def test_preview_clears_session_after_creation(self):
        self._post_valid_form()
        self.client.post(reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}), {
            'submit': 'Create Events',
            'selected_dates': ['0', '1', '2', '3'],
        })
        session = self.client.session
        self.assertNotIn('recurring_event_form_data', session)
        self.assertNotIn('recurring_event_dates', session)

    def test_preview_cancel_clears_session_and_redirects(self):
        self._post_valid_form()
        response = self.client.post(reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}), {
            'cancel': 'Cancel',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('group_event_list', kwargs={'slug': self.group.slug}))
        session = self.client.session
        self.assertNotIn('recurring_event_form_data', session)
        self.assertNotIn('recurring_event_dates', session)
        self.assertEqual(Event.objects.filter(title='Weekly Game Night').count(), 0)

    def test_preview_skip_all_dates_fails(self):
        self._post_valid_form(occurrence_count='2')
        response = self.client.post(reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}), {
            'submit': 'Create Events',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Event.objects.filter(title='Weekly Game Night').count(), 0)

    def test_preview_redirects_to_group_event_list_after_creation(self):
        self._post_valid_form()
        response = self.client.post(reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}), {
            'submit': 'Create Events',
            'selected_dates': ['0', '1', '2', '3'],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('group_event_list', kwargs={'slug': self.group.slug}))

    def test_weekly_dates_are_seven_days_apart(self):
        self._post_valid_form(occurrence_count='3')
        response = self.client.get(reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}))
        dates = response.context['dates']
        self.assertEqual(len(dates), 3)
        for i in range(1, len(dates)):
            diff = dates[i]['datetime'] - dates[i - 1]['datetime']
            self.assertEqual(diff.days, 7)

    def test_end_date_produces_correct_number_of_dates(self):
        start = (timezone.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        end = (timezone.now() + timedelta(days=22)).strftime('%Y-%m-%d')
        self._post_valid_form(end_type='end_date', end_date=end, start_date=start)
        response = self.client.get(reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}))
        dates = response.context['dates']
        self.assertEqual(len(dates), 4)

    def test_preview_has_select_all_checkbox(self):
        self._post_valid_form()
        response = self.client.get(reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}))
        self.assertContains(response, 'select-all-toggle')
