from datetime import timedelta, time

from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from club.models import Event, EventAttendance, SiteSettings

User = get_user_model()


@tag("integration")
class EventListViewTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_organizer=True
        )
        self.event1 = Event.objects.create(
            title='Friday Night', date='2026-05-01T18:00:00Z',
            voting_deadline='2026-05-01T18:00:00Z',
            location='Community Center', created_by=self.admin
        )
        self.event2 = Event.objects.create(
            title='Saturday Bash', date='2026-06-01T12:00:00Z',
            voting_deadline='2026-06-01T12:00:00Z',
            created_by=self.admin
        )

    def test_event_list_displays_all_events(self):
        response = self.client.get(reverse('event_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Friday Night')
        self.assertContains(response, 'Saturday Bash')


@tag("integration")
class EventCreateViewTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_organizer=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )
        self.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123',
            is_site_admin=True, is_organizer=False,
        )

    def test_create_page_requires_login(self):
        response = self.client.get(reverse('event_add'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_admin_can_access_create_page(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('event_add'))
        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_access_create_page(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('event_add'))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_event_with_date_and_time(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(reverse('event_add'), {
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
        self.assertEqual(response.url, reverse('event_detail', kwargs={'pk': event.pk}))

    def test_create_event_with_date_only_defaults_time_to_midnight(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(reverse('event_add'), {
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
        response = self.client.post(reverse('event_add'), {
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
        response = self.client.post(reverse('event_add'), {
            'title': '',
            'date': '2026-08-01',
            'time': '18:00',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.exists())

    def test_create_event_without_date_fails(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(reverse('event_add'), {
            'title': 'No Date Event',
            'date': '',
            'time': '18:00',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='No Date Event').exists())

    def test_regular_user_cannot_create_event(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(reverse('event_add'), {
            'title': 'Sneaky Event',
            'date': '2026-08-01',
            'time': '18:00',
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Event.objects.filter(title='Sneaky Event').exists())

    def test_cannot_create_event_with_past_date(self):
        self.client.login(username='admin', password='testpass123')
        past = (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add'), {
            'title': 'Past Event',
            'date': past,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Past Event').exists())
        self.assertContains(response, 'past')

    def test_can_create_event_with_future_date(self):
        self.client.login(username='admin', password='testpass123')
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add'), {
            'title': 'Future Event',
            'date': future,
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Event.objects.filter(title='Future Event').exists())

    def test_create_event_form_html(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('event_add'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="date"')
        self.assertContains(response, 'type="time"')
        self.assertContains(response, 'Event Details')
        self.assertContains(response, 'Date &amp; Time')
        self.assertContains(response, 'Location')
        html = response.content.decode()
        asterisk_count = html.count('<span class="required-asterisk">')
        self.assertEqual(asterisk_count, 2)
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

    def test_site_admin_without_organizer_can_access_create_page(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('event_add'))
        self.assertEqual(response.status_code, 200)

    def test_site_admin_without_organizer_can_create_event(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post(reverse('event_add'), {
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
        response = self.client.post(reverse('event_add'), {
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
        response = self.client.post(reverse('event_add'), {
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
        response = self.client.post(reverse('event_add'), {
            'title': 'Default Offset',
            'date': '2026-07-01',
            'time': '18:00',
        })
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get(title='Default Offset')
        self.assertEqual(event.voting_deadline_offset_minutes, 0)


@tag("integration")
class EventDetailViewTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_organizer=True
        )
        self.event = Event.objects.create(
            title='Test Event', date='2026-05-01T18:00:00Z',
            voting_deadline='2026-05-01T18:00:00Z',
            location='Hall', description='A test event',
            created_by=self.admin
        )

    def test_event_detail_displays_info(self):
        response = self.client.get(reverse('event_detail', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Event')
        self.assertContains(response, 'Hall')
        self.assertContains(response, 'A test event')

    def test_event_detail_nonexistent_returns_404(self):
        response = self.client.get(reverse('event_detail', kwargs={'pk': 9999}))
        self.assertEqual(response.status_code, 404)

    def test_event_detail_shows_attendees(self):
        user1 = User.objects.create_user(username='u1', password='testpass123')
        EventAttendance.objects.create(user=user1, event=self.event)
        response = self.client.get(reverse('event_detail', kwargs={'pk': self.event.pk}))
        self.assertContains(response, 'u1')

    def test_event_detail_shows_rsvp_for_authenticated_user(self):
        user = User.objects.create_user(username='attendee', password='testpass123')
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'pk': self.event.pk}))
        self.assertContains(response, 'RSVP')


@tag("integration")
class EventRSVPTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_organizer=True
        )
        self.user = User.objects.create_user(
            username='attendee', password='testpass123'
        )
        self.event = Event.objects.create(
            title='RSVP Event', date='2026-05-01T18:00:00Z',
            voting_deadline='2026-05-01T18:00:00Z',
            created_by=self.admin
        )

    def test_rsvp_requires_login(self):
        response = self.client.post(reverse('event_rsvp', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_user_can_rsvp(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(reverse('event_rsvp', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            EventAttendance.objects.filter(user=self.user, event=self.event).exists()
        )

    def test_user_can_cancel_rsvp(self):
        EventAttendance.objects.create(user=self.user, event=self.event)
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(reverse('event_rsvp', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            EventAttendance.objects.filter(user=self.user, event=self.event).exists()
        )

    def test_rsvp_redirects_to_event_detail(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(reverse('event_rsvp', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.url, reverse('event_detail', kwargs={'pk': self.event.pk}))

    def test_rsvp_nonexistent_event_returns_404(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.post(reverse('event_rsvp', kwargs={'pk': 9999}))
        self.assertEqual(response.status_code, 404)


@tag("integration")
class EventEditViewTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_organizer=True
        )
        self.other_organizer = User.objects.create_user(
            username='other_org', password='testpass123', is_organizer=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )
        self.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123',
            is_site_admin=True, is_organizer=True,
        )
        self.site_admin_only = User.objects.create_user(
            username='siteadminonly', password='testpass123',
            is_site_admin=True, is_organizer=False,
        )
        self.future_date = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        self.event = Event.objects.create(
            title='Original Title',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            location='Original Location',
            description='Original Description',
            created_by=self.organizer,
        )

    def test_edit_page_requires_login(self):
        response = self.client.get(reverse('event_edit', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_organizer_can_access_edit_page(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('event_edit', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)

    def test_other_organizer_can_access_edit_page(self):
        self.client.login(username='other_org', password='testpass123')
        response = self.client.get(reverse('event_edit', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_access_edit_page(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('event_edit', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 403)

    def test_site_admin_can_access_edit_page(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('event_edit', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)

    def test_edit_page_shows_pre_populated_form_and_edit_action(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('event_edit', kwargs={'pk': self.event.pk}))
        self.assertContains(response, 'Original Title')
        self.assertContains(response, 'Original Location')
        self.assertContains(response, 'Original Description')
        self.assertContains(response, 'Edit Event')
        self.assertContains(response, 'Edit Event</button>')

    def test_organizer_can_edit_event_title(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('event_edit', kwargs={'pk': self.event.pk}), {
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
        response = self.client.post(reverse('event_edit', kwargs={'pk': self.event.pk}), {
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
        response = self.client.post(reverse('event_edit', kwargs={'pk': self.event.pk}), {
            'title': 'Updated Title',
            'date': self.future_date,
            'time': '',
            'location': 'Original Location',
            'description': 'Original Description',
        })
        self.assertRedirects(response, reverse('event_detail', kwargs={'pk': self.event.pk}))

    def test_cannot_edit_date_to_past(self):
        self.client.login(username='organizer', password='testpass123')
        past = (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_edit', kwargs={'pk': self.event.pk}), {
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
        )
        self.client.login(username='organizer', password='testpass123')
        date_str = past_event.date.strftime('%Y-%m-%d')
        time_str = past_event.date.strftime('%H:%M')
        response = self.client.post(reverse('event_edit', kwargs={'pk': past_event.pk}), {
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
        response = self.client.get(reverse('event_edit', kwargs={'pk': 9999}))
        self.assertEqual(response.status_code, 404)

    def test_edit_preserves_created_by(self):
        self.client.login(username='other_org', password='testpass123')
        self.client.post(reverse('event_edit', kwargs={'pk': self.event.pk}), {
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
        response = self.client.post(reverse('event_edit', kwargs={'pk': self.event.pk}), {
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
        response = self.client.get(reverse('event_edit', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        asterisk_count = html.count('<span class="required-asterisk">')
        self.assertEqual(asterisk_count, 2)

    def test_site_admin_without_organizer_can_access_edit_page(self):
        self.client.login(username='siteadminonly', password='testpass123')
        response = self.client.get(reverse('event_edit', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)

    def test_site_admin_without_organizer_can_edit_event_via_post(self):
        self.client.login(username='siteadminonly', password='testpass123')
        response = self.client.post(reverse('event_edit', kwargs={'pk': self.event.pk}), {
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
        response = self.client.post(reverse('event_edit', kwargs={'pk': self.event.pk}), {
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
        response = self.client.post(reverse('event_edit', kwargs={'pk': self.event.pk}), {
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
        response = self.client.post(reverse('event_edit', kwargs={'pk': self.event.pk}), {
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

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_organizer=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )
        self.site_admin_only = User.objects.create_user(
            username='siteadminonly', password='testpass123',
            is_site_admin=True, is_organizer=False,
        )
        self.event = Event.objects.create(
            title='Test Event',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=self.organizer,
        )

    def test_organizer_sees_edit_button_on_event_detail(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'pk': self.event.pk}))
        self.assertContains(response, reverse('event_edit', kwargs={'pk': self.event.pk}))
        self.assertContains(response, 'Edit Event')

    def test_regular_user_does_not_see_edit_button(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'pk': self.event.pk}))
        self.assertNotContains(response, 'Edit Event')

    def test_anonymous_user_does_not_see_edit_button(self):
        response = self.client.get(reverse('event_detail', kwargs={'pk': self.event.pk}))
        self.assertNotContains(response, 'Edit Event')

    def test_site_admin_without_organizer_sees_edit_button_on_event_detail(self):
        self.client.login(username='siteadminonly', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'pk': self.event.pk}))
        self.assertContains(response, reverse('event_edit', kwargs={'pk': self.event.pk}))
        self.assertContains(response, 'Edit Event')


@tag("integration")
class RecurringEventAccessTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_organizer=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )
        self.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123',
            is_site_admin=True, is_organizer=False,
        )

    def test_recurring_page_requires_login(self):
        response = self.client.get(reverse('event_add_recurring'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_organizer_can_access_recurring_page(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('event_add_recurring'))
        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_access_recurring_page(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('event_add_recurring'))
        self.assertEqual(response.status_code, 403)

    def test_site_admin_can_access_recurring_page(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('event_add_recurring'))
        self.assertEqual(response.status_code, 200)

    def test_preview_page_requires_login(self):
        response = self.client.get(reverse('event_add_recurring_preview'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_regular_user_cannot_access_preview_page(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('event_add_recurring_preview'))
        self.assertEqual(response.status_code, 403)


@tag("integration")
class RecurringEventFormValidationTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_organizer=True
        )
        self.client.login(username='organizer', password='testpass123')

    def test_start_date_in_past_fails(self):
        past = (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add_recurring'), {
            'title': 'Past Recurring',
            'start_date': past,
            'end_type': 'count',
            'occurrence_count': '3',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Past Recurring').exists())

    def test_occurrence_count_below_minimum_fails(self):
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add_recurring'), {
            'title': 'Too Few',
            'start_date': future,
            'end_type': 'count',
            'occurrence_count': '1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Too Few').exists())

    def test_occurrence_count_above_maximum_fails(self):
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add_recurring'), {
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
        response = self.client.post(reverse('event_add_recurring'), {
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
        response = self.client.post(reverse('event_add_recurring'), {
            'title': 'Past End',
            'start_date': future,
            'end_type': 'end_date',
            'end_date': past,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Past End').exists())

    def test_missing_title_fails(self):
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add_recurring'), {
            'title': '',
            'start_date': future,
            'end_type': 'count',
            'occurrence_count': '3',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.exists())

    def test_missing_start_date_fails(self):
        response = self.client.post(reverse('event_add_recurring'), {
            'title': 'No Date',
            'start_date': '',
            'end_type': 'count',
            'occurrence_count': '3',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.exists())

    def test_valid_count_redirects_to_preview(self):
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add_recurring'), {
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
        self.assertEqual(response.url, reverse('event_add_recurring_preview'))

    def test_valid_end_date_redirects_to_preview(self):
        start = (timezone.now() + timedelta(days=3)).strftime('%Y-%m-%d')
        end = (timezone.now() + timedelta(days=24)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add_recurring'), {
            'title': 'Weekly Game Night',
            'start_date': start,
            'end_type': 'end_date',
            'end_date': end,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('event_add_recurring_preview'))


@tag("system")
class RecurringEventPreviewTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_organizer=True
        )
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
        return self.client.post(reverse('event_add_recurring'), defaults)

    def test_preview_shows_all_computed_dates(self):
        self._post_valid_form()
        response = self.client.get(reverse('event_add_recurring_preview'))
        self.assertEqual(response.status_code, 200)
        dates = response.context['dates']
        self.assertEqual(len(dates), 4)
        for d in dates:
            self.assertTrue(d['checked'])

    def test_preview_shows_event_details(self):
        self._post_valid_form()
        response = self.client.get(reverse('event_add_recurring_preview'))
        self.assertContains(response, 'Weekly Game Night')
        self.assertContains(response, 'The Den')

    def test_preview_without_session_redirects_to_form(self):
        response = self.client.get(reverse('event_add_recurring_preview'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('event_add_recurring'))

    def test_preview_with_skip_dates_creates_only_checked_events(self):
        self._post_valid_form(occurrence_count='4')
        response = self.client.post(reverse('event_add_recurring_preview'), {
            'submit': 'Create Events',
            'selected_dates': ['0', '2'],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Event.objects.filter(title='Weekly Game Night').count(), 2)

    def test_preview_creates_events_with_correct_fields(self):
        self._post_valid_form()
        response = self.client.post(reverse('event_add_recurring_preview'), {
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
        self.client.post(reverse('event_add_recurring_preview'), {
            'submit': 'Create Events',
            'selected_dates': ['0', '1', '2', '3'],
        })
        session = self.client.session
        self.assertNotIn('recurring_event_form_data', session)
        self.assertNotIn('recurring_event_dates', session)

    def test_preview_cancel_clears_session_and_redirects(self):
        self._post_valid_form()
        response = self.client.post(reverse('event_add_recurring_preview'), {
            'cancel': 'Cancel',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('event_list'))
        session = self.client.session
        self.assertNotIn('recurring_event_form_data', session)
        self.assertNotIn('recurring_event_dates', session)
        self.assertEqual(Event.objects.filter(title='Weekly Game Night').count(), 0)

    def test_preview_skip_all_dates_fails(self):
        self._post_valid_form(occurrence_count='2')
        response = self.client.post(reverse('event_add_recurring_preview'), {
            'submit': 'Create Events',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Event.objects.filter(title='Weekly Game Night').count(), 0)

    def test_preview_redirects_to_event_list_after_creation(self):
        self._post_valid_form()
        response = self.client.post(reverse('event_add_recurring_preview'), {
            'submit': 'Create Events',
            'selected_dates': ['0', '1', '2', '3'],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('event_list'))

    def test_weekly_dates_are_seven_days_apart(self):
        self._post_valid_form(occurrence_count='3')
        response = self.client.get(reverse('event_add_recurring_preview'))
        dates = response.context['dates']
        self.assertEqual(len(dates), 3)
        for i in range(1, len(dates)):
            diff = dates[i]['datetime'] - dates[i - 1]['datetime']
            self.assertEqual(diff.days, 7)

    def test_end_date_produces_correct_number_of_dates(self):
        start = (timezone.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        end = (timezone.now() + timedelta(days=22)).strftime('%Y-%m-%d')
        self._post_valid_form(end_type='end_date', end_date=end, start_date=start)
        response = self.client.get(reverse('event_add_recurring_preview'))
        dates = response.context['dates']
        self.assertEqual(len(dates), 4)

    def test_preview_has_select_all_checkbox(self):
        self._post_valid_form()
        response = self.client.get(reverse('event_add_recurring_preview'))
        self.assertContains(response, 'select-all-toggle')


@tag("integration")
class RecurringEventButtonTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123', is_organizer=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )

    def test_organizer_sees_recurring_event_button(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, reverse('event_add_recurring'))
        self.assertContains(response, 'Create Recurring Event')

    def test_regular_user_does_not_see_recurring_event_button(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertNotContains(response, 'Create Recurring Event')
