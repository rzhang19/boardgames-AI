import zoneinfo

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from club.middleware import TimezoneMiddleware
from club.timezone_utils import get_timezone_choices, is_valid_timezone

User = get_user_model()


class UserModelTimezoneTest(TestCase):

    def test_user_timezone_defaults_to_utc(self):
        user = User.objects.create_user(username='tzuser', password='testpass123')
        self.assertEqual(user.timezone, 'UTC')

    def test_user_timezone_detected_defaults_to_false(self):
        user = User.objects.create_user(username='tzuser', password='testpass123')
        self.assertFalse(user.timezone_detected)

    def test_user_can_set_timezone(self):
        user = User.objects.create_user(username='tzuser', password='testpass123')
        user.timezone = 'America/New_York'
        user.save()
        user.refresh_from_db()
        self.assertEqual(user.timezone, 'America/New_York')

    def test_user_can_set_timezone_detected_flag(self):
        user = User.objects.create_user(username='tzuser', password='testpass123')
        user.timezone_detected = True
        user.save()
        user.refresh_from_db()
        self.assertTrue(user.timezone_detected)


class TimezoneUtilsTest(TestCase):

    def test_get_timezone_choices_returns_list(self):
        choices = get_timezone_choices()
        self.assertIsInstance(choices, list)
        self.assertTrue(len(choices) > 0)

    def test_get_timezone_choices_contains_utc(self):
        choices = get_timezone_choices()
        values = [c[0] for c in choices]
        self.assertIn('UTC', values)

    def test_get_timezone_choices_contains_us_zones(self):
        choices = get_timezone_choices()
        values = [c[0] for c in choices]
        self.assertIn('US/Eastern', values)
        self.assertIn('US/Pacific', values)

    def test_get_timezone_choices_contains_europe_zones(self):
        choices = get_timezone_choices()
        values = [c[0] for c in choices]
        self.assertIn('Europe/London', values)
        self.assertIn('Europe/Paris', values)

    def test_is_valid_timezone_with_valid_zone(self):
        self.assertTrue(is_valid_timezone('America/New_York'))

    def test_is_valid_timezone_with_utc(self):
        self.assertTrue(is_valid_timezone('UTC'))

    def test_is_valid_timezone_with_invalid_zone(self):
        self.assertFalse(is_valid_timezone('Invalid/Zone'))

    def test_is_valid_timezone_with_empty_string(self):
        self.assertFalse(is_valid_timezone(''))


class TimezoneMiddlewareTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = TimezoneMiddleware(lambda request: None)

    def test_middleware_activates_user_timezone(self):
        user = User.objects.create_user(
            username='tzuser', password='testpass123',
            timezone='America/Chicago',
        )
        request = self.factory.get('/')
        request.user = user
        self.middleware(request)
        self.assertEqual(
            timezone.get_current_timezone(),
            zoneinfo.ZoneInfo('America/Chicago'),
        )

    def test_middleware_defaults_to_utc_for_anonymous(self):
        request = self.factory.get('/')
        request.user = type('AnonymousUser', (), {'is_authenticated': False})()
        self.middleware(request)
        self.assertEqual(timezone.get_current_timezone(), zoneinfo.ZoneInfo('UTC'))

    def test_middleware_handles_invalid_timezone_gracefully(self):
        user = User.objects.create_user(
            username='tzuser', password='testpass123',
            timezone='Invalid/Zone',
        )
        request = self.factory.get('/')
        request.user = user
        self.middleware(request)
        self.assertEqual(timezone.get_current_timezone(), zoneinfo.ZoneInfo('UTC'))

    def test_middleware_uses_utc_when_user_has_default(self):
        user = User.objects.create_user(
            username='tzuser', password='testpass123',
        )
        request = self.factory.get('/')
        request.user = user
        self.middleware(request)
        self.assertEqual(timezone.get_current_timezone(), zoneinfo.ZoneInfo('UTC'))


class SettingsTimezoneViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='tzuser', password='testpass123',
            email='tz@example.com',
        )
        self.client.login(username='tzuser', password='testpass123')

    def test_settings_page_shows_timezone_dropdown(self):
        response = self.client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id_timezone')

    def test_settings_page_shows_current_timezone_selected(self):
        self.user.timezone = 'US/Pacific'
        self.user.save()
        response = self.client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'US/Pacific')

    def test_settings_save_timezone(self):
        self.client.post(reverse('user_settings'), {
            'email': 'tz@example.com',
            'timezone': 'America/New_York',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.timezone, 'America/New_York')
        self.assertFalse(self.user.timezone_detected)

    def test_settings_save_both_email_and_timezone(self):
        self.client.post(reverse('user_settings'), {
            'email': 'new@example.com',
            'timezone': 'Europe/London',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'new@example.com')
        self.assertEqual(self.user.timezone, 'Europe/London')

    def test_settings_rejects_invalid_timezone(self):
        response = self.client.post(reverse('user_settings'), {
            'email': 'tz@example.com',
            'timezone': 'Invalid/Zone',
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.timezone, 'UTC')

    def test_settings_combined_form_has_single_save_button(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'Save Settings')


class SaveTimezoneEndpointTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='tzuser', password='testpass123',
        )
        self.client.login(username='tzuser', password='testpass123')

    def test_save_timezone_saves_valid_timezone(self):
        self.client.post(reverse('save_timezone'), {
            'timezone': 'America/Chicago',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.timezone, 'America/Chicago')
        self.assertTrue(self.user.timezone_detected)

    def test_save_timezone_rejects_invalid_timezone(self):
        self.client.post(reverse('save_timezone'), {
            'timezone': 'Invalid/Zone',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.timezone, 'UTC')

    def test_save_timezone_does_not_override_if_already_detected(self):
        self.user.timezone = 'America/New_York'
        self.user.timezone_detected = True
        self.user.save()
        self.client.post(reverse('save_timezone'), {
            'timezone': 'America/Chicago',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.timezone, 'America/New_York')

    def test_save_timezone_redirects_to_next(self):
        response = self.client.post(reverse('save_timezone'), {
            'timezone': 'America/Chicago',
            'next': '/games/',
        })
        self.assertRedirects(response, '/games/')

    def test_save_timezone_redirects_to_dashboard_by_default(self):
        response = self.client.post(reverse('save_timezone'), {
            'timezone': 'America/Chicago',
        })
        self.assertRedirects(response, '/')

    def test_save_timezone_requires_login(self):
        self.client.logout()
        response = self.client.post(reverse('save_timezone'), {
            'timezone': 'America/Chicago',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_save_timezone_get_redirects_to_dashboard(self):
        response = self.client.get(reverse('save_timezone'))
        self.assertRedirects(response, '/')


class AutoDetectJavascriptTest(TestCase):

    def test_detect_script_present_when_not_detected(self):
        user = User.objects.create_user(username='tzuser', password='testpass123')
        self.client.login(username='tzuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Intl.DateTimeFormat')

    def test_detect_script_absent_when_already_detected(self):
        user = User.objects.create_user(
            username='tzuser', password='testpass123',
            timezone_detected=True,
        )
        self.client.login(username='tzuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'Intl.DateTimeFormat')

    def test_detect_script_absent_for_anonymous(self):
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'Intl.DateTimeFormat')
