from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from club.models import (
    BoardGame, Event, EventAttendance, EventPresence,
    Group, GroupMembership,
)

User = get_user_model()


def _make_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_group_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='organizer')


def _make_member(user, group):
    GroupMembership.objects.create(user=user, group=group, role='member')


@tag("unit")
class EventPresenceModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='user', password='pass')
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.group = Group.objects.create(name='Presence Group')
        _make_organizer(self.admin, self.group)
        self.event = Event.objects.create(
            title='Presence Event',
            date='2026-05-01T18:00:00Z',
            voting_deadline='2026-05-01T18:00:00Z',
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
        from django.db import IntegrityError
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
        _make_organizer(self.admin, self.group)

    def test_not_locked_before_12h(self):
        event = Event.objects.create(
            title='Future Event',
            date=timezone.now() + timezone.timedelta(hours=24),
            voting_deadline=timezone.now() + timezone.timedelta(hours=24),
            created_by=self.admin,
            group=self.group,
        )
        from club.presence import is_presence_locked
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
        from club.presence import is_presence_locked
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
        from club.presence import is_presence_locked
        locked, lock_time = is_presence_locked(event)
        self.assertTrue(locked)


@tag("integration")
class TogglePresenceViewTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        self.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        self.outsider = User.objects.create_user(
            username='outsider', password='testpass123'
        )
        self.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True
        )
        self.group = Group.objects.create(name='Toggle Presence Group')
        _make_organizer(self.organizer, self.group)
        _make_member(self.member, self.group)
        _make_member(self.site_admin, self.group)
        self.event = Event.objects.create(
            title='Toggle Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.member, event=self.event)

    def test_organizer_can_mark_present(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_presence', kwargs={'pk': self.event.pk}),
            {'user_id': self.member.pk},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['present'])
        self.assertTrue(
            EventPresence.objects.filter(
                event=self.event, user=self.member
            ).exists()
        )

    def test_organizer_can_unmark_present(self):
        EventPresence.objects.create(
            event=self.event, user=self.member, marked_by=self.organizer
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_presence', kwargs={'pk': self.event.pk}),
            {'user_id': self.member.pk},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['present'])
        self.assertFalse(
            EventPresence.objects.filter(
                event=self.event, user=self.member
            ).exists()
        )

    def test_regular_member_cannot_toggle_presence(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_presence', kwargs={'pk': self.event.pk}),
            {'user_id': self.member.pk},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_cannot_toggle(self):
        response = self.client.post(
            reverse('event_toggle_presence', kwargs={'pk': self.event.pk}),
            {'user_id': self.member.pk},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_cannot_mark_user_without_attendance(self):
        non_attendee = User.objects.create_user(
            username='no_rsvp', password='testpass123'
        )
        _make_member(non_attendee, self.group)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_presence', kwargs={'pk': self.event.pk}),
            {'user_id': non_attendee.pk},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_locked_after_12h_organizer_denied(self):
        past_event = Event.objects.create(
            title='Past Event',
            date=timezone.now() - timezone.timedelta(hours=13),
            voting_deadline=timezone.now() - timezone.timedelta(hours=13),
            created_by=self.organizer,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.member, event=past_event)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_presence', kwargs={'pk': past_event.pk}),
            {'user_id': self.member.pk},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_site_admin_can_toggle_after_12h_lock(self):
        past_event = Event.objects.create(
            title='Admin Past Event',
            date=timezone.now() - timezone.timedelta(hours=13),
            voting_deadline=timezone.now() - timezone.timedelta(hours=13),
            created_by=self.organizer,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.member, event=past_event)
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_presence', kwargs={'pk': past_event.pk}),
            {'user_id': self.member.pk},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

    def test_get_request_not_allowed(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_toggle_presence', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 405)


@tag("integration")
class PrivateEventTogglePresenceTest(TestCase):

    def setUp(self):
        self.creator = User.objects.create_user(
            username='creator', password='testpass123'
        )
        self.attendee = User.objects.create_user(
            username='attendee', password='testpass123'
        )
        self.other = User.objects.create_user(
            username='other', password='testpass123'
        )
        self.event = Event.objects.create(
            title='Private Presence Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.creator,
            privacy='public',
        )
        EventAttendance.objects.create(user=self.attendee, event=self.event)

    def test_creator_can_mark_present(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_presence', kwargs={'pk': self.event.pk}),
            {'user_id': self.attendee.pk},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            EventPresence.objects.filter(
                event=self.event, user=self.attendee
            ).exists()
        )

    def test_non_creator_cannot_toggle(self):
        self.client.login(username='other', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_presence', kwargs={'pk': self.event.pk}),
            {'user_id': self.attendee.pk},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_can_mark_user_with_event_access_but_no_attendance(self):
        accessible_user = User.objects.create_user(
            username='accessible', password='testpass123'
        )
        from club.permissions import can_view_private_event
        self.assertTrue(
            can_view_private_event(accessible_user, self.event)
        )
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(
            reverse('event_toggle_presence', kwargs={'pk': self.event.pk}),
            {'user_id': accessible_user.pk},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
