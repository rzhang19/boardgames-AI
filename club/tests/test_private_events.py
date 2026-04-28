from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, tag
from django.utils import timezone

from club.models import (
    BoardGame,
    Event, EventAttendance, EventInvite,
    Group, GroupMembership,
    Notification,
    PrivateEventCreationLog,
)

User = get_user_model()


def _create_users(*usernames, password='testpass123'):
    return [User.objects.create_user(username=u, password=password) for u in usernames]


def _create_group(creator, name='Test Group'):
    group = Group.objects.create(name=name, created_by=creator)
    GroupMembership.objects.create(user=creator, group=group, role='admin')
    return group


# ---------------------------------------------------------------------------
# Event model changes
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
        self.assertFalse(event.auto_add_games)
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


# ---------------------------------------------------------------------------
# EventInvite model
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# PrivateEventCreationLog model
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Form tests
# ---------------------------------------------------------------------------

@tag("unit")
class PrivateEventFormTest(TestCase):

    def test_valid_form(self):
        from club.forms import PrivateEventForm
        future = (timezone.now() + timedelta(days=7)).date()
        form = PrivateEventForm(data={
            'title': 'Game Night',
            'description': 'Fun times',
            'location': 'My house',
            'date': future.strftime('%Y-%m-%d'),
            'privacy': 'public',
            'allow_invite_others': 'nobody',
            'auto_add_games': False,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_past_date_invalid(self):
        from club.forms import PrivateEventForm
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
        from club.forms import PrivateEventForm
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
        from club.forms import PrivateEventForm
        user = _create_users('alice')[0]
        future = (timezone.now() + timedelta(days=7)).date()
        form = PrivateEventForm(data={
            'title': 'No Group Event',
            'date': future.strftime('%Y-%m-%d'),
            'privacy': 'private',
            'allow_invite_others': 'friends_only',
            'auto_add_games': True,
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
        from club.forms import EventSettingsForm
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
            'auto_add_games': True,
            'organizers_can_edit_title': True,
            'organizers_can_edit_description': False,
            'organizers_can_edit_datetime': True,
        }, instance=event)
        self.assertTrue(form.is_valid(), form.errors)
        updated = form.save()
        self.assertEqual(updated.privacy, 'private')
        self.assertFalse(updated.show_description_publicly)
        self.assertTrue(updated.auto_add_games)


@tag("unit")
class EventInviteFormTest(TestCase):

    def test_valid_user_ids(self):
        from club.forms import EventInviteForm
        alice, bob = _create_users('alice', 'bob')
        form = EventInviteForm(data={'user_ids': str(bob.pk)})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['user_ids'], [bob.pk])

    def test_multiple_user_ids(self):
        from club.forms import EventInviteForm
        alice, bob, carol = _create_users('alice', 'bob', 'carol')
        form = EventInviteForm(data={'user_ids': f'{bob.pk},{carol.pk}'})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['user_ids'], [bob.pk, carol.pk])

    def test_empty_user_ids_invalid(self):
        from club.forms import EventInviteForm
        form = EventInviteForm(data={'user_ids': ''})
        self.assertFalse(form.is_valid())


# ---------------------------------------------------------------------------
# View tests — Private event creation
# ---------------------------------------------------------------------------

@tag("integration")
class PrivateEventCreateViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='alice', password='testpass123', email_verified=True,
        )

    def test_create_private_event_success(self):
        from django.urls import reverse
        self.client.login(username='alice', password='testpass123')
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        resp = self.client.post(reverse('private_event_create'), {
            'title': 'Game Night',
            'date': future,
            'description': 'Fun times',
            'location': 'My house',
            'privacy': 'public',
            'allow_invite_others': 'nobody',
            'auto_add_games': False,
        })
        self.assertEqual(resp.status_code, 302)
        event = Event.objects.get(title='Game Night')
        self.assertIsNone(event.group)
        self.assertEqual(event.created_by, self.user)
        self.assertEqual(event.privacy, 'public')
        self.assertTrue(
            PrivateEventCreationLog.objects.filter(user=self.user, event=event).exists()
        )

    def test_unverified_user_blocked(self):
        from django.urls import reverse
        self.user.email_verified = False
        self.user.save()
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(reverse('private_event_create'))
        self.assertEqual(resp.status_code, 403)

    def test_requires_login(self):
        from django.urls import reverse
        resp = self.client.get(reverse('private_event_create'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_rate_limited(self):
        from django.urls import reverse
        for i in range(5):
            PrivateEventCreationLog.objects.create(user=self.user)
        self.client.login(username='alice', password='testpass123')
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        resp = self.client.post(reverse('private_event_create'), {
            'title': 'Blocked Event',
            'date': future,
            'privacy': 'public',
            'allow_invite_others': 'nobody',
        })
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# View tests — Private event detail (redirect for group events)
# ---------------------------------------------------------------------------

@tag("integration")
class PrivateEventDetailViewTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='testpass123')
        self.bob = User.objects.create_user(username='bob', password='testpass123')
        self.group = Group.objects.create(name='Test Group')
        GroupMembership.objects.create(user=self.alice, group=self.group, role='admin')

    def test_group_event_redirects(self):
        from django.urls import reverse
        event = Event.objects.create(
            title='Group Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            group=self.group,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(reverse('private_event_detail', kwargs={'pk': event.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/groups/{self.group.slug}/events/{event.pk}/', resp.url)

    def test_private_event_shows_detail(self):
        from django.urls import reverse
        event = Event.objects.create(
            title='Private Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
            privacy='public',
        )
        self.client.login(username='bob', password='testpass123')
        resp = self.client.get(reverse('private_event_detail', kwargs={'pk': event.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_private_event_hidden_from_non_invitee(self):
        from django.urls import reverse
        event = Event.objects.create(
            title='Secret Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
            privacy='private',
        )
        self.client.login(username='bob', password='testpass123')
        resp = self.client.get(reverse('private_event_detail', kwargs={'pk': event.pk}))
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# View tests — Private event RSVP
# ---------------------------------------------------------------------------

@tag("integration")
class PrivateEventRsvpViewTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='testpass123')
        self.bob = User.objects.create_user(username='bob', password='testpass123')

    def test_rsvp_public_event(self):
        from django.urls import reverse
        event = Event.objects.create(
            title='Public Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
            privacy='public',
        )
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(reverse('private_event_rsvp', kwargs={'pk': event.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            EventAttendance.objects.filter(user=self.bob, event=event).exists()
        )

    def test_rsvp_private_event_without_invite_fails(self):
        from django.urls import reverse
        event = Event.objects.create(
            title='Private Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
            privacy='private',
        )
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(reverse('private_event_rsvp', kwargs={'pk': event.pk}))
        self.assertEqual(resp.status_code, 403)

    def test_rsvp_private_event_with_invite(self):
        from django.urls import reverse
        event = Event.objects.create(
            title='Private Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
            privacy='private',
        )
        EventInvite.objects.create(
            event=event, user=self.bob, invited_by=self.alice,
        )
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(reverse('private_event_rsvp', kwargs={'pk': event.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            EventAttendance.objects.filter(user=self.bob, event=event).exists()
        )

    def test_cancel_rsvp(self):
        from django.urls import reverse
        event = Event.objects.create(
            title='Public Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
            privacy='public',
        )
        EventAttendance.objects.create(user=self.bob, event=event)
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(reverse('private_event_rsvp', kwargs={'pk': event.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(
            EventAttendance.objects.filter(user=self.bob, event=event).exists()
        )


# ---------------------------------------------------------------------------
# View tests — Event invite
# ---------------------------------------------------------------------------

@tag("integration")
class EventInviteViewTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='testpass123')
        self.bob = User.objects.create_user(username='bob', password='testpass123')
        self.event = Event.objects.create(
            title='My Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
            privacy='private',
        )

    def test_creator_can_invite(self):
        from django.urls import reverse
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(reverse('event_invite', kwargs={'pk': self.event.pk}), {
            'user_ids': str(self.bob.pk),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            EventInvite.objects.filter(event=self.event, user=self.bob).exists()
        )

    def test_non_organizer_cannot_invite(self):
        from django.urls import reverse
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(reverse('event_invite', kwargs={'pk': self.event.pk}), {
            'user_ids': str(self.alice.pk),
        })
        self.assertEqual(resp.status_code, 403)

    def test_accept_invite(self):
        from django.urls import reverse
        invite = EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(
            reverse('event_invite_respond', kwargs={'pk': self.event.pk, 'invite_pk': invite.pk, 'status': 'accept'}),
        )
        self.assertEqual(resp.status_code, 302)
        invite.refresh_from_db()
        self.assertEqual(invite.status, 'accepted')
        self.assertTrue(
            EventAttendance.objects.filter(user=self.bob, event=self.event).exists()
        )

    def test_decline_invite(self):
        from django.urls import reverse
        invite = EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(
            reverse('event_invite_respond', kwargs={'pk': self.event.pk, 'invite_pk': invite.pk, 'status': 'decline'}),
        )
        self.assertEqual(resp.status_code, 302)
        invite.refresh_from_db()
        self.assertEqual(invite.status, 'declined')
        self.assertFalse(
            EventAttendance.objects.filter(user=self.bob, event=self.event).exists()
        )

    def test_accept_wrong_user_forbidden(self):
        from django.urls import reverse
        carol = User.objects.create_user(username='carol', password='testpass123')
        invite = EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        self.client.login(username='carol', password='testpass123')
        resp = self.client.post(
            reverse('event_invite_respond', kwargs={'pk': self.event.pk, 'invite_pk': invite.pk, 'status': 'accept'}),
        )
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# Notification tests — Event invites
# ---------------------------------------------------------------------------

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
        from club.notifications import notify_event_invite_sent
        notify_event_invite_sent(self.bob, self.alice, self.event)
        notif = Notification.objects.get(
            user=self.bob, notification_type='event_invite',
        )
        self.assertIn('alice', notif.message)
        self.assertIn('Game Night', notif.message)
        self.assertIn(f'/events/{self.event.pk}/', notif.url)

    def test_invite_accepted_creates_notification(self):
        from club.notifications import notify_event_invite_accepted
        notify_event_invite_accepted(self.alice, self.bob, self.event)
        notif = Notification.objects.get(
            user=self.alice, notification_type='event_invite_accepted',
        )
        self.assertIn('bob', notif.message)
        self.assertIn('Game Night', notif.message)

    def test_invite_declined_creates_notification(self):
        from club.notifications import notify_event_invite_declined
        notify_event_invite_declined(self.alice, self.bob, self.event)
        notif = Notification.objects.get(
            user=self.alice, notification_type='event_invite_declined',
        )
        self.assertIn('bob', notif.message)
        self.assertIn('Game Night', notif.message)

    def test_organizer_designated_creates_notification(self):
        from club.notifications import notify_event_organizer_designated
        notify_event_organizer_designated(self.bob, self.event)
        notif = Notification.objects.get(
            user=self.bob, notification_type='event_organizer_designated',
        )
        self.assertIn('Game Night', notif.message)
        self.assertIn(f'/events/{self.event.pk}/', notif.url)


@tag("integration")
class EventInviteNotificationViewTest(TestCase):

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

    def test_sending_invite_creates_notification(self):
        from django.urls import reverse
        self.client.login(username='alice', password='testpass123')
        self.client.post(reverse('event_invite', kwargs={'pk': self.event.pk}), {
            'user_ids': str(self.bob.pk),
        })
        self.assertTrue(
            Notification.objects.filter(
                user=self.bob,
                notification_type='event_invite',
            ).exists()
        )

    def test_accepting_invite_creates_notification_for_inviter(self):
        from django.urls import reverse
        invite = EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        self.client.login(username='bob', password='testpass123')
        self.client.post(
            reverse('event_invite_respond', kwargs={'pk': self.event.pk, 'invite_pk': invite.pk, 'status': 'accept'}),
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.alice,
                notification_type='event_invite_accepted',
            ).exists()
        )

    def test_declining_invite_creates_notification_for_inviter(self):
        from django.urls import reverse
        invite = EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        self.client.login(username='bob', password='testpass123')
        self.client.post(
            reverse('event_invite_respond', kwargs={'pk': self.event.pk, 'invite_pk': invite.pk, 'status': 'decline'}),
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.alice,
                notification_type='event_invite_declined',
            ).exists()
        )


# ---------------------------------------------------------------------------
# Auto-add games — Event.get_game_pool()
# ---------------------------------------------------------------------------

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
        self.event.auto_add_games = False
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
