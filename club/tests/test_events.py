from datetime import timedelta, time

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from club.models import Event, EventAttendance

User = get_user_model()


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
