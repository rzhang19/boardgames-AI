import zoneinfo

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, SimpleTestCase, RequestFactory, tag
from django.utils import timezone

from club.middleware import TimezoneMiddleware
from club.timezone_utils import get_timezone_choices, is_valid_timezone
from club.validators import HasLetterAndDigitValidator

User = get_user_model()


@tag("unit")
class HasLetterAndDigitValidatorTest(TestCase):

    def setUp(self):
        self.validator = HasLetterAndDigitValidator()

    def test_password_with_letter_and_digit_passes(self):
        self.assertIsNone(self.validator.validate('Password1'))

    def test_password_with_only_letters_fails(self):
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate('abcdefgh')
        self.assertEqual(ctx.exception.code, 'password_no_digit')

    def test_password_with_only_digits_fails(self):
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate('12345678')
        self.assertEqual(ctx.exception.code, 'password_no_letter')

    def test_password_with_mixed_case_and_digit_passes(self):
        self.assertIsNone(self.validator.validate('MyPass99'))

    def test_password_with_special_chars_letter_and_digit_passes(self):
        self.assertIsNone(self.validator.validate('P@ssw0rd!'))

    def test_help_text_returns_expected_string(self):
        self.assertIn('letter', self.validator.get_help_text())
        self.assertIn('digit', self.validator.get_help_text())


@tag("unit")
class UserThemeFieldTest(TestCase):

    def test_theme_default_is_system(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        self.assertEqual(user.theme, 'system')

    def test_theme_accepts_light(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        user.theme = 'light'
        user.save()
        user.refresh_from_db()
        self.assertEqual(user.theme, 'light')

    def test_theme_accepts_dark(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        user.theme = 'dark'
        user.save()
        user.refresh_from_db()
        self.assertEqual(user.theme, 'dark')

    def test_theme_accepts_system(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        user.theme = 'system'
        user.save()
        user.refresh_from_db()
        self.assertEqual(user.theme, 'system')


@tag("unit")
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


@tag("unit")
class TimezoneUtilsTest(SimpleTestCase):

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


@tag("unit")
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
