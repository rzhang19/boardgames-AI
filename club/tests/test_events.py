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
            location='Community Center', created_by=self.admin
        )
        self.event2 = Event.objects.create(
            title='Saturday Bash', date='2026-06-01T12:00:00Z',
            created_by=self.admin
        )

    def test_event_list_displays_all_events(self):
        response = self.client.get(reverse('event_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Friday Night')
        self.assertContains(response, 'Saturday Bash')

    def test_event_list_accessible_without_login(self):
        response = self.client.get(reverse('event_list'))
        self.assertEqual(response.status_code, 200)


class EventCreateViewTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_organizer=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
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

    def test_created_event_redirects_to_detail(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.post(reverse('event_add'), {
            'title': 'New Event',
            'date': '2026-08-01',
            'time': '18:00',
        })
        event = Event.objects.get(title='New Event')
        self.assertEqual(response.url, reverse('event_detail', kwargs={'pk': event.pk}))

    def test_cannot_create_event_with_past_date(self):
        self.client.login(username='admin', password='testpass123')
        past = (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add'), {
            'title': 'Past Event',
            'date': past,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Event.objects.filter(title='Past Event').exists())

    def test_cannot_create_event_with_past_date_shows_error(self):
        self.client.login(username='admin', password='testpass123')
        past = (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        response = self.client.post(reverse('event_add'), {
            'title': 'Past Event',
            'date': past,
        })
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

    def test_create_form_has_separate_date_and_time_inputs(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('event_add'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="date"')
        self.assertContains(response, 'type="time"')

    def test_date_and_time_rendered_on_same_line(self):
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('event_add'))
        self.assertContains(response, 'datetime-row')


class EventDetailViewTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123', is_organizer=True
        )
        self.event = Event.objects.create(
            title='Test Event', date='2026-05-01T18:00:00Z',
            location='Hall', description='A test event',
            created_by=self.admin
        )

    def test_event_detail_displays_info(self):
        response = self.client.get(reverse('event_detail', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Event')
        self.assertContains(response, 'Hall')
        self.assertContains(response, 'A test event')

    def test_event_detail_accessible_without_login(self):
        response = self.client.get(reverse('event_detail', kwargs={'pk': self.event.pk}))
        self.assertEqual(response.status_code, 200)

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

    def test_rsvp_toggles_correctly(self):
        self.client.login(username='attendee', password='testpass123')
        self.client.post(reverse('event_rsvp', kwargs={'pk': self.event.pk}))
        self.assertTrue(
            EventAttendance.objects.filter(user=self.user, event=self.event).exists()
        )
        self.client.post(reverse('event_rsvp', kwargs={'pk': self.event.pk}))
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
