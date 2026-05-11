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


@tag("unit")
class CaseInsensitiveBackendTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='TestUser', password='testpass123', email='Test@Example.com'
        )
        from club.backends import EmailOrUsernameBackend
        self.backend = EmailOrUsernameBackend()

    def test_authenticate_with_lowercase_username(self):
        result = self.backend.authenticate(
            request=None, username='testuser', password='testpass123'
        )
        self.assertEqual(result, self.user)

    def test_authenticate_with_uppercase_username(self):
        result = self.backend.authenticate(
            request=None, username='TESTUSER', password='testpass123'
        )
        self.assertEqual(result, self.user)

    def test_authenticate_with_lowercase_email(self):
        result = self.backend.authenticate(
            request=None, username='test@example.com', password='testpass123'
        )
        self.assertEqual(result, self.user)

    def test_authenticate_with_uppercase_email(self):
        result = self.backend.authenticate(
            request=None, username='TEST@EXAMPLE.COM', password='testpass123'
        )
        self.assertEqual(result, self.user)


@tag("unit")
class EmailOrUsernameBackendTimingTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='backenduser', password='testpass123', email='backend@example.com'
        )
        from club.backends import EmailOrUsernameBackend
        self.backend = EmailOrUsernameBackend()

    def test_nonexistent_user_triggers_password_hash(self):
        from unittest.mock import patch
        with patch.object(User, 'set_password') as mock_set_password:
            result = self.backend.authenticate(
                request=None, username='ghost', password='anypass'
            )
            mock_set_password.assert_called_once_with('anypass')
            self.assertIsNone(result)

    def test_nonexistent_user_returns_none(self):
        result = self.backend.authenticate(
            request=None, username='ghost', password='anypass'
        )
        self.assertIsNone(result)

    def test_existing_user_wrong_password_returns_none(self):
        result = self.backend.authenticate(
            request=None, username='backenduser', password='wrongpass'
        )
        self.assertIsNone(result)

    def test_existing_user_correct_password_by_username(self):
        result = self.backend.authenticate(
            request=None, username='backenduser', password='testpass123'
        )
        self.assertEqual(result, self.user)

    def test_existing_user_correct_password_by_email(self):
        result = self.backend.authenticate(
            request=None, username='backend@example.com', password='testpass123'
        )
        self.assertEqual(result, self.user)

    def test_unverified_user_returns_none(self):
        from django.test import override_settings
        user = User.objects.create_user(
            username='unverified', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        with override_settings(REQUIRE_EMAIL_VERIFICATION=True):
            result = self.backend.authenticate(
                request=None, username='unverified', password='testpass123'
            )
            self.assertIsNone(result)


@tag("unit")
class UnverifiedFriendRequestRateLimitTest(TestCase):

    def setUp(self):
        self.unverified = User.objects.create_user(
            username='unverified', password='testpass123',
        )

    def _create_users(self, *usernames, password='testpass123'):
        return [User.objects.create_user(username=u, password=password) for u in usernames]

    def test_unverified_can_send_up_to_3_pending(self):
        targets = self._create_users('target1', 'target2', 'target3')
        for t in targets:
            from club.models import Friendship
            self.assertTrue(Friendship.can_send_request(self.unverified, t))
            Friendship.objects.create(requester=self.unverified, receiver=t, status='pending')

    def test_unverified_blocked_on_4th_pending(self):
        from club.models import Friendship
        targets = self._create_users('target1', 'target2', 'target3', 'target4')
        for t in targets[:3]:
            Friendship.objects.create(requester=self.unverified, receiver=t, status='pending')
        self.assertFalse(Friendship.can_send_request(self.unverified, targets[3]))

    def test_verified_user_not_limited(self):
        from club.models import Friendship
        verified = User.objects.create_user(
            username='verified', password='testpass123',
            email_verified=True, email='verified@test.com',
        )
        targets = self._create_users('target1', 'target2', 'target3', 'target4')
        for t in targets[:3]:
            Friendship.objects.create(requester=verified, receiver=t, status='pending')
        self.assertTrue(Friendship.can_send_request(verified, targets[3]))

    def test_accepting_frees_up_slot(self):
        from club.models import Friendship
        targets = self._create_users('target1', 'target2', 'target3', 'target4')
        for t in targets[:3]:
            Friendship.objects.create(requester=self.unverified, receiver=t, status='pending')
        Friendship.objects.filter(requester=self.unverified, receiver=targets[0]).update(status='accepted')
        self.assertTrue(Friendship.can_send_request(self.unverified, targets[3]))

    def test_declining_frees_up_slot(self):
        from club.models import Friendship
        targets = self._create_users('target1', 'target2', 'target3', 'target4')
        for t in targets[:3]:
            Friendship.objects.create(requester=self.unverified, receiver=t, status='pending')
        Friendship.objects.filter(requester=self.unverified, receiver=targets[0]).update(status='declined')
        self.assertTrue(Friendship.can_send_request(self.unverified, targets[3]))

    def test_unverified_still_subject_to_decline_cooldown(self):
        from club.models import Friendship
        from django.utils import timezone
        target = self._create_users('target1')[0]
        Friendship.objects.create(
            requester=self.unverified, receiver=target,
            status='declined', decline_count=2, last_declined_at=timezone.now(),
        )
        self.assertFalse(Friendship.can_send_request(self.unverified, target))
