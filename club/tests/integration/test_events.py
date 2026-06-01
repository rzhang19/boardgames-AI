from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from club.models import (
    BoardGame,
    Event,
    EventAttendance,
    EventInvite,
    EventPresence,
    EventTag,
    Friendship,
    GameOwnershipProposal,
    GameSession,
    GameSessionPlayer,
    Group,
    GroupMembership,
    Notification,
    PrivateEventCreationLog,
    SiteSettings,
)

User = get_user_model()

FUTURE_DATE = timezone.now() + timedelta(days=30)


def _make_group_admin(user, group):
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


@tag("integration")
class EventListViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='admin', password='testpass123', is_site_admin=True
        )
        cls.group = Group.objects.create(name='Test Group')
        _make_group_admin(cls.admin, cls.group)
        cls.event1 = Event.objects.create(
            title='Friday Night', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            location='Community Center', created_by=cls.admin,
            group=cls.group
        )
        cls.event2 = Event.objects.create(
            title='Saturday Bash', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=cls.admin, group=cls.group
        )

    def test_event_list_displays_all_events(self):
        response = self.client.get(reverse('event_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Friday Night')
        self.assertContains(response, 'Saturday Bash')


@tag("integration")
class EventCreateViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='admin', password='testpass123', is_site_admin=True
        )
        cls.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )
        cls.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123',
            is_site_admin=True,
        )
        cls.group = Group.objects.create(name='Create Group')
        _make_group_admin(cls.admin, cls.group)

    def test_create_page_requires_login(self):
        response = self.client.get(reverse('event_add', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_admin_can_access_create_page(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('event_add', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_access_create_page(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('event_add', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_event_with_date_and_time(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Game Night',
            'date': '2026-07-01',
            'time': '18:00',
            'location': 'The Den',
            'description': 'Weekly meetup',
        })
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title='Game Night')
        self.assertEqual(event.created_by, self.admin)
        self.assertEqual(event.location, 'The Den')
        self.assertEqual(event.date.hour, 18)
        self.assertEqual(event.date.minute, 0)
        self.assertEqual(response.url, reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk}))

    def test_create_event_with_date_only_defaults_time_to_midnight(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Midnight Event',
            'date': '2026-08-01',
        })
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title='Midnight Event')
        self.assertEqual(event.date.hour, 0)
        self.assertEqual(event.date.minute, 0)
        self.assertEqual(event.location, '')
        self.assertEqual(event.description, '')

    def test_create_event_with_required_fields_only(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Minimal Event',
            'date': '2026-08-01',
            'time': '18:00',
        })
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title='Minimal Event')
        self.assertEqual(event.location, '')
        self.assertEqual(event.description, '')

    def test_create_event_without_title_fails(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': '',
            'date': '2026-08-01',
            'time': '18:00',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.exists())

    def test_create_event_without_date_fails(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'No Date Event',
            'date': '',
            'time': '18:00',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='No Date Event').exists())

    def test_regular_user_cannot_create_event(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Sneaky Event',
            'date': '2026-08-01',
            'time': '18:00',
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Event.objects.filter(title='Sneaky Event').exists())

    def test_cannot_create_event_with_past_date(self):
        self.client.login(username='admin', password='testpass123')
        past = (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Past Event',
            'date': past,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Past Event').exists())
        self.assertContains(response, 'past')

    def test_can_create_event_with_future_date(self):
        self.client.login(username='admin', password='testpass123')
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Future Event',
            'date': future,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Event.objects.filter(title='Future Event').exists())

    def test_create_event_form_html(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('event_add', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="date"')
        self.assertContains(response, 'type="time"')
        self.assertContains(response, 'Event Details')
        self.assertContains(response, 'Date &amp; Time')
        self.assertContains(response, 'Location')
        html = response.content.decode()
        asterisk_count = html.count('<span class="required-asterisk">')
        self.assertEqual(asterisk_count, 3)
        title_section = html[html.find('id="id_title"') - 200:html.find('id="id_title"') + 50]
        self.assertIn('required-asterisk', title_section)
        date_section = html[html.find('id="id_date"') - 200:html.find('id="id_date"') + 50]
        self.assertIn('required-asterisk', date_section)
        time_section = html[html.find('id="id_time"') - 200:html.find('id="id_time"') + 50]
        self.assertNotIn('required-asterisk', time_section)
        location_section = html[html.find('id="id_location"') - 200:html.find('id="id_location"') + 50]
        self.assertNotIn('required-asterisk', location_section)
        description_section = html[html.find('id="id_description"') - 200:html.find('id="id_description"') + 50]
        self.assertNotIn('required-asterisk', description_section)

    def test_site_admin_without_membership_cannot_access_create_page(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('event_add', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 403)

    def test_site_admin_as_organizer_can_create_event(self):
        _make_group_admin(self.site_admin, self.group)
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Admin Event',
            'date': '2026-09-01',
            'time': '18:00',
            'location': 'Admin HQ',
            'description': 'Created by site admin',
        })
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title='Admin Event')
        self.assertEqual(event.created_by, self.site_admin)
        self.assertEqual(event.location, 'Admin HQ')

    def test_create_event_uses_global_offset_for_voting_deadline(self):
        site_settings = SiteSettings.load()
        site_settings.default_voting_offset_minutes = 60
        site_settings.save()
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Offset Event',
            'date': '2026-07-01',
            'time': '18:00',
            'voting_deadline_offset_minutes': '60',
        })
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title='Offset Event')
        self.assertEqual(event.voting_deadline_offset_minutes, 60)
        expected_deadline = event.date - timedelta(minutes=60)
        self.assertEqual(event.voting_deadline, expected_deadline)

    def test_create_event_with_zero_offset_sets_deadline_to_event_time(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Zero Offset',
            'date': '2026-07-01',
            'time': '18:00',
            'voting_deadline_offset_minutes': '0',
        })
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title='Zero Offset')
        self.assertEqual(event.voting_deadline_offset_minutes, 0)
        self.assertEqual(event.voting_deadline, event.date)

    def test_create_event_default_offset_is_zero_when_no_global_setting(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Default Offset',
            'date': '2026-07-01',
            'time': '18:00',
        })
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title='Default Offset')
        self.assertEqual(event.voting_deadline_offset_minutes, 0)


@tag("integration")
class EventDetailViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='admin', password='testpass123', is_site_admin=True
        )
        cls.group = Group.objects.create(name='Detail Group')
        _make_group_admin(cls.admin, cls.group)
        cls.event = Event.objects.create(
            title='Test Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            location='Hall', description='A test event',
            created_by=cls.admin, group=cls.group
        )

    def setUp(self):
        self.client.login(username='admin', password='testpass123')

    def test_event_detail_displays_info(self):
        response = self.client.get(reverse('event_detail', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Event')
        self.assertContains(response, 'Hall')
        self.assertContains(response, 'A test event')

    def test_event_detail_nonexistent_returns_404(self):
        response = self.client.get(reverse('event_detail', kwargs={'slug': self.group.slug, 'pk': 9999}))
        self.assertEqual(response.status_code, 404)

    def test_event_detail_shows_attendees(self):
        user1 = User.objects.create_user(username='u1', password='testpass123')
        EventAttendance.objects.create(user=user1, event=self.event)
        response = self.client.get(reverse('event_detail', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertContains(response, 'u1')

    def test_event_detail_shows_rsvp_for_authenticated_user(self):
        user = User.objects.create_user(username='attendee', password='testpass123')
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertContains(response, 'RSVP')

    def test_unauthenticated_gets_403_on_event_detail(self):
        self.client.logout()
        response = self.client.get(reverse('event_detail', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 403)


@tag("integration")
class EventRSVPTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='admin', password='testpass123', is_site_admin=True
        )
        cls.user = User.objects.create_user(
            username='attendee', password='testpass123'
        )
        cls.group = Group.objects.create(name='RSVP Group')
        _make_group_admin(cls.admin, cls.group)
        GroupMembership.objects.create(user=cls.user, group=cls.group, role='member')
        cls.event = Event.objects.create(
            title='RSVP Event', date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=cls.admin, group=cls.group
        )

    def test_rsvp_requires_login(self):
        response = self.client.post(reverse('event_rsvp', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_user_can_rsvp(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(reverse('event_rsvp', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            EventAttendance.objects.filter(user=self.user, event=self.event).exists()
        )

    def test_user_can_cancel_rsvp(self):
        EventAttendance.objects.create(user=self.user, event=self.event)
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(reverse('event_rsvp', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            EventAttendance.objects.filter(user=self.user, event=self.event).exists()
        )

    def test_rsvp_redirects_to_event_detail(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(reverse('event_rsvp', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.url, reverse('event_detail', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))

    def test_rsvp_nonexistent_event_returns_404(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(reverse('event_rsvp', kwargs={'slug': self.group.slug, 'pk': 9999}))
        self.assertEqual(response.status_code, 404)

    def test_non_member_cannot_rsvp(self):
        outsider = User.objects.create_user(username='outsider', password='testpass123')
        self.client.login(username='outsider', password='testpass123')
        response = self.client.post(reverse('event_rsvp', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 403)


@tag("integration")
class EventEditViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_site_admin=True
        )
        cls.other_organizer = User.objects.create_user(
            username='other_org', password='testpass123', is_site_admin=True
        )
        cls.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )
        cls.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123',
            is_site_admin=True,
        )
        cls.site_admin_only = User.objects.create_user(
            username='siteadminonly', password='testpass123',
            is_site_admin=True,
        )
        cls.group = Group.objects.create(name='Edit Group')
        _make_group_admin(cls.organizer, cls.group)
        _make_group_admin(cls.other_organizer, cls.group)
        _make_group_admin(cls.site_admin_only, cls.group)
        cls.future_date = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        cls.event = Event.objects.create(
            title='Original Title',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            location='Original Location',
            description='Original Description',
            created_by=cls.organizer,
            group=cls.group,
        )

    def test_edit_page_requires_login(self):
        response = self.client.get(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_organizer_can_access_edit_page(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)

    def test_other_organizer_can_access_edit_page(self):
        self.client.login(username='other_org', password='testpass123')
        response = self.client.get(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_access_edit_page(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 403)

    def test_site_admin_who_is_organizer_can_access_edit_page(self):
        self.client.login(username='siteadminonly', password='testpass123')
        response = self.client.get(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)

    def test_edit_page_shows_pre_populated_form_and_edit_action(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertContains(response, 'Original Title')
        self.assertContains(response, 'Original Location')
        self.assertContains(response, 'Original Description')
        self.assertContains(response, 'Edit Event')
        self.assertContains(response, 'Edit Event</button>')

    def test_organizer_can_edit_event_title(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}), {
            'title': 'Updated Title',
            'date': self.future_date,
            'time': '',
            'location': 'Original Location',
            'description': 'Original Description',
        })
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, 'Updated Title')

    def test_organizer_can_edit_all_fields(self):
        self.client.login(username='organizer', password='testpass123')
        new_date = (timezone.now() + timedelta(days=14)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}), {
            'title': 'Completely New Title',
            'date': new_date,
            'time': '19:30',
            'location': 'New Venue',
            'description': 'Updated description',
        })
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, 'Completely New Title')
        self.assertEqual(self.event.location, 'New Venue')
        self.assertEqual(self.event.description, 'Updated description')
        self.assertEqual(self.event.date.hour, 19)
        self.assertEqual(self.event.date.minute, 30)

    def test_edit_redirects_to_event_detail(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}), {
            'title': 'Updated Title',
            'date': self.future_date,
            'time': '',
            'location': 'Original Location',
            'description': 'Original Description',
        })
        self.assertRedirects(response, reverse('event_detail', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))

    def test_cannot_edit_date_to_past(self):
        self.client.login(username='organizer', password='testpass123')
        past = (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}), {
            'title': 'Original Title',
            'date': past,
            'time': '',
            'location': 'Original Location',
            'description': 'Original Description',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'past')
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, 'Original Title')

    def test_edit_past_event_with_field_changes(self):
        past_event = Event.objects.create(
            title='Old Past Event',
            date=timezone.now() - timedelta(days=2),
            voting_deadline=timezone.now() - timedelta(days=2),
            location='Old Place',
            description='Old Desc',
            created_by=self.organizer,
            group=self.group,
        )
        self.client.login(username='organizer', password='testpass123')
        date_str = past_event.date.strftime('%Y-%m-%d')
        time_str = past_event.date.strftime('%H:%M')
        response = self.client.post(reverse('event_edit', kwargs={'slug': past_event.group.slug, 'pk': past_event.pk}), {
            'title': 'Updated Past Event',
            'date': date_str,
            'time': time_str,
            'location': 'New Place',
            'description': 'New Desc',
        })
        self.assertEqual(response.status_code, 302)
        past_event.refresh_from_db()
        self.assertEqual(past_event.title, 'Updated Past Event')
        self.assertEqual(past_event.location, 'New Place')
        self.assertEqual(past_event.description, 'New Desc')

    def test_edit_nonexistent_event_returns_404(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('event_edit', kwargs={'slug': self.group.slug, 'pk': 9999}))
        self.assertEqual(response.status_code, 404)

    def test_edit_preserves_created_by(self):
        self.client.login(username='other_org', password='testpass123')
        self.client.post(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}), {
            'title': 'Updated by Other',
            'date': self.future_date,
            'time': '',
            'location': 'Original Location',
            'description': 'Original Description',
        })
        self.event.refresh_from_db()
        self.assertEqual(self.event.created_by, self.organizer)

    def test_regular_user_cannot_edit_event_via_post(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}), {
            'title': 'Hacked Title',
            'date': self.future_date,
            'time': '',
            'location': 'Original Location',
            'description': 'Original Description',
        })
        self.assertEqual(response.status_code, 403)
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, 'Original Title')

    def test_edit_page_shows_required_asterisks(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        asterisk_count = html.count('<span class="required-asterisk">')
        self.assertEqual(asterisk_count, 3)

    def test_site_admin_without_membership_cannot_edit(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 403)

    def test_site_admin_who_is_organizer_can_edit_event_via_post(self):
        self.client.login(username='siteadminonly', password='testpass123')
        response = self.client.post(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}), {
            'title': 'Admin Edited Title',
            'date': self.future_date,
            'time': '',
            'location': 'Original Location',
            'description': 'Original Description',
        })
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, 'Admin Edited Title')

    def test_edit_event_preserves_per_event_offset(self):
        self.event.voting_deadline_offset_minutes = 30
        self.event.save()
        new_date = (timezone.now() + timedelta(days=14)).strftime('%Y-%m-%d')
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}), {
            'title': 'Original Title',
            'date': new_date,
            'time': '19:30',
            'location': 'Original Location',
            'description': 'Original Description',
            'voting_deadline_offset_minutes': '30',
        })
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.voting_deadline_offset_minutes, 30)
        expected_deadline = self.event.date - timedelta(minutes=30)
        self.assertEqual(self.event.voting_deadline, expected_deadline)

    def test_edit_event_offset_change_updates_deadline(self):
        self.event.voting_deadline_offset_minutes = 0
        self.event.save()
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}), {
            'title': 'Original Title',
            'date': self.future_date,
            'time': '18:00',
            'location': 'Original Location',
            'description': 'Original Description',
            'voting_deadline_offset_minutes': '60',
        })
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.voting_deadline_offset_minutes, 60)
        expected_deadline = self.event.date - timedelta(minutes=60)
        self.assertEqual(self.event.voting_deadline, expected_deadline)

    def test_edit_event_does_not_use_global_offset(self):
        site_settings = SiteSettings.load()
        site_settings.default_voting_offset_minutes = 120
        site_settings.save()
        self.event.voting_deadline_offset_minutes = 30
        self.event.save()
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}), {
            'title': 'Original Title',
            'date': self.future_date,
            'time': '18:00',
            'location': 'Original Location',
            'description': 'Original Description',
            'voting_deadline_offset_minutes': '30',
        })
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.voting_deadline_offset_minutes, 30)
        expected_deadline = self.event.date - timedelta(minutes=30)
        self.assertEqual(self.event.voting_deadline, expected_deadline)


@tag("integration")
class EventDetailEditButtonTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_site_admin=True
        )
        cls.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )
        cls.site_admin_only = User.objects.create_user(
            username='siteadminonly', password='testpass123',
            is_site_admin=True,
        )
        cls.group = Group.objects.create(name='Button Group')
        _make_group_admin(cls.organizer, cls.group)
        _make_group_admin(cls.site_admin_only, cls.group)
        cls.event = Event.objects.create(
            title='Test Event',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=cls.organizer,
            group=cls.group,
        )

    def test_organizer_sees_edit_button_on_event_detail(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertContains(response, reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertContains(response, 'Edit Event')

    def test_regular_user_does_not_see_edit_button(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertNotContains(response, 'Edit Event')

    def test_anonymous_user_gets_403_on_event_detail(self):
        response = self.client.get(reverse('event_detail', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertEqual(response.status_code, 403)

    def test_site_admin_who_is_organizer_sees_edit_button_on_event_detail(self):
        self.client.login(username='siteadminonly', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertContains(response, reverse('event_edit', kwargs={'slug': self.event.group.slug, 'pk': self.event.pk}))
        self.assertContains(response, 'Edit Event')


@tag("integration")
class RecurringEventAccessTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_site_admin=True
        )
        cls.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )
        cls.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123',
            is_site_admin=True,
        )
        cls.group = Group.objects.create(name='Recurring Group')
        _make_group_admin(cls.organizer, cls.group)

    def test_recurring_page_requires_login(self):
        response = self.client.get(reverse('event_add_recurring', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_organizer_can_access_recurring_page(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('event_add_recurring', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_access_recurring_page(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('event_add_recurring', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 403)

    def test_site_admin_who_is_organizer_can_access_recurring_page(self):
        _make_group_admin(self.site_admin, self.group)
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('event_add_recurring', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 200)

    def test_preview_page_requires_login(self):
        response = self.client.get(reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_regular_user_cannot_access_preview_page(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 403)


@tag("integration")
class RecurringEventFormValidationTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_site_admin=True
        )
        cls.group = Group.objects.create(name='Validation Group')
        _make_group_admin(cls.organizer, cls.group)

    def setUp(self):
        self.client.login(username='organizer', password='testpass123')

    def test_start_date_in_past_fails(self):
        past = (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add_recurring', kwargs={'slug': self.group.slug}), {
            'title': 'Past Recurring',
            'start_date': past,
            'end_type': 'count',
            'occurrence_count': '3',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Past Recurring').exists())

    def test_occurrence_count_below_minimum_fails(self):
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add_recurring', kwargs={'slug': self.group.slug}), {
            'title': 'Too Few',
            'start_date': future,
            'end_type': 'count',
            'occurrence_count': '1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Too Few').exists())

    def test_occurrence_count_above_maximum_fails(self):
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add_recurring', kwargs={'slug': self.group.slug}), {
            'title': 'Too Many',
            'start_date': future,
            'end_type': 'count',
            'occurrence_count': '53',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Too Many').exists())

    def test_end_date_before_start_date_fails(self):
        start = (timezone.now() + timedelta(days=14)).strftime('%Y-%m-%d')
        end = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add_recurring', kwargs={'slug': self.group.slug}), {
            'title': 'Bad Range',
            'start_date': start,
            'end_type': 'end_date',
            'end_date': end,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Bad Range').exists())

    def test_end_date_in_past_fails(self):
        future = (timezone.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        past = (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add_recurring', kwargs={'slug': self.group.slug}), {
            'title': 'Past End',
            'start_date': future,
            'end_type': 'end_date',
            'end_date': past,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Past End').exists())

    def test_missing_title_fails(self):
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add_recurring', kwargs={'slug': self.group.slug}), {
            'title': '',
            'start_date': future,
            'end_type': 'count',
            'occurrence_count': '3',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.exists())

    def test_missing_start_date_fails(self):
        response = self.client.post(reverse('event_add_recurring', kwargs={'slug': self.group.slug}), {
            'title': 'No Date',
            'start_date': '',
            'end_type': 'count',
            'occurrence_count': '3',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.exists())

    def test_valid_count_redirects_to_preview(self):
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add_recurring', kwargs={'slug': self.group.slug}), {
            'title': 'Weekly Game Night',
            'start_date': future,
            'time': '18:00',
            'location': 'The Den',
            'description': 'Weekly meetup',
            'end_type': 'count',
            'occurrence_count': '4',
            'voting_deadline_offset_minutes': '60',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}))

    def test_valid_end_date_redirects_to_preview(self):
        start = (timezone.now() + timedelta(days=3)).strftime('%Y-%m-%d')
        end = (timezone.now() + timedelta(days=24)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add_recurring', kwargs={'slug': self.group.slug}), {
            'title': 'Weekly Game Night',
            'start_date': start,
            'end_type': 'end_date',
            'end_date': end,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('event_add_recurring_preview', kwargs={'slug': self.group.slug}))


@tag("integration")
class RecurringEventButtonTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_site_admin=True
        )
        cls.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )
        cls.group = Group.objects.create(name='Button Group')
        _make_group_admin(cls.organizer, cls.group)

    def test_organizer_sees_recurring_event_button(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('group_event_list', kwargs={'slug': self.group.slug}))
        self.assertContains(response, reverse('event_add_recurring', kwargs={'slug': self.group.slug}))
        self.assertContains(response, 'Create Recurring Event')

    def test_regular_user_does_not_see_recurring_event_button(self):
        GroupMembership.objects.create(user=self.regular, group=self.group, role='member')
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('group_event_list', kwargs={'slug': self.group.slug}))
        self.assertNotContains(response, 'Create Recurring Event')


@tag("integration")
class GroupEventListUnauthenticatedTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='admin', password='testpass123', is_site_admin=True
        )
        cls.group = Group.objects.create(name='Public Events Group')
        _make_group_admin(cls.admin, cls.group)

    def test_unauthenticated_gets_403_on_group_event_list(self):
        response = self.client.get(reverse('group_event_list', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 403)


@tag("integration")
class EventCreationNotificationTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_site_admin=True
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.group = Group.objects.create(name='Notif Group')
        _make_group_admin(cls.organizer, cls.group)
        GroupMembership.objects.create(user=cls.member, group=cls.group, role='member')

    def test_create_event_sends_notification_to_members(self):
        self.client.login(username='organizer', password='testpass123')
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Notif Event',
            'date': future,
            'time': '18:00',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Notification.objects.filter(
            user=self.member,
            notification_type='group_event_created',
        ).exists())
        notif = Notification.objects.get(user=self.member, notification_type='group_event_created')
        self.assertIn('Notif Event', notif.message)

    def test_create_event_does_not_notify_creator(self):
        self.client.login(username='organizer', password='testpass123')
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Notif Event',
            'date': future,
            'time': '18:00',
        })
        self.assertFalse(Notification.objects.filter(
            user=self.organizer,
            notification_type='group_event_created',
        ).exists())

    def test_edit_event_sends_notification_to_members(self):
        event = Event.objects.create(
            title='Original',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
        )
        self.client.login(username='organizer', password='testpass123')
        future = (timezone.now() + timedelta(days=14)).strftime('%Y-%m-%d')
        self.client.post(reverse('event_edit', kwargs={'slug': event.group.slug, 'pk': event.pk}), {
            'title': 'Updated',
            'date': future,
            'time': '',
            'location': '',
            'description': '',
        })
        self.assertTrue(Notification.objects.filter(
            user=self.member,
            notification_type='group_event_updated',
        ).exists())


@tag("integration")
class PrivateEventCreateViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='alice', password='testpass123', email_verified=True,
        )

    def test_create_private_event_success(self):
        self.client.login(username='alice', password='testpass123')
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        resp = self.client.post(reverse('private_event_create'), {
            'title': 'Game Night',
            'date': future,
            'description': 'Fun times',
            'location': 'My house',
            'privacy': 'public',
            'allow_invite_others': 'nobody',
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
        self.user.email_verified = False
        self.user.save()
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(reverse('private_event_create'))
        self.assertEqual(resp.status_code, 403)

    def test_requires_login(self):
        resp = self.client.get(reverse('private_event_create'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_rate_limited(self):
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

    def test_unverified_user_blocked_on_post(self):
        self.user.email_verified = False
        self.user.save()
        self.client.login(username='alice', password='testpass123')
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        resp = self.client.post(reverse('private_event_create'), {
            'title': 'Sneaky Event',
            'date': future,
            'privacy': 'public',
            'allow_invite_others': 'nobody',
        })
        self.assertEqual(resp.status_code, 403)


@tag("integration")
class PrivateEventCreateButtonTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.verified_user = User.objects.create_user(
            username='verified', password='testpass123', email_verified=True,
        )
        cls.unverified_user = User.objects.create_user(
            username='unverified', password='testpass123', email_verified=False,
        )

    def test_event_list_shows_create_button_for_verified_user(self):
        self.client.login(username='verified', password='testpass123')
        resp = self.client.get(reverse('event_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse('private_event_create'))
        self.assertContains(resp, 'Create Event')

    def test_event_list_hides_create_button_for_unverified_user(self):
        self.client.login(username='unverified', password='testpass123')
        resp = self.client.get(reverse('event_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, reverse('private_event_create'))

    def test_event_list_hides_create_button_for_unauthenticated(self):
        resp = self.client.get(reverse('event_list'))
        self.assertNotContains(resp, reverse('private_event_create'))

    def test_discover_events_shows_create_button_for_verified_user(self):
        self.client.login(username='verified', password='testpass123')
        resp = self.client.get(reverse('discover_events'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse('private_event_create'))

    def test_discover_events_hides_create_button_for_unverified_user(self):
        self.client.login(username='unverified', password='testpass123')
        resp = self.client.get(reverse('discover_events'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, reverse('private_event_create'))

    def test_discover_events_hides_create_button_for_unauthenticated(self):
        resp = self.client.get(reverse('discover_events'))
        self.assertNotContains(resp, reverse('private_event_create'))


@tag("integration")
class PrivateEventDetailViewTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='testpass123')
        self.bob = User.objects.create_user(username='bob', password='testpass123')
        self.group = Group.objects.create(name='Test Group')
        GroupMembership.objects.create(user=self.alice, group=self.group, role='admin')

    def test_group_event_redirects(self):
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


@tag("integration")
class PrivateEventRsvpViewTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='testpass123')
        self.bob = User.objects.create_user(username='bob', password='testpass123')

    def test_rsvp_public_event(self):
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
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(reverse('event_invite', kwargs={'pk': self.event.pk}), {
            'user_ids': str(self.bob.pk),
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            EventInvite.objects.filter(event=self.event, user=self.bob).exists()
        )

    def test_non_organizer_cannot_invite(self):
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(reverse('event_invite', kwargs={'pk': self.event.pk}), {
            'user_ids': str(self.alice.pk),
        })
        self.assertEqual(resp.status_code, 403)

    def test_accept_invite(self):
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
        carol = User.objects.create_user(username='carol', password='testpass123')
        invite = EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        self.client.login(username='carol', password='testpass123')
        resp = self.client.post(
            reverse('event_invite_respond', kwargs={'pk': self.event.pk, 'invite_pk': invite.pk, 'status': 'accept'}),
        )
        self.assertEqual(resp.status_code, 403)


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


@tag("integration")
class EventCreateViewDurationTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123'
        )
        self.group = Group.objects.create(name='Duration Create Group')
        _make_group_admin(self.admin, self.group)

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
        _make_group_admin(self.admin, self.group)
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
        _make_group_admin(self.organizer, self.group)
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


@tag("integration")
class PlayGameViewTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(username='organizer', password='testpass123')
        self.member = User.objects.create_user(username='member', password='testpass123')
        self.group = Group.objects.create(name='Play Group')
        from club.models import GroupMembership
        GroupMembership.objects.create(user=self.organizer, group=self.group, role='admin')
        GroupMembership.objects.create(user=self.member, group=self.group, role='member')
        self.event = Event.objects.create(
            title='Play Event',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=self.organizer, group=self.group,
        )
        EventAttendance.objects.create(user=self.member, event=self.event)
        self.game = BoardGame.objects.create(name='Catan', owner=self.organizer)

    def test_organizer_can_view_play_form(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('event_play_game', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)

    def test_member_cannot_view_play_form(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('event_play_game', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 403)

    def test_organizer_can_record_session(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('event_play_game', kwargs={'pk': self.event.pk}), {
            'board_game': self.game.pk, 'selection_method': 'manual',
            'players': str(self.member.pk), 'guest_names': '',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(GameSession.objects.filter(event=self.event, board_game=self.game).exists())

    def test_organizer_can_record_session_with_guest(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('event_play_game', kwargs={'pk': self.event.pk}), {
            'board_game': self.game.pk, 'selection_method': 'manual',
            'players': '', 'guest_names': 'Guest1,Guest2',
        })
        self.assertEqual(response.status_code, 302)
        session = GameSession.objects.get(event=self.event)
        self.assertEqual(GameSessionPlayer.objects.filter(game_session=session).exclude(guest_name='').count(), 2)

    def test_unauthenticated_redirected(self):
        response = self.client.get(reverse('event_play_game', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)


@tag("integration")
class GameSessionDetailViewTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(username='organizer', password='testpass123')
        self.member = User.objects.create_user(username='member', password='testpass123')
        self.group = Group.objects.create(name='Detail Group', discoverable=False)
        from club.models import GroupMembership
        GroupMembership.objects.create(user=self.organizer, group=self.group, role='admin')
        GroupMembership.objects.create(user=self.member, group=self.group, role='member')
        self.event = Event.objects.create(
            title='Detail Event',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=self.organizer, group=self.group,
        )
        EventAttendance.objects.create(user=self.member, event=self.event)
        self.game = BoardGame.objects.create(name='Catan', owner=self.organizer)
        self.session = GameSession.objects.create(
            event=self.event, board_game=self.game,
            selection_method='manual', created_by=self.organizer,
        )
        GameSessionPlayer.objects.create(game_session=self.session, user=self.member)

    def test_authenticated_user_can_view_session(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('game_session_detail', kwargs={'event_pk': self.event.pk, 'pk': self.session.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Catan')

    def test_non_member_blocked_from_group_session(self):
        outsider = User.objects.create_user(username='outsider', password='pass')
        self.client.login(username='outsider', password='pass')
        response = self.client.get(reverse('game_session_detail', kwargs={'event_pk': self.event.pk, 'pk': self.session.pk}))
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_redirected(self):
        response = self.client.get(reverse('game_session_detail', kwargs={'event_pk': self.event.pk, 'pk': self.session.pk}))
        self.assertEqual(response.status_code, 302)


@tag("integration")
class GameSessionDetailPrivateEventTest(TestCase):

    def setUp(self):
        self.creator = User.objects.create_user(username='creator', password='testpass123')
        self.attendee = User.objects.create_user(username='attendee', password='testpass123')
        self.stranger = User.objects.create_user(username='stranger', password='testpass123')
        self.event = Event.objects.create(
            title='Private Event',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=self.creator, privacy='private',
        )
        EventAttendance.objects.create(user=self.attendee, event=self.event)
        self.game = BoardGame.objects.create(name='Wingspan', owner=self.creator)
        self.session = GameSession.objects.create(
            event=self.event, board_game=self.game,
            selection_method='manual', created_by=self.creator,
        )

    def test_creator_can_view_private_session(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.get(reverse('game_session_detail', kwargs={'event_pk': self.event.pk, 'pk': self.session.pk}))
        self.assertEqual(response.status_code, 200)

    def test_attendee_can_view_private_session(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(reverse('game_session_detail', kwargs={'event_pk': self.event.pk, 'pk': self.session.pk}))
        self.assertEqual(response.status_code, 200)

    def test_stranger_blocked_from_private_session(self):
        self.client.login(username='stranger', password='testpass123')
        response = self.client.get(reverse('game_session_detail', kwargs={'event_pk': self.event.pk, 'pk': self.session.pk}))
        self.assertEqual(response.status_code, 403)


@tag("integration")
class GameSessionDeleteTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(username='organizer', password='testpass123')
        self.member = User.objects.create_user(username='member', password='testpass123')
        self.group = Group.objects.create(name='Delete Group')
        from club.models import GroupMembership
        GroupMembership.objects.create(user=self.organizer, group=self.group, role='admin')
        GroupMembership.objects.create(user=self.member, group=self.group, role='member')
        self.event = Event.objects.create(
            title='Delete Event',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=self.organizer, group=self.group,
        )
        self.game = BoardGame.objects.create(name='Catan', owner=self.organizer)
        self.session = GameSession.objects.create(
            event=self.event, board_game=self.game,
            selection_method='manual', created_by=self.organizer,
        )

    def test_organizer_can_delete_session(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('game_session_delete', kwargs={'event_pk': self.event.pk, 'pk': self.session.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(GameSession.objects.filter(pk=self.session.pk).exists())

    def test_member_cannot_delete_session(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.post(reverse('game_session_delete', kwargs={'event_pk': self.event.pk, 'pk': self.session.pk}))
        self.assertEqual(response.status_code, 403)

    def test_delete_shows_confirmation_on_get(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('game_session_delete', kwargs={'event_pk': self.event.pk, 'pk': self.session.pk}))
        self.assertEqual(response.status_code, 200)


@tag("integration")
class DiscoverEventsViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.creator = User.objects.create_user(username='creator', password='testpass123')
        cls.public_event = Event.objects.create(
            title='Public Game Night',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            location='Community Center',
            description='Everyone welcome!',
            created_by=cls.creator,
            privacy='public',
        )
        cls.invite_public_event = Event.objects.create(
            title='Invite Only Public Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            location='Private Venue',
            description='See details if invited',
            created_by=cls.creator,
            privacy='invite_only_public',
        )
        cls.private_event = Event.objects.create(
            title='Secret Meeting',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=cls.creator,
            privacy='private',
        )
        cls.group = Group.objects.create(name='Some Group')
        cls.group_event = Event.objects.create(
            title='Group Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=cls.creator,
            group=cls.group,
            privacy='public',
        )
        past_date = timezone.now() - timedelta(days=1)
        cls.past_event = Event.objects.create(
            title='Past Public Event',
            date=past_date,
            voting_deadline=past_date,
            duration_minutes=60,
            created_by=cls.creator,
            privacy='public',
        )

    def test_discover_page_shows_public_non_group_events(self):
        response = self.client.get(reverse('discover_events'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Public Game Night')

    def test_discover_page_shows_invite_only_public_events(self):
        response = self.client.get(reverse('discover_events'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invite Only Public Event')

    def test_discover_page_hides_private_events(self):
        response = self.client.get(reverse('discover_events'))
        self.assertNotContains(response, 'Secret Meeting')

    def test_discover_page_hides_group_events(self):
        response = self.client.get(reverse('discover_events'))
        self.assertNotContains(response, 'Group Event')

    def test_discover_page_hides_past_events(self):
        response = self.client.get(reverse('discover_events'))
        self.assertNotContains(response, 'Past Public Event')

    def test_discover_page_accessible_unauthenticated(self):
        response = self.client.get(reverse('discover_events'))
        self.assertEqual(response.status_code, 200)

    def test_discover_page_accessible_authenticated(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.get(reverse('discover_events'))
        self.assertEqual(response.status_code, 200)

    def test_discover_page_empty_when_no_events(self):
        Event.objects.filter(group__isnull=True).delete()
        response = self.client.get(reverse('discover_events'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No upcoming public events')

    def test_discover_page_shows_location_when_public(self):
        response = self.client.get(reverse('discover_events'))
        self.assertContains(response, 'Community Center')

    def test_discover_page_hides_location_when_flag_false(self):
        event = Event.objects.create(
            title='Hidden Location Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            location='Secret Spot',
            created_by=self.creator,
            privacy='invite_only_public',
            show_location_publicly=False,
        )
        response = self.client.get(reverse('discover_events'))
        self.assertContains(response, 'Hidden Location Event')
        self.assertNotContains(response, 'Secret Spot')

    def test_discover_page_hides_description_when_flag_false(self):
        Event.objects.create(
            title='Hidden Desc Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            description='Super secret description',
            created_by=self.creator,
            privacy='invite_only_public',
            show_description_publicly=False,
        )
        response = self.client.get(reverse('discover_events'))
        self.assertContains(response, 'Hidden Desc Event')
        self.assertNotContains(response, 'Super secret description')


@tag("integration")
class DiscoverEventsFilterTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.creator = User.objects.create_user(username='creator', password='testpass123')
        cls.tag_board = EventTag.objects.create(name='boardgames')
        cls.tag_card = EventTag.objects.create(name='cardgames')
        cls.event_tagged = Event.objects.create(
            title='Tagged Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=cls.creator,
            privacy='public',
        )
        cls.event_tagged.tags.add(cls.tag_board)
        cls.event_untagged = Event.objects.create(
            title='Untagged Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=cls.creator,
            privacy='public',
        )
        cls.event_card = Event.objects.create(
            title='Card Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=cls.creator,
            privacy='public',
        )
        cls.event_card.tags.add(cls.tag_card)

    def test_filter_by_tag(self):
        response = self.client.get(reverse('discover_events'), {'tag': ['boardgames']})
        self.assertContains(response, 'Tagged Event')
        self.assertNotContains(response, 'Untagged Event')
        self.assertNotContains(response, 'Card Event')

    def test_filter_no_tags(self):
        response = self.client.get(reverse('discover_events'), {'tag': ['__none__']})
        self.assertContains(response, 'Untagged Event')
        self.assertNotContains(response, 'Tagged Event')
        self.assertNotContains(response, 'Card Event')

    def test_filter_multiple_tags(self):
        response = self.client.get(reverse('discover_events'), {'tag': ['boardgames', 'cardgames']})
        self.assertContains(response, 'Tagged Event')
        self.assertContains(response, 'Card Event')
        self.assertNotContains(response, 'Untagged Event')

    def test_date_from_filter(self):
        future_plus = timezone.now() + timedelta(days=60)
        Event.objects.create(
            title='Far Future Event',
            date=future_plus,
            voting_deadline=future_plus,
            created_by=self.creator,
            privacy='public',
        )
        response = self.client.get(reverse('discover_events'), {
            'date_from': (timezone.now() + timedelta(days=45)).strftime('%Y-%m-%d'),
        })
        self.assertContains(response, 'Far Future Event')
        self.assertNotContains(response, 'Tagged Event')

    def test_date_to_filter(self):
        near_future = timezone.now() + timedelta(days=2)
        Event.objects.create(
            title='Near Event',
            date=near_future,
            voting_deadline=near_future,
            created_by=self.creator,
            privacy='public',
        )
        response = self.client.get(reverse('discover_events'), {
            'date_to': (timezone.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
        })
        self.assertNotContains(response, 'Near Event')
        self.assertNotContains(response, 'Tagged Event')

    def test_date_range_filter(self):
        near_future = timezone.now() + timedelta(days=2)
        Event.objects.create(
            title='Range Event',
            date=near_future,
            voting_deadline=near_future,
            created_by=self.creator,
            privacy='public',
        )
        response = self.client.get(reverse('discover_events'), {
            'date_from': (timezone.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
            'date_to': (timezone.now() + timedelta(days=3)).strftime('%Y-%m-%d'),
        })
        self.assertContains(response, 'Range Event')
        self.assertNotContains(response, 'Tagged Event')

    def test_sort_ascending_default(self):
        early = timezone.now() + timedelta(days=5)
        late = timezone.now() + timedelta(days=15)
        Event.objects.create(title='Late Event', date=late, voting_deadline=late, created_by=self.creator, privacy='public')
        Event.objects.create(title='Early Event', date=early, voting_deadline=early, created_by=self.creator, privacy='public')
        response = self.client.get(reverse('discover_events'))
        content = response.content.decode()
        self.assertLess(content.index('Early Event'), content.index('Late Event'))

    def test_sort_descending(self):
        early = timezone.now() + timedelta(days=5)
        late = timezone.now() + timedelta(days=15)
        Event.objects.create(title='Late Event', date=late, voting_deadline=late, created_by=self.creator, privacy='public')
        Event.objects.create(title='Early Event', date=early, voting_deadline=early, created_by=self.creator, privacy='public')
        response = self.client.get(reverse('discover_events'), {'sort': 'desc'})
        content = response.content.decode()
        self.assertLess(content.index('Late Event'), content.index('Early Event'))

    def test_clear_filters_shows_all(self):
        response = self.client.get(reverse('discover_events'))
        self.assertContains(response, 'Tagged Event')
        self.assertContains(response, 'Untagged Event')
        self.assertContains(response, 'Card Event')


@tag("integration")
class EventListRedesignTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='member', password='testpass123')
        cls.group = Group.objects.create(name='My Group')
        _make_member(cls.user, cls.group)
        cls.group_event = Event.objects.create(
            title='Group Game Night',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            location='Clubhouse',
            created_by=cls.user,
            group=cls.group,
        )
        cls.creator = User.objects.create_user(username='privcreator', password='testpass123')
        cls.rsvp_event = Event.objects.create(
            title='My Private Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=cls.creator,
            privacy='public',
        )
        EventAttendance.objects.create(user=cls.user, event=cls.rsvp_event)
        cls.non_rsvp_event = Event.objects.create(
            title='Other Private Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=cls.creator,
            privacy='public',
        )

    def test_authenticated_sees_group_events_card(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Group Game Night')

    def test_authenticated_sees_rsvp_non_group_events(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, 'My Private Event')

    def test_authenticated_does_not_see_non_rsvp_non_group_events(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertNotContains(response, 'Other Private Event')

    def test_has_discover_events_link(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, reverse('discover_events'))

    def test_unauthenticated_sees_discoverable_group_events(self):
        response = self.client.get(reverse('event_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Group Game Night')

    def test_unauthenticated_sees_discover_link(self):
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, reverse('discover_events'))

    def test_no_rsvp_events_shows_empty_or_hides_card(self):
        user2 = User.objects.create_user(username='loner', password='testpass123')
        self.client.login(username='loner', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertEqual(response.status_code, 200)


@tag("integration")
class PrivateEventCoCreatorCreateTest(TestCase):

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
        self.dave = User.objects.create_user(
            username='dave', password='testpass123', email_verified=True,
        )
        Friendship.objects.create(
            requester=self.alice, receiver=self.bob, status='accepted',
        )
        Friendship.objects.create(
            requester=self.alice, receiver=self.carol, status='accepted',
        )
        Friendship.objects.create(
            requester=self.alice, receiver=self.dave, status='accepted',
        )

    def _post_data(self, **overrides):
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        data = {
            'title': 'Co-Created Event',
            'date': future,
            'privacy': 'public',
            'allow_invite_others': 'nobody',
            'co_creator_ids': '',
            'duration_minutes': 120,
        }
        data.update(overrides)
        return data

    def test_create_with_co_creators_success(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(
            reverse('private_event_create'),
            self._post_data(co_creator_ids=f'{self.bob.pk},{self.carol.pk}'),
        )
        self.assertEqual(resp.status_code, 302)
        event = Event.objects.get(title='Co-Created Event')
        self.assertTrue(event.co_creators.filter(pk=self.bob.pk).exists())
        self.assertTrue(event.co_creators.filter(pk=self.carol.pk).exists())

    def test_co_creators_auto_rsvpd(self):
        self.client.login(username='alice', password='testpass123')
        self.client.post(
            reverse('private_event_create'),
            self._post_data(co_creator_ids=f'{self.bob.pk},{self.carol.pk}'),
        )
        event = Event.objects.get(title='Co-Created Event')
        self.assertTrue(
            EventAttendance.objects.filter(user=self.bob, event=event).exists()
        )
        self.assertTrue(
            EventAttendance.objects.filter(user=self.carol, event=event).exists()
        )

    def test_co_creators_receive_notification(self):
        self.client.login(username='alice', password='testpass123')
        self.client.post(
            reverse('private_event_create'),
            self._post_data(co_creator_ids=str(self.bob.pk)),
        )
        event = Event.objects.get(title='Co-Created Event')
        self.assertTrue(
            Notification.objects.filter(
                user=self.bob,
                notification_type='event_co_creator',
                url=f'/events/{event.pk}/',
            ).exists()
        )

    def test_create_with_non_friend_co_creator_rejected(self):
        self.client.login(username='alice', password='testpass123')
        stranger = User.objects.create_user(
            username='stranger', password='testpass123', email_verified=True,
        )
        resp = self.client.post(
            reverse('private_event_create'),
            self._post_data(co_creator_ids=str(stranger.pk)),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Co-Created Event').exists())

    def test_create_exceeding_max_co_creators_rejected(self):
        extra = User.objects.create_user(
            username='extra', password='testpass123', email_verified=True,
        )
        Friendship.objects.create(
            requester=self.alice, receiver=extra, status='accepted',
        )
        self.client.login(username='alice', password='testpass123')
        ids = f'{self.bob.pk},{self.carol.pk},{self.dave.pk},{extra.pk}'
        resp = self.client.post(
            reverse('private_event_create'),
            self._post_data(co_creator_ids=ids),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Co-Created Event').exists())

    def test_create_without_co_creators_still_works(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(
            reverse('private_event_create'),
            self._post_data(co_creator_ids=''),
        )
        self.assertEqual(resp.status_code, 302)
        event = Event.objects.get(title='Co-Created Event')
        self.assertEqual(event.co_creators.count(), 0)

    def test_creation_log_created_for_creator(self):
        self.client.login(username='alice', password='testpass123')
        self.client.post(
            reverse('private_event_create'),
            self._post_data(co_creator_ids=str(self.bob.pk)),
        )
        event = Event.objects.get(title='Co-Created Event')
        self.assertTrue(
            PrivateEventCreationLog.objects.filter(
                user=self.alice, event=event,
            ).exists()
        )


@tag("integration")
class CoCreatorPermissionTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(
            username='alice', password='testpass123', email_verified=True,
        )
        self.bob = User.objects.create_user(
            username='bob', password='testpass123', email_verified=True,
        )
        Friendship.objects.create(
            requester=self.alice, receiver=self.bob, status='accepted',
        )
        future = timezone.now() + timedelta(days=7)
        self.event = Event.objects.create(
            title='Co-Created Event',
            date=future,
            voting_deadline=future,
            created_by=self.alice,
            privacy='public',
        )
        self.event.co_creators.add(self.bob)
        EventAttendance.objects.create(user=self.bob, event=self.event)

    def test_co_creator_can_edit_event(self):
        self.client.login(username='bob', password='testpass123')
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        resp = self.client.post(
            reverse('private_event_edit', kwargs={'pk': self.event.pk}),
            {
                'title': 'Updated by Co-Creator',
                'date': future,
                'privacy': 'public',
                'allow_invite_others': 'nobody',
                'duration_minutes': 120,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, 'Updated by Co-Creator')

    def test_co_creator_can_access_settings(self):
        self.client.login(username='bob', password='testpass123')
        resp = self.client.get(
            reverse('event_settings', kwargs={'pk': self.event.pk}),
        )
        self.assertEqual(resp.status_code, 200)

    def test_co_creator_can_toggle_voting(self):
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(
            reverse('private_event_toggle_voting', kwargs={'pk': self.event.pk}),
        )
        self.assertEqual(resp.status_code, 302)
        self.event.refresh_from_db()
        self.assertFalse(self.event.voting_open)

    def test_co_creator_can_toggle_visibility(self):
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(
            reverse('private_event_toggle_visibility', kwargs={'pk': self.event.pk}),
        )
        self.assertEqual(resp.status_code, 302)
        self.event.refresh_from_db()
        self.assertTrue(self.event.show_individual_votes)

    def test_co_creator_can_view_results(self):
        self.client.login(username='bob', password='testpass123')
        resp = self.client.get(
            reverse('private_event_results', kwargs={'pk': self.event.pk}),
        )
        self.assertEqual(resp.status_code, 200)

    def test_co_creator_can_invite(self):
        carol = User.objects.create_user(
            username='carol', password='testpass123', email_verified=True,
        )
        Friendship.objects.create(
            requester=self.bob, receiver=carol, status='accepted',
        )
        self.event.allow_invite_others = 'friends_only'
        self.event.save()
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(
            reverse('event_invite', kwargs={'pk': self.event.pk}),
            {'user_ids': str(carol.pk)},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            EventInvite.objects.filter(event=self.event, user=carol).exists()
        )

    def test_co_creator_can_rsvp_private_event(self):
        event = Event.objects.create(
            title='Private Co Event',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=6),
            created_by=self.alice,
            privacy='private',
        )
        event.co_creators.add(self.bob)
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(
            reverse('private_event_rsvp', kwargs={'pk': event.pk}),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            EventAttendance.objects.filter(user=self.bob, event=event).exists()
        )

    def test_co_creator_can_view_private_event(self):
        event = Event.objects.create(
            title='Private Co Event',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=6),
            created_by=self.alice,
            privacy='private',
        )
        event.co_creators.add(self.bob)
        self.client.login(username='bob', password='testpass123')
        resp = self.client.get(
            reverse('private_event_detail', kwargs={'pk': event.pk}),
        )
        self.assertEqual(resp.status_code, 200)


@tag("integration")
class CoCreatorNotModifiableAfterCreationTest(TestCase):

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
        future = timezone.now() + timedelta(days=7)
        self.event = Event.objects.create(
            title='Co-Created',
            date=future,
            voting_deadline=future,
            created_by=self.alice,
            privacy='public',
        )
        self.event.co_creators.add(self.bob)
        EventAttendance.objects.create(user=self.bob, event=self.event)

    def test_edit_form_does_not_include_co_creator_field(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(
            reverse('private_event_edit', kwargs={'pk': self.event.pk}),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('co_creator_ids', resp.context['form'].fields)

    def test_settings_form_does_not_modify_co_creators(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(
            reverse('event_settings', kwargs={'pk': self.event.pk}),
            {
                'privacy': 'public',
                'show_description_publicly': True,
                'show_location_publicly': True,
                'show_datetime_publicly': True,
                'show_attendees_publicly': True,
                'allow_invite_others': 'nobody',
                'organizers_can_edit_title': True,
                'organizers_can_edit_description': True,
                'organizers_can_edit_datetime': True,
                'additional_organizer_ids': '',
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.co_creators.count(), 1)
        self.assertTrue(self.event.co_creators.filter(pk=self.bob.pk).exists())


@tag("integration")
class QuickAddGameDuringEventTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(username='organizer', password='testpass123')
        self.attendee = User.objects.create_user(username='attendee', password='testpass123')
        self.group = Group.objects.create(name='Play Group')
        GroupMembership.objects.create(user=self.organizer, group=self.group, role='admin')
        GroupMembership.objects.create(user=self.attendee, group=self.group, role='member')
        event_date = timezone.now() - timedelta(minutes=30)
        self.event = Event.objects.create(
            title='Ongoing Event',
            date=event_date,
            voting_deadline=event_date,
            created_by=self.organizer,
            group=self.group,
            duration_minutes=120,
        )
        EventAttendance.objects.create(user=self.attendee, event=self.event)

    def test_organizer_can_quick_add_game_by_name(self):
        self.client.login(username='organizer', password='testpass123')
        resp = self.client.post(reverse('event_play_game', kwargs={'pk': self.event.pk}), {
            'ad_hoc_game_name': 'Monopoly',
            'selection_method': 'manual',
            'players': str(self.attendee.pk),
        })
        self.assertEqual(resp.status_code, 302)
        game = BoardGame.objects.get(name='Monopoly')
        self.assertTrue(game.is_temporary)
        self.assertIsNone(game.owner)
        self.assertIsNone(game.group)
        self.assertTrue(GameSession.objects.filter(event=self.event, board_game=game).exists())

    def test_quick_add_creates_temporary_game(self):
        self.client.login(username='organizer', password='testpass123')
        self.client.post(reverse('event_play_game', kwargs={'pk': self.event.pk}), {
            'ad_hoc_game_name': 'Quick Game',
            'selection_method': 'manual',
        })
        game = BoardGame.objects.get(name='Quick Game')
        self.assertTrue(game.is_temporary)
        self.assertFalse(hasattr(game, 'owner') and game.owner is not None)

    def test_quick_add_ignored_when_board_game_selected(self):
        existing_game = BoardGame.objects.create(name='Catan', owner=self.organizer)
        self.client.login(username='organizer', password='testpass123')
        self.client.post(reverse('event_play_game', kwargs={'pk': self.event.pk}), {
            'board_game': existing_game.pk,
            'ad_hoc_game_name': 'Should Be Ignored',
            'selection_method': 'manual',
        })
        self.assertFalse(BoardGame.objects.filter(name='Should Be Ignored').exists())
        session = GameSession.objects.get(event=self.event)
        self.assertEqual(session.board_game, existing_game)
        self.assertFalse(session.board_game.is_temporary)

    def test_non_organizer_cannot_quick_add(self):
        self.client.login(username='attendee', password='testpass123')
        resp = self.client.post(reverse('event_play_game', kwargs={'pk': self.event.pk}), {
            'ad_hoc_game_name': 'Blocked Game',
            'selection_method': 'manual',
        })
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(BoardGame.objects.filter(name='Blocked Game').exists())

    def test_quick_add_redirects_to_group_event(self):
        self.client.login(username='organizer', password='testpass123')
        resp = self.client.post(reverse('event_play_game', kwargs={'pk': self.event.pk}), {
            'ad_hoc_game_name': 'Monopoly',
            'selection_method': 'manual',
        })
        self.assertRedirects(resp, reverse('event_detail', kwargs={'slug': self.group.slug, 'pk': self.event.pk}))

    def test_quick_add_with_guests(self):
        self.client.login(username='organizer', password='testpass123')
        self.client.post(reverse('event_play_game', kwargs={'pk': self.event.pk}), {
            'ad_hoc_game_name': 'Party Game',
            'selection_method': 'manual',
            'guest_names': 'Guest1,Guest2',
        })
        session = GameSession.objects.get(event=self.event)
        self.assertEqual(
            GameSessionPlayer.objects.filter(game_session=session).count(), 2,
        )

    def test_quick_add_private_event(self):
        creator = User.objects.create_user(username='privcreator', password='testpass123')
        event_date = timezone.now() - timedelta(minutes=30)
        private_event = Event.objects.create(
            title='Private Ongoing',
            date=event_date,
            voting_deadline=event_date,
            created_by=creator,
            duration_minutes=120,
        )
        self.client.login(username='privcreator', password='testpass123')
        resp = self.client.post(reverse('event_play_game', kwargs={'pk': private_event.pk}), {
            'ad_hoc_game_name': 'Private Game',
            'selection_method': 'manual',
        })
        self.assertRedirects(resp, reverse('private_event_detail', kwargs={'pk': private_event.pk}))
        self.assertTrue(BoardGame.objects.filter(name='Private Game', is_temporary=True).exists())


@tag("integration")
class EventSummaryViewTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(username='organizer', password='testpass123')
        self.member = User.objects.create_user(username='member', password='testpass123')
        self.group = Group.objects.create(name='Summary Group')
        GroupMembership.objects.create(user=self.organizer, group=self.group, role='admin')
        GroupMembership.objects.create(user=self.member, group=self.group, role='member')
        event_date = timezone.now() - timedelta(hours=3)
        self.event = Event.objects.create(
            title='Completed Event',
            date=event_date,
            voting_deadline=event_date,
            created_by=self.organizer,
            group=self.group,
            duration_minutes=60,
        )
        EventAttendance.objects.create(user=self.member, event=self.event)

    def test_organizer_can_view_summary(self):
        self.client.login(username='organizer', password='testpass123')
        resp = self.client.get(reverse('event_summary', kwargs={'pk': self.event.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_group_admin_can_view_summary(self):
        admin = User.objects.create_user(username='admin2', password='testpass123')
        GroupMembership.objects.create(user=admin, group=self.group, role='admin')
        self.client.login(username='admin2', password='testpass123')
        resp = self.client.get(reverse('event_summary', kwargs={'pk': self.event.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_member_cannot_view_summary(self):
        self.client.login(username='member', password='testpass123')
        resp = self.client.get(reverse('event_summary', kwargs={'pk': self.event.pk}))
        self.assertEqual(resp.status_code, 403)

    def test_summary_shows_temporary_games(self):
        temp_game = BoardGame.objects.create(name='Temp Catan', is_temporary=True)
        GameSession.objects.create(
            event=self.event, board_game=temp_game,
            selection_method='manual', created_by=self.organizer,
        )
        self.client.login(username='organizer', password='testpass123')
        resp = self.client.get(reverse('event_summary', kwargs={'pk': self.event.pk}))
        self.assertContains(resp, 'Temp Catan')
        self.assertContains(resp, 'Add to Library')

    def test_summary_shows_owned_games(self):
        owned_game = BoardGame.objects.create(name='Owned Catan', owner=self.organizer)
        GameSession.objects.create(
            event=self.event, board_game=owned_game,
            selection_method='manual', created_by=self.organizer,
        )
        self.client.login(username='organizer', password='testpass123')
        resp = self.client.get(reverse('event_summary', kwargs={'pk': self.event.pk}))
        self.assertContains(resp, 'Owned Catan')
        self.assertNotContains(resp, 'Add to Library')

    def test_summary_not_available_for_ongoing_event(self):
        event_date = timezone.now() - timedelta(minutes=30)
        ongoing = Event.objects.create(
            title='Ongoing',
            date=event_date,
            voting_deadline=event_date,
            created_by=self.organizer,
            group=self.group,
            duration_minutes=120,
        )
        self.client.login(username='organizer', password='testpass123')
        resp = self.client.get(reverse('event_summary', kwargs={'pk': ongoing.pk}))
        self.assertEqual(resp.status_code, 302)

    def test_summary_private_event(self):
        creator = User.objects.create_user(username='privcreator', password='testpass123')
        event_date = timezone.now() - timedelta(hours=3)
        private_event = Event.objects.create(
            title='Private Completed',
            date=event_date,
            voting_deadline=event_date,
            created_by=creator,
            duration_minutes=60,
        )
        self.client.login(username='privcreator', password='testpass123')
        resp = self.client.get(reverse('event_summary', kwargs={'pk': private_event.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_summary_shows_pending_proposal(self):
        temp_game = BoardGame.objects.create(name='Pending Game', is_temporary=True)
        GameSession.objects.create(
            event=self.event, board_game=temp_game,
            selection_method='manual', created_by=self.organizer,
        )
        GameOwnershipProposal.objects.create(
            board_game=temp_game,
            proposed_owner=self.member,
            proposed_by=self.organizer,
            event=self.event,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.login(username='organizer', password='testpass123')
        resp = self.client.get(reverse('event_summary', kwargs={'pk': self.event.pk}))
        self.assertContains(resp, 'Pending')
        self.assertNotContains(resp, 'Add to Library')


@tag("integration")
class GameAddToLibraryTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(username='organizer', password='testpass123')
        self.attendee = User.objects.create_user(username='attendee', password='testpass123')
        self.group = Group.objects.create(name='Library Group')
        GroupMembership.objects.create(user=self.organizer, group=self.group, role='admin')
        GroupMembership.objects.create(user=self.attendee, group=self.group, role='member')
        event_date = timezone.now() - timedelta(hours=3)
        self.event = Event.objects.create(
            title='Completed Event',
            date=event_date,
            voting_deadline=event_date,
            created_by=self.organizer,
            group=self.group,
            duration_minutes=60,
        )
        EventAttendance.objects.create(user=self.attendee, event=self.event)
        self.temp_game = BoardGame.objects.create(name='Temp Game', is_temporary=True)

    def test_add_to_self_library(self):
        self.client.login(username='organizer', password='testpass123')
        resp = self.client.post(
            reverse('game_add_to_library', kwargs={'pk': self.temp_game.pk}) + f'?event={self.event.pk}',
            {'owner_type': 'self'},
        )
        self.assertEqual(resp.status_code, 302)
        self.temp_game.refresh_from_db()
        self.assertEqual(self.temp_game.owner, self.organizer)
        self.assertFalse(self.temp_game.is_temporary)

    def test_add_to_group_library(self):
        self.client.login(username='organizer', password='testpass123')
        resp = self.client.post(
            reverse('game_add_to_library', kwargs={'pk': self.temp_game.pk}) + f'?event={self.event.pk}',
            {'owner_type': 'group'},
        )
        self.assertEqual(resp.status_code, 302)
        self.temp_game.refresh_from_db()
        self.assertEqual(self.temp_game.group, self.group)
        self.assertFalse(self.temp_game.is_temporary)

    def test_propose_to_attendee(self):
        self.client.login(username='organizer', password='testpass123')
        resp = self.client.post(
            reverse('game_add_to_library', kwargs={'pk': self.temp_game.pk}) + f'?event={self.event.pk}',
            {'owner_type': 'attendee', 'owner_id': str(self.attendee.pk)},
        )
        self.assertEqual(resp.status_code, 302)
        self.temp_game.refresh_from_db()
        self.assertTrue(self.temp_game.is_temporary)
        proposal = GameOwnershipProposal.objects.get(board_game=self.temp_game)
        self.assertEqual(proposal.proposed_owner, self.attendee)
        self.assertEqual(proposal.status, 'pending')

    def test_propose_creates_notification(self):
        self.client.login(username='organizer', password='testpass123')
        self.client.post(
            reverse('game_add_to_library', kwargs={'pk': self.temp_game.pk}) + f'?event={self.event.pk}',
            {'owner_type': 'attendee', 'owner_id': str(self.attendee.pk)},
        )
        self.assertTrue(
            Notification.objects.filter(
                user=self.attendee,
                notification_type='game_ownership_proposed',
            ).exists()
        )

    def test_non_temporary_game_rejected(self):
        owned_game = BoardGame.objects.create(name='Owned', owner=self.organizer)
        self.client.login(username='organizer', password='testpass123')
        resp = self.client.get(
            reverse('game_add_to_library', kwargs={'pk': owned_game.pk}) + f'?event={self.event.pk}',
        )
        self.assertEqual(resp.status_code, 302)

    def test_non_organizer_cannot_add_to_library(self):
        self.client.login(username='attendee', password='testpass123')
        resp = self.client.post(
            reverse('game_add_to_library', kwargs={'pk': self.temp_game.pk}) + f'?event={self.event.pk}',
            {'owner_type': 'self'},
        )
        self.assertEqual(resp.status_code, 403)


@tag("integration")
class GameProposalAcceptDeclineTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(username='organizer', password='testpass123')
        self.attendee = User.objects.create_user(username='attendee', password='testpass123')
        self.group = Group.objects.create(name='Proposal Group')
        GroupMembership.objects.create(user=self.organizer, group=self.group, role='admin')
        event_date = timezone.now() - timedelta(hours=3)
        self.event = Event.objects.create(
            title='Proposal Event',
            date=event_date,
            voting_deadline=event_date,
            created_by=self.organizer,
            group=self.group,
            duration_minutes=60,
        )
        self.temp_game = BoardGame.objects.create(name='Proposed Game', is_temporary=True)
        self.proposal = GameOwnershipProposal.objects.create(
            board_game=self.temp_game,
            proposed_owner=self.attendee,
            proposed_by=self.organizer,
            event=self.event,
            expires_at=timezone.now() + timedelta(days=7),
        )

    def test_proposed_owner_can_accept(self):
        self.client.login(username='attendee', password='testpass123')
        resp = self.client.post(reverse('game_proposal_accept', kwargs={'pk': self.proposal.pk}))
        self.assertEqual(resp.status_code, 302)
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, 'accepted')
        self.temp_game.refresh_from_db()
        self.assertEqual(self.temp_game.owner, self.attendee)
        self.assertFalse(self.temp_game.is_temporary)

    def test_proposed_owner_can_decline(self):
        self.client.login(username='attendee', password='testpass123')
        resp = self.client.post(reverse('game_proposal_decline', kwargs={'pk': self.proposal.pk}))
        self.assertEqual(resp.status_code, 302)
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, 'declined')
        self.temp_game.refresh_from_db()
        self.assertIsNone(self.temp_game.owner)
        self.assertTrue(self.temp_game.is_temporary)

    def test_other_user_cannot_accept(self):
        other = User.objects.create_user(username='other', password='testpass123')
        self.client.login(username='other', password='testpass123')
        resp = self.client.post(reverse('game_proposal_accept', kwargs={'pk': self.proposal.pk}))
        self.assertEqual(resp.status_code, 403)

    def test_accept_creates_notification_for_proposer(self):
        self.client.login(username='attendee', password='testpass123')
        self.client.post(reverse('game_proposal_accept', kwargs={'pk': self.proposal.pk}))
        self.assertTrue(
            Notification.objects.filter(
                user=self.organizer,
                notification_type='game_ownership_accepted',
            ).exists()
        )

    def test_decline_creates_notification_for_proposer(self):
        self.client.login(username='attendee', password='testpass123')
        self.client.post(reverse('game_proposal_decline', kwargs={'pk': self.proposal.pk}))
        self.assertTrue(
            Notification.objects.filter(
                user=self.organizer,
                notification_type='game_ownership_declined',
            ).exists()
        )

    def test_cannot_accept_already_accepted(self):
        self.proposal.accept()
        self.client.login(username='attendee', password='testpass123')
        resp = self.client.post(reverse('game_proposal_accept', kwargs={'pk': self.proposal.pk}))
        self.assertEqual(resp.status_code, 302)


@tag("integration")
class EventListFilterModalTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='member', password='testpass123')
        cls.group = Group.objects.create(name='My Group')
        _make_member(cls.user, cls.group)
        cls.tag = EventTag.objects.create(name='tournament')
        cls.event = Event.objects.create(
            title='Group Game Night',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=cls.user,
            group=cls.group,
        )
        cls.event.tags.add(cls.tag)

    def test_event_list_has_filter_button(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, 'filter-modal-btn')

    def test_event_list_has_filter_modal(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, 'filter-modal-overlay')
        self.assertContains(response, 'filter-modal-close')
        self.assertContains(response, 'filter-apply-btn')

    def test_event_list_filter_button_shows_active_count(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('event_list'), {'tag': ['tournament']})
        self.assertContains(response, 'filter-modal-btn')
        self.assertEqual(response.context['active_filter_count'], 1)

    def test_event_list_no_active_filters_shows_zero_count(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertEqual(response.context['active_filter_count'], 0)

    def test_event_list_tag_filter_works_via_modal_submit(self):
        Event.objects.create(
            title='Other Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=self.user,
            group=self.group,
        )
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('event_list'), {'tag': ['tournament']})
        self.assertContains(response, 'Group Game Night')
        self.assertNotContains(response, 'Other Event')

    def test_event_list_filter_has_clear_link(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, reverse('event_list'))

    def test_event_list_unauthenticated_has_filter_button(self):
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, 'filter-modal-btn')

    def test_event_list_no_tags_still_shows_filter_when_tags_exist(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, 'filter-modal-overlay')


@tag("integration")
class DiscoverEventsFilterModalTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.creator = User.objects.create_user(username='creator', password='testpass123')
        cls.tag = EventTag.objects.create(name='boardgames')
        cls.event_tagged = Event.objects.create(
            title='Tagged Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=cls.creator,
            privacy='public',
        )
        cls.event_tagged.tags.add(cls.tag)
        cls.event_untagged = Event.objects.create(
            title='Untagged Event',
            date=FUTURE_DATE,
            voting_deadline=FUTURE_DATE,
            created_by=cls.creator,
            privacy='public',
        )

    def test_discover_has_filter_button(self):
        response = self.client.get(reverse('discover_events'))
        self.assertContains(response, 'filter-modal-btn')

    def test_discover_has_filter_modal(self):
        response = self.client.get(reverse('discover_events'))
        self.assertContains(response, 'filter-modal-overlay')
        self.assertContains(response, 'filter-modal-close')
        self.assertContains(response, 'filter-apply-btn')

    def test_discover_filter_button_shows_active_count_for_tag(self):
        response = self.client.get(reverse('discover_events'), {'tag': ['boardgames']})
        self.assertEqual(response.context['active_filter_count'], 1)

    def test_discover_filter_button_shows_active_count_for_date(self):
        response = self.client.get(
            reverse('discover_events'),
            {'date_from': (timezone.now() + timedelta(days=1)).strftime('%Y-%m-%d')},
        )
        self.assertEqual(response.context['active_filter_count'], 1)

    def test_discover_filter_button_shows_active_count_for_sort_non_default(self):
        response = self.client.get(reverse('discover_events'), {'sort': 'desc'})
        self.assertEqual(response.context['active_filter_count'], 1)

    def test_discover_filter_button_shows_active_count_for_multiple(self):
        response = self.client.get(
            reverse('discover_events'),
            {'tag': ['boardgames'], 'sort': 'desc'},
        )
        self.assertEqual(response.context['active_filter_count'], 2)

    def test_discover_no_active_filters_shows_zero_count(self):
        response = self.client.get(reverse('discover_events'))
        self.assertEqual(response.context['active_filter_count'], 0)

    def test_discover_tag_filter_still_works(self):
        response = self.client.get(reverse('discover_events'), {'tag': ['boardgames']})
        self.assertContains(response, 'Tagged Event')
        self.assertNotContains(response, 'Untagged Event')

    def test_discover_date_filter_still_works(self):
        future_plus = timezone.now() + timedelta(days=60)
        Event.objects.create(
            title='Far Future Event',
            date=future_plus,
            voting_deadline=future_plus,
            created_by=self.creator,
            privacy='public',
        )
        response = self.client.get(reverse('discover_events'), {
            'date_from': (timezone.now() + timedelta(days=45)).strftime('%Y-%m-%d'),
        })
        self.assertContains(response, 'Far Future Event')
        self.assertNotContains(response, 'Tagged Event')

    def test_discover_sort_still_works(self):
        early = timezone.now() + timedelta(days=5)
        late = timezone.now() + timedelta(days=15)
        Event.objects.create(title='Late Evt', date=late, voting_deadline=late, created_by=self.creator, privacy='public')
        Event.objects.create(title='Early Evt', date=early, voting_deadline=early, created_by=self.creator, privacy='public')
        response = self.client.get(reverse('discover_events'), {'sort': 'desc'})
        content = response.content.decode()
        self.assertLess(content.index('Late Evt'), content.index('Early Evt'))

    def test_discover_filter_has_clear_link(self):
        response = self.client.get(reverse('discover_events'))
        self.assertContains(response, reverse('discover_events'))
