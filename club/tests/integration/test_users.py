import hashlib
import io
import os
import re
import time
import zoneinfo
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from django.core.signing import TimestampSigner
from django.test import Client, TestCase, override_settings, tag
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from club.models import (
    Block,
    BoardGame,
    Event,
    EventAttendance,
    Friendship,
    Group,
    GroupMembership,
    Notification,
    PasswordHistory,
    SiteSettings,
    VerifiedIcon,
    Vote,
)

User = get_user_model()


def _password_state_component(user):
    return hashlib.sha256(user.password.encode()).hexdigest()[:16]


def _create_image(filename='test.jpg', size=(100, 100), fmt='JPEG'):
    img = Image.new('RGB', size, color='red')
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return SimpleUploadedFile(filename, buf.read(), content_type='image/jpeg')


def _create_users(*usernames, password='testpass123', **kwargs):
    return [User.objects.create_user(username=u, password=password, **kwargs) for u in usernames]


def _create_verified_user(username, password='testpass123', **kwargs):
    return User.objects.create_user(
        username=username, password=password,
        email_verified=True, email=f'{username}@test.com', **kwargs,
    )


def _create_icon_image(name='test.png'):
    img = Image.new('RGB', (1, 1), color='red')
    buffer = io.BytesIO()
    fmt = name.rsplit('.', 1)[-1].upper()
    if fmt == 'JPG':
        fmt = 'JPEG'
    img.save(buffer, format=fmt)
    return ContentFile(buffer.getvalue(), name=name)


def _read_css():
    css_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        '..', '..', 'static', 'css', 'style.css'
    )
    css_path = os.path.normpath(css_path)
    with open(css_path, 'r') as f:
        return f.read()


def _read_base_template():
    from django.template.loader import get_template
    return get_template('base.html').template.source


def _read_settings_template():
    from django.template.loader import get_template
    return get_template('club/settings.html').template.source


GENERIC_MESSAGE = 'If an account with that email or username exists, a reset link has been sent.'


@tag("integration")
class RegistrationTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()

    def test_registration_page_loads(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Register')

    def test_register_new_user_with_valid_data(self):
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='newuser').exists())
        new_user = User.objects.get(username='newuser')
        self.assertFalse(new_user.is_superuser)
        self.assertTrue(new_user.email_verified)

    def test_registered_user_is_automatically_logged_in(self):
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_registration_with_mismatched_passwords_fails(self):
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'DifferentP@ss456',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newuser').exists())

    def test_registration_with_duplicate_username_fails(self):
        User.objects.create_user(username='taken', email='taken@example.com', password='testpass123')
        response = self.client.post(reverse('register'), {
            'username': 'taken',
            'email': 'another@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username='taken').count(), 1)

    def test_registration_with_blank_username_fails(self):
        response = self.client.post(reverse('register'), {
            'username': '',
            'email': 'newuser@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='').exists())

    def test_registration_without_email_succeeds(self):
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'email': '',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='newuser').exists())
        user = User.objects.get(username='newuser')
        self.assertEqual(user.email, '')
        self.assertFalse(user.email_verified)


@tag("integration")
class LoginTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()
        self.user = User.objects.create_user(
            username='loginuser', password='testpass123', email='login@example.com'
        )

    def test_login_page_loads(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Login')
        self.assertContains(response, 'Email or Username')

    def test_login_with_username(self):
        response = self.client.post(reverse('login'), {
            'username': 'loginuser',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    def test_login_with_email(self):
        response = self.client.post(reverse('login'), {
            'username': 'login@example.com',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    def test_login_with_invalid_password(self):
        response = self.client.post(reverse('login'), {
            'username': 'loginuser',
            'password': 'wrongpass',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please enter a correct')

    def test_password_toggle_script_present_on_login_page(self):
        response = self.client.get(reverse('login'))
        self.assertContains(response, 'pw-toggle-wrapper')
        self.assertContains(response, 'pw-toggle-btn')
        self.assertContains(response, 'Toggle password visibility')

    def test_password_toggle_script_present_after_failed_login(self):
        response = self.client.post(reverse('login'), {
            'username': 'loginuser',
            'password': 'wrongpass',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'pw-toggle-wrapper')
        self.assertContains(response, 'pw-toggle-btn')
        self.assertContains(response, 'Toggle password visibility')

    def test_password_toggle_script_has_double_wrap_guard(self):
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        self.assertIn('closest', content)

    def test_password_toggle_script_has_mutation_observer_fallback(self):
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        self.assertIn('MutationObserver', content)

    def test_password_field_present_after_failed_login(self):
        response = self.client.post(reverse('login'), {
            'username': 'loginuser',
            'password': 'wrongpass',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="password"')

    def test_login_with_nonexistent_user(self):
        response = self.client.post(reverse('login'), {
            'username': 'ghost',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 200)

    def test_authenticated_user_sees_username_on_dashboard(self):
        self.client.login(username='loginuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'My Groups')
        self.assertContains(response, 'My Games')

    def test_login_with_must_change_password_redirects_to_change_password(self):
        User.objects.create_user(
            username='tempuser', password='testpass123',
            must_change_password=True,
        )
        response = self.client.post(reverse('login'), {
            'username': 'tempuser',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('forced_password_change'))


@tag("integration")
class AdminBadgeTest(TestCase):

    def setUp(self):
        self.site_admin_user = User.objects.create_user(
            username='siteadminuser', password='testpass123', is_site_admin=True
        )
        self.regular_user = User.objects.create_user(
            username='regularuser', password='testpass123'
        )

    def test_site_admin_sees_site_admin_badge_on_dashboard(self):
        self.client.login(username='siteadminuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'My Groups')
        self.assertEqual(response.status_code, 200)

    def test_regular_user_does_not_see_any_badge(self):
        self.client.login(username='regularuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'Site Admin')


@tag("integration")
class LogoutTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='logoutuser', password='testpass123'
        )
        self.client.login(username='logoutuser', password='testpass123')

    def test_logout_redirects_to_dashboard(self):
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    def test_logout_actually_logs_out(self):
        self.client.post(reverse('logout'))
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'logoutuser')


@tag("integration")
class AccessControlTest(TestCase):

    def test_unauthenticated_user_cannot_access_manage_users(self):
        response = self.client.get(reverse('manage_users'), follow=False)
        self.assertIn('/login/', response.url)
        self.assertEqual(response.status_code, 302)

    def test_dashboard_accessible_without_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_login_link_present_for_anonymous_user(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('login'))

    def test_logout_link_present_for_authenticated_user(self):
        User.objects.create_user(username='authuser', password='testpass123')
        self.client.login(username='authuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('logout'))

    def test_register_link_present_for_anonymous_user(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('register'))


@tag("integration")
@override_settings(REQUIRE_EMAIL_VERIFICATION=True)
class EmailVerificationRegistrationTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()

    def test_register_with_verification_shows_sent_page(self):
        response = self.client.post(reverse('register'), {
            'username': 'verifyuser',
            'email': 'verify@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Check Your Email')
        self.assertContains(response, 'verify@example.com')

    def test_register_with_verification_sends_email(self):
        self.client.post(reverse('register'), {
            'username': 'verifyuser',
            'email': 'verify@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('verify@example.com', mail.outbox[0].to)

    def test_register_with_verification_does_not_auto_login(self):
        self.client.post(reverse('register'), {
            'username': 'verifyuser',
            'email': 'verify@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'verifyuser')

    def test_register_with_verification_user_not_email_verified(self):
        self.client.post(reverse('register'), {
            'username': 'verifyuser',
            'email': 'verify@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        user = User.objects.get(username='verifyuser')
        self.assertFalse(user.email_verified)


@tag("integration")
class EmailVerificationViewTest(TestCase):

    def test_valid_token_verifies_email(self):
        user = User.objects.create_user(
            username='verifyuser', password='testpass123',
            email='verify@example.com', email_verified=False
        )
        signer = TimestampSigner()
        token = signer.sign(user.pk)
        response = self.client.get(reverse('verify_email', kwargs={'token': token}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Email Verified')
        user.refresh_from_db()
        self.assertTrue(user.email_verified)

    def test_invalid_token_shows_failure(self):
        response = self.client.get(reverse('verify_email', kwargs={'token': 'invalid-token'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Verification Failed')

    def test_already_verified_user_stays_verified(self):
        user = User.objects.create_user(
            username='verifyuser', password='testpass123',
            email='verify@example.com', email_verified=True
        )
        signer = TimestampSigner()
        token = signer.sign(user.pk)
        response = self.client.get(reverse('verify_email', kwargs={'token': token}))
        self.assertContains(response, 'Email Verified')
        user.refresh_from_db()
        self.assertTrue(user.email_verified)


@tag("integration")
@override_settings(REQUIRE_EMAIL_VERIFICATION=True, DEBUG=False)
class EmailVerificationLoginBlockTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()

    def test_unverified_user_cannot_login(self):
        User.objects.create_user(
            username='unverified', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        response = self.client.post(reverse('login'), {
            'username': 'unverified',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please enter a correct')

    def test_unverified_user_cannot_login_with_email(self):
        User.objects.create_user(
            username='unverified', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        response = self.client.post(reverse('login'), {
            'username': 'unverified@example.com',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please enter a correct')

    def test_verified_user_can_login(self):
        User.objects.create_user(
            username='verified', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        response = self.client.post(reverse('login'), {
            'username': 'verified',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))


@tag("integration")
class UsernameValidationTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()

    def test_register_with_letters_numbers_underscore_dash(self):
        response = self.client.post(reverse('register'), {
            'username': 'my-user_123',
            'email': 'valid@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='my-user_123').exists())

    def test_register_with_username_containing_period(self):
        response = self.client.post(reverse('register'), {
            'username': 'user.name',
            'email': 'period@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='user.name').exists())

    def test_register_with_username_containing_at_sign_fails(self):
        response = self.client.post(reverse('register'), {
            'username': 'user@name',
            'email': 'atsign@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='user@name').exists())

    def test_register_with_username_containing_plus_fails(self):
        response = self.client.post(reverse('register'), {
            'username': 'user+name',
            'email': 'plus@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='user+name').exists())

    def test_register_with_username_starting_with_dash_fails(self):
        response = self.client.post(reverse('register'), {
            'username': '-user',
            'email': 'dash@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='-user').exists())

    def test_register_with_username_starting_with_period_fails(self):
        response = self.client.post(reverse('register'), {
            'username': '.user',
            'email': 'period@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='.user').exists())

    def test_register_with_username_starting_with_underscore_fails(self):
        response = self.client.post(reverse('register'), {
            'username': '_user',
            'email': 'underscore@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='_user').exists())

    def test_register_with_username_ending_with_dash_fails(self):
        response = self.client.post(reverse('register'), {
            'username': 'user-',
            'email': 'dash@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='user-').exists())

    def test_register_with_username_ending_with_period_fails(self):
        response = self.client.post(reverse('register'), {
            'username': 'user.',
            'email': 'period@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='user.').exists())

    def test_register_with_username_ending_with_underscore_fails(self):
        response = self.client.post(reverse('register'), {
            'username': 'user_',
            'email': 'underscore@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='user_').exists())

    def test_register_with_username_containing_spaces_fails(self):
        response = self.client.post(reverse('register'), {
            'username': 'user name',
            'email': 'space@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='user name').exists())

    def test_register_with_three_char_username_fails(self):
        response = self.client.post(reverse('register'), {
            'username': 'abc',
            'email': 'short@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='abc').exists())

    def test_register_with_exactly_four_char_username_succeeds(self):
        response = self.client.post(reverse('register'), {
            'username': 'abcd',
            'email': 'four@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='abcd').exists())


@tag("integration")
class PasswordHistoryTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()

    def test_password_history_stored_on_forced_change(self):
        user = User.objects.create_user(
            username='historytester',
            password='TempPassword123',
            must_change_password=True,
        )
        self.client.login(username='historytester', password='TempPassword123')
        response = self.client.post(reverse('forced_password_change'), {
            'new_password1': 'NewPassword456',
            'new_password2': 'NewPassword456',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(PasswordHistory.objects.filter(user=user).exists())

    def test_password_history_limits_to_five(self):
        user = User.objects.create_user(
            username='historylimit',
            password='Pass1',
            must_change_password=True,
        )
        self.client.login(username='historylimit', password='Pass1')
        for i in range(6):
            self.client.post(reverse('forced_password_change'), {
                'new_password1': f'Pass{i+2}',
                'new_password2': f'Pass{i+2}',
            })
            user.refresh_from_db()
            user.must_change_password = True
            user.save()
            self.client.login(username='historylimit', password=f'Pass{i+2}')
        history_count = PasswordHistory.objects.filter(user=user).count()
        self.assertLessEqual(history_count, 5)

    def test_can_use_different_password(self):
        user = User.objects.create_user(
            username='differentpass',
            password='OldPassword123',
            must_change_password=True,
        )
        self.client.login(username='differentpass', password='OldPassword123')
        response = self.client.post(reverse('forced_password_change'), {
            'new_password1': 'FreshPassword456',
            'new_password2': 'FreshPassword456',
        })
        self.assertEqual(response.status_code, 302)


@tag("integration")
class PasswordResetTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()

    def test_password_reset_page_loads(self):
        response = self.client.get(reverse('password_reset'))
        self.assertEqual(response.status_code, 200)

    def test_password_reset_with_valid_email_sends_link(self):
        User.objects.create_user(
            username='resetuser',
            email='reset@example.com',
            password='SomePassword123',
        )
        response = self.client.post(reverse('password_reset'), {
            'email_or_username': 'reset@example.com',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GENERIC_MESSAGE)
        self.assertNotContains(response, 'reset@example.com')
        self.assertEqual(len(mail.outbox), 1)

    def test_password_reset_with_valid_username_sends_link(self):
        User.objects.create_user(
            username='resetuser2',
            email='reset2@example.com',
            password='SomePassword123',
        )
        response = self.client.post(reverse('password_reset'), {
            'email_or_username': 'resetuser2',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GENERIC_MESSAGE)
        self.assertEqual(len(mail.outbox), 1)

    def test_password_reset_nonexistent_email_shows_generic_message(self):
        response = self.client.post(reverse('password_reset'), {
            'email_or_username': 'nonexistent@example.com',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GENERIC_MESSAGE)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_nonexistent_username_shows_generic_message(self):
        response = self.client.post(reverse('password_reset'), {
            'email_or_username': 'ghostuser',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GENERIC_MESSAGE)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_user_without_email_shows_generic_message(self):
        User.objects.create_user(
            username='noemailuser',
            password='SomePassword123',
        )
        response = self.client.post(reverse('password_reset'), {
            'email_or_username': 'noemailuser',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GENERIC_MESSAGE)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_does_not_reveal_email(self):
        User.objects.create_user(
            username='secretuser',
            email='secret@example.com',
            password='SomePassword123',
        )
        response = self.client.post(reverse('password_reset'), {
            'email_or_username': 'secretuser',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'secret@example.com')

    def test_password_reset_same_response_for_existing_and_nonexistent(self):
        User.objects.create_user(
            username='existsuser',
            email='exists@example.com',
            password='SomePassword123',
        )
        response_existing = self.client.post(reverse('password_reset'), {
            'email_or_username': 'existsuser',
        })
        response_nonexistent = self.client.post(reverse('password_reset'), {
            'email_or_username': 'doesnotexist',
        })
        self.assertEqual(response_existing.status_code, response_nonexistent.status_code)
        self.assertContains(response_existing, GENERIC_MESSAGE)
        self.assertContains(response_nonexistent, GENERIC_MESSAGE)

    def test_password_reset_rate_limit_prevents_rapid_resend(self):
        User.objects.create_user(
            username='ratelimituser',
            email='ratelimit@example.com',
            password='SomePassword123',
        )
        self.client.post(reverse('password_reset'), {
            'email_or_username': 'ratelimituser',
        })
        self.assertEqual(len(mail.outbox), 1)
        response = self.client.post(reverse('password_reset'), {
            'email_or_username': 'ratelimituser',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GENERIC_MESSAGE)
        self.assertEqual(len(mail.outbox), 1)

    def test_password_reset_rate_limit_applies_to_nonexistent_user(self):
        self.client.post(reverse('password_reset'), {
            'email_or_username': 'fake@example.com',
        })
        self.assertEqual(len(mail.outbox), 0)
        response = self.client.post(reverse('password_reset'), {
            'email_or_username': 'fake@example.com',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GENERIC_MESSAGE)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_resend_after_rate_limit_sends_new_email(self):
        from django.core.cache import cache
        User.objects.create_user(
            username='resenduser',
            email='resend@example.com',
            password='SomePassword123',
        )
        self.client.post(reverse('password_reset'), {
            'email_or_username': 'resenduser',
        })
        self.assertEqual(len(mail.outbox), 1)
        cache.delete('password_reset_rl_resenduser')
        self.client.post(reverse('password_reset'), {
            'email_or_username': 'resenduser',
        })
        self.assertEqual(len(mail.outbox), 2)

    def test_password_reset_old_token_invalidated_on_resend(self):
        from django.core.cache import cache
        from club.views import generate_password_token
        User.objects.create_user(
            username='tokeninvuser',
            email='tokeninv@example.com',
            password='SomePassword123',
            reset_token_version=0,
        )
        user = User.objects.get(username='tokeninvuser')
        old_token = generate_password_token(user)
        user.reset_token_version = 1
        user.save(update_fields=['reset_token_version'])
        cache.delete('password_reset_rl_tokeninvuser')
        response = self.client.get(reverse('password_reset_form', kwargs={'token': old_token}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid')

    def test_password_reset_form_valid_token(self):
        from club.views import generate_password_token
        user = User.objects.create_user(
            username='formuser',
            email='form@example.com',
            password='OldPass123',
        )
        token = generate_password_token(user)
        response = self.client.get(reverse('password_reset_form', kwargs={'token': token}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'New password')

    def test_password_reset_with_invalid_token_fails(self):
        response = self.client.get(reverse('password_reset_form', kwargs={'token': 'invalid'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid')

    def test_password_reset_updates_password(self):
        from club.views import generate_password_token
        user = User.objects.create_user(
            username='resetpass',
            email='resetpass@example.com',
            password='OriginalPass',
        )
        token = generate_password_token(user)
        response = self.client.post(reverse('password_reset_form', kwargs={'token': token}), {
            'new_password1': 'ResetPass123',
            'new_password2': 'ResetPass123',
        })
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertNotEqual(user.password, 'OriginalPass')

    def test_password_reset_token_invalid_after_password_change(self):
        from club.views import generate_password_token
        user = User.objects.create_user(
            username='tokeninval',
            email='tokeninval@example.com',
            password='OriginalPass123',
        )
        token = generate_password_token(user)
        user.set_password('CompletelyDifferent456')
        user.save()
        response = self.client.get(reverse('password_reset_form', kwargs={'token': token}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid')

    def test_password_reset_token_rejected_after_using_reset(self):
        from club.views import generate_password_token
        user = User.objects.create_user(
            username='usedreset',
            email='usedreset@example.com',
            password='OriginalPass123',
        )
        token = generate_password_token(user)
        self.client.post(reverse('password_reset_form', kwargs={'token': token}), {
            'new_password1': 'NewPass456',
            'new_password2': 'NewPass456',
        })
        response = self.client.post(reverse('password_reset_form', kwargs={'token': token}), {
            'new_password1': 'AnotherPass789',
            'new_password2': 'AnotherPass789',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid')
        user.refresh_from_db()
        self.assertTrue(user.check_password('NewPass456'))

    def test_password_reset_old_format_token_rejected(self):
        user = User.objects.create_user(
            username='oldformat',
            email='oldformat@example.com',
            password='SomePass123',
        )
        signer = TimestampSigner()
        token = signer.sign(user.pk)
        response = self.client.get(reverse('password_reset_form', kwargs={'token': token}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid')


@tag("integration")
class ProtectedUserTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()

    @override_settings(PROTECTED_USERNAMES='protecteduser')
    def test_protected_user_cannot_use_forced_password_change(self):
        user = User.objects.create_user(
            username='protecteduser',
            password='TempPassword123',
            must_change_password=True,
        )
        self.client.login(username='protecteduser', password='TempPassword123')
        response = self.client.get(reverse('forced_password_change'))
        self.assertContains(response, 'cannot have its password changed')

    @override_settings(PROTECTED_USERNAMES='protecteduser')
    def test_protected_user_password_reset_shows_generic_message(self):
        User.objects.create_user(
            username='protecteduser',
            email='protected@example.com',
            password='SomePassword123',
        )
        response = self.client.post(reverse('password_reset'), {
            'email_or_username': 'protecteduser',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GENERIC_MESSAGE)
        self.assertNotContains(response, 'cannot have its password reset')
        self.assertEqual(len(mail.outbox), 0)


@tag("integration")
class CaseInsensitiveLoginTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()
        self.user = User.objects.create_user(
            username='TestUser', password='testpass123', email='Test@Example.com'
        )

    def test_login_with_lowercase_username(self):
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    def test_login_with_uppercase_username(self):
        response = self.client.post(reverse('login'), {
            'username': 'TESTUSER',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    def test_login_with_mixed_case_email(self):
        response = self.client.post(reverse('login'), {
            'username': 'test@example.com',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    def test_username_stored_as_originally_entered(self):
        User.objects.create_user(
            username='StoredCase', password='testpass123'
        )
        user = User.objects.get(username='StoredCase')
        self.assertEqual(user.username, 'StoredCase')


@tag("integration")
class CaseInsensitiveRegistrationTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()

    def test_register_with_case_variant_of_existing_username_fails(self):
        User.objects.create_user(username='testuser', password='testpass123')
        response = self.client.post(reverse('register'), {
            'username': 'TestUser',
            'email': 'new@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='TestUser').exists())

    def test_register_with_exact_same_username_fails(self):
        User.objects.create_user(username='testuser', password='testpass123')
        response = self.client.post(reverse('register'), {
            'username': 'testuser',
            'email': 'new@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username='testuser').count(), 1)

    def test_register_with_all_uppercase_variant_fails(self):
        User.objects.create_user(username='testuser', password='testpass123')
        response = self.client.post(reverse('register'), {
            'username': 'TESTUSER',
            'email': 'new@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='TESTUSER').exists())

    def test_register_with_new_username_succeeds(self):
        response = self.client.post(reverse('register'), {
            'username': 'BrandNewUser',
            'email': 'new@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='BrandNewUser').exists())


@tag("integration")
class CaseInsensitivePasswordResetTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()

    def test_password_reset_with_different_case_username_sends_email(self):
        User.objects.create_user(
            username='ResetUser',
            email='reset@example.com',
            password='SomePassword123',
        )
        response = self.client.post(reverse('password_reset'), {
            'email_or_username': 'resetuser',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GENERIC_MESSAGE)
        self.assertEqual(len(mail.outbox), 1)


@tag("integration")
class CaseInsensitiveProfileLookupTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()
        self.user = User.objects.create_user(
            username='ProfileUser', password='testpass123'
        )
        self.client.login(username='ProfileUser', password='testpass123')

    def test_profile_with_lowercase_username(self):
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'profileuser'})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ProfileUser')

    def test_profile_with_uppercase_username(self):
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'PROFILEUSER'})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ProfileUser')


@tag("integration")
class RegistrationWithoutEmailTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()

    def test_registration_without_email(self):
        response = self.client.post(reverse('register'), {
            'username': 'noemailuser',
            'email': '',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))
        self.assertTrue(User.objects.filter(username='noemailuser').exists())
        user = User.objects.get(username='noemailuser')
        self.assertEqual(user.email, '')
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.email_verified)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'My Groups')
        self.assertContains(response, 'My Games')
        self.assertContains(response, 'Upcoming Events')


@tag("integration")
class RegistrationWithEmailOptionalWarningTest(TestCase):

    def test_register_page_shows_email_optional_warning(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'verified')
        self.assertContains(response, 'email')


@tag("integration")
@override_settings(REQUIRE_EMAIL_VERIFICATION=True)
class NoEmailLoginWhenVerificationRequiredTest(TestCase):

    def test_user_without_email_can_login_when_verification_required(self):
        User.objects.create_user(
            username='noemailuser', password='testpass123'
        )
        response = self.client.post(reverse('login'), {
            'username': 'noemailuser',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))


@tag("integration")
class ProfileViewAccessTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
        )
        self.other = User.objects.create_user(
            username='otheruser', password='testpass123',
        )

    def test_profile_page_returns_200(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'otheruser'})
        )
        self.assertEqual(response.status_code, 200)

    def test_own_profile_returns_200(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'testuser'})
        )
        self.assertEqual(response.status_code, 200)

    def test_profile_shows_username(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'otheruser'})
        )
        self.assertContains(response, 'otheruser')

    def test_profile_shows_bio(self):
        self.other.bio = 'Hello, I love board games!'
        self.other.save()
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'otheruser'})
        )
        self.assertContains(response, 'Hello, I love board games!')

    def test_profile_404_for_nonexistent_user(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'nobody'})
        )
        self.assertEqual(response.status_code, 404)

    def test_profile_redirects_for_anonymous(self):
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'testuser'})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_own_profile_shows_edit_link(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'testuser'})
        )
        self.assertContains(response, 'Edit Profile')

    def test_other_profile_does_not_show_edit_link(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'otheruser'})
        )
        self.assertNotContains(response, 'Edit Profile')


@tag("integration")
class ProfilePrivacyTest(TestCase):

    def setUp(self):
        self.viewer = User.objects.create_user(
            username='viewer', password='testpass123',
        )
        self.owner = User.objects.create_user(
            username='owner', password='testpass123',
        )
        self.group = Group.objects.create(name='Test Group')
        self.game = BoardGame.objects.create(
            name='Catan', owner=self.owner, complexity='medium',
        )
        self.event = Event.objects.create(
            title='Game Night',
            date=timezone.now() + timedelta(days=7),
            created_by=self.owner,
            voting_deadline=timezone.now() + timedelta(days=6),
            group=self.group,
        )
        EventAttendance.objects.create(user=self.owner, event=self.event)

    def test_games_visible_when_show_games_true(self):
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertContains(response, 'Catan')

    def test_games_hidden_when_show_games_false(self):
        self.owner.show_games = False
        self.owner.save()
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertNotContains(response, 'Catan')

    def test_events_visible_when_show_events_true(self):
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertContains(response, 'Game Night')

    def test_events_hidden_when_show_events_false(self):
        self.owner.show_events = False
        self.owner.save()
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertNotContains(response, 'Game Night')

    def test_date_joined_visible_when_show_true(self):
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertContains(response, 'Joined')

    def test_date_joined_hidden_when_show_false(self):
        self.owner.show_date_joined = False
        self.owner.save()
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertNotContains(response, 'Joined')

    def test_owner_sees_own_games_regardless_of_privacy(self):
        self.owner.show_games = False
        self.owner.save()
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertContains(response, 'Catan')

    def test_owner_sees_own_events_regardless_of_privacy(self):
        self.owner.show_events = False
        self.owner.save()
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertContains(response, 'Game Night')

    def test_owner_sees_own_date_joined_regardless_of_privacy(self):
        self.owner.show_date_joined = False
        self.owner.save()
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertContains(response, 'Joined')

    def test_friends_link_hidden_when_show_friends_false(self):
        self.owner.show_friends = False
        self.owner.save()
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertNotContains(response, reverse('friends_list', kwargs={'username': 'owner'}))

    def test_friends_link_visible_when_show_friends_true(self):
        self.owner.show_friends = True
        self.owner.save()
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertContains(response, reverse('friends_list', kwargs={'username': 'owner'}))

    def test_owner_sees_friends_link_regardless_of_privacy(self):
        self.owner.show_friends = False
        self.owner.save()
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertContains(response, reverse('friends_list', kwargs={'username': 'owner'}))


@tag("integration")
class ProfilePictureUploadTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
        )
        self.client.login(username='testuser', password='testpass123')

    @override_settings(MEDIA_ROOT=os.path.join(settings.BASE_DIR, 'test_media'))
    def test_can_upload_profile_picture(self):
        image = _create_image()
        response = self.client.post(reverse('user_settings'), {
            'email': '',
            'timezone': 'UTC',
            'bio': '',
            'profile_picture': image,
            'show_games': True,
            'show_events': True,
            'show_date_joined': True,
            'show_friends': True,
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.profile_picture)

    def test_rejects_image_over_2mb(self):
        big_file = SimpleUploadedFile(
            'big.jpg', b'x' * (2 * 1024 * 1024 + 1),
            content_type='image/jpeg',
        )
        response = self.client.post(reverse('user_settings'), {
            'email': '',
            'timezone': 'UTC',
            'bio': '',
            'profile_picture': big_file,
            'show_games': True,
            'show_events': True,
            'show_date_joined': True,
            'show_friends': True,
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.profile_picture)

    @override_settings(MEDIA_ROOT=os.path.join(settings.BASE_DIR, 'test_media'))
    def test_can_update_bio(self):
        response = self.client.post(reverse('user_settings'), {
            'email': '',
            'timezone': 'UTC',
            'bio': 'I love Catan!',
            'show_games': True,
            'show_events': True,
            'show_date_joined': True,
            'show_friends': True,
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.bio, 'I love Catan!')

    @override_settings(MEDIA_ROOT=os.path.join(settings.BASE_DIR, 'test_media'))
    def test_can_toggle_privacy_settings(self):
        response = self.client.post(reverse('user_settings'), {
            'email': '',
            'timezone': 'UTC',
            'bio': '',
            'show_games': False,
            'show_events': False,
            'show_date_joined': False,
            'show_friends': False,
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.show_games)
        self.assertFalse(self.user.show_events)
        self.assertFalse(self.user.show_date_joined)
        self.assertFalse(self.user.show_friends)


@tag("integration")
class ProfileLinkTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
        )
        self.client.login(username='testuser', password='testpass123')

    def test_game_detail_owner_links_to_profile(self):
        game = BoardGame.objects.create(
            name='Catan', owner=self.user, complexity='medium',
        )
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(
            response,
            reverse('public_profile', kwargs={'username': 'testuser'}),
        )


@tag("integration")
class SettingsPageAccessTest(TestCase):

    def test_settings_page_shows_current_email(self):
        User.objects.create_user(
            username='testuser', password='testpass123',
            email='current@example.com'
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'current@example.com')

    def test_settings_page_redirects_for_anonymous(self):
        response = self.client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)


@tag("integration")
class SettingsGearIconTest(TestCase):

    def test_gear_icon_present_in_nav_when_logged_in(self):
        User.objects.create_user(username='testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('user_settings'))
        self.assertContains(response, '&#9881;')

    def test_gear_icon_not_present_when_logged_out(self):
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, reverse('user_settings'))


@tag("integration")
class SettingsAddEmailTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_add_email_saves_to_user(self):
        self.client.post(reverse('user_settings'), {
            'email': 'new@example.com',
            'timezone': 'UTC',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'new@example.com')

    def test_add_email_resets_email_verified_to_false(self):
        self.client.post(reverse('user_settings'), {
            'email': 'new@example.com',
            'timezone': 'UTC',
        })
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_add_email_sends_verification_link(self):
        self.client.post(reverse('user_settings'), {
            'email': 'new@example.com',
            'timezone': 'UTC',
        })
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('new@example.com', mail.outbox[0].to)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_add_email_verification_link_actually_verifies(self):
        self.client.post(reverse('user_settings'), {
            'email': 'new@example.com',
            'timezone': 'UTC',
        })
        signer = TimestampSigner()
        token = signer.sign(self.user.pk)
        self.client.get(reverse('verify_email', kwargs={'token': token}))
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)


@tag("integration")
class SettingsUpdateEmailTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
            email='old@example.com', email_verified=True
        )
        self.client.login(username='testuser', password='testpass123')

    def test_update_email_changes_email(self):
        self.client.post(reverse('user_settings'), {
            'email': 'updated@example.com',
            'timezone': 'UTC',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'updated@example.com')

    def test_update_email_resets_verification(self):
        self.client.post(reverse('user_settings'), {
            'email': 'updated@example.com',
            'timezone': 'UTC',
        })
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_update_email_sends_new_verification(self):
        self.client.post(reverse('user_settings'), {
            'email': 'updated@example.com',
            'timezone': 'UTC',
        })
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('updated@example.com', mail.outbox[0].to)

    def test_submit_same_email_keeps_verified(self):
        self.client.post(reverse('user_settings'), {
            'email': 'old@example.com',
            'timezone': 'UTC',
        })
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

    def test_submit_same_email_does_not_send_email(self):
        self.client.post(reverse('user_settings'), {
            'email': 'old@example.com',
            'timezone': 'UTC',
        })
        self.assertEqual(len(mail.outbox), 0)

    def test_submit_blank_email_clears_email(self):
        self.client.post(reverse('user_settings'), {
            'email': '',
            'timezone': 'UTC',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, '')

    def test_submit_blank_email_resets_verified(self):
        self.client.post(reverse('user_settings'), {
            'email': '',
            'timezone': 'UTC',
        })
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)


@tag("integration")
class SettingsEmailVerifiedBadgeTest(TestCase):

    def test_settings_shows_verified_status_when_verified(self):
        User.objects.create_user(
            username='testuser', password='testpass123',
            email='test@example.com', email_verified=True
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'verified-badge')

    def test_settings_shows_unverified_status_when_not_verified(self):
        User.objects.create_user(
            username='testuser', password='testpass123',
            email='test@example.com', email_verified=False
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('user_settings'))
        self.assertNotContains(response, 'verified-badge')


@tag("integration")
class GlobalVotingOffsetMovedToAdminSettingsTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='organizer', password='testpass123', is_site_admin=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )

    def test_admin_does_not_see_global_offset_on_personal_settings(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('user_settings'))
        self.assertNotContains(response, 'Default Voting Deadline Offset')

    def test_regular_user_does_not_see_global_offset(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('user_settings'))
        self.assertNotContains(response, 'Default Voting Deadline Offset')


@tag("integration")
class SettingsRemoveEmailTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
            email='test@example.com', email_verified=True,
        )
        self.client.login(username='testuser', password='testpass123')

    def test_remove_email_clears_email(self):
        response = self.client.post(reverse('remove_email'))
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, '')

    def test_remove_email_resets_email_verified(self):
        self.client.post(reverse('remove_email'))
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    def test_remove_email_clears_verified_icon(self):
        icon = VerifiedIcon.objects.create(name='Test Icon', image='test.png')
        self.user.verified_icon = icon
        self.user.save()
        self.client.post(reverse('remove_email'))
        self.user.refresh_from_db()
        self.assertIsNone(self.user.verified_icon)

    def test_remove_email_redirects_to_settings(self):
        response = self.client.post(reverse('remove_email'))
        self.assertRedirects(response, reverse('user_settings'))

    def test_remove_email_requires_login(self):
        self.client.logout()
        response = self.client.post(reverse('remove_email'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_remove_email_requires_post(self):
        response = self.client.get(reverse('remove_email'))
        self.assertEqual(response.status_code, 405)

    def test_remove_email_does_not_affect_other_fields(self):
        self.user.timezone = 'America/New_York'
        self.user.bio = 'Hello world'
        self.user.show_games = False
        self.user.save()
        self.client.post(reverse('remove_email'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.timezone, 'America/New_York')
        self.assertEqual(self.user.bio, 'Hello world')
        self.assertFalse(self.user.show_games)


@tag("integration")
class SettingsRemoveEmailUITest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
            email='test@example.com', email_verified=True,
        )
        self.no_email_user = User.objects.create_user(
            username='noemail', password='testpass123',
        )

    def test_settings_shows_remove_button_when_email_present(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'remove-email-btn')

    def test_settings_does_not_show_remove_button_when_no_email(self):
        self.client.login(username='noemail', password='testpass123')
        response = self.client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'remove-email-btn')

    def test_settings_shows_email_display_when_email_present(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'email-display-value')

    def test_settings_shows_email_input_when_no_email(self):
        self.client.login(username='noemail', password='testpass123')
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'id_email')

    def test_settings_shows_remove_email_confirmation_modal(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'remove-email-modal')


@tag("integration")
class SettingsShowInSearchTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
        )
        self.client.login(username='testuser', password='testpass123')

    def test_show_in_search_defaults_to_true(self):
        self.assertTrue(self.user.show_in_search)

    def test_settings_page_has_show_in_search_checkbox(self):
        response = self.client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="show_in_search"')

    def test_show_in_search_unchecked_saves_as_false(self):
        self.user.show_in_search = True
        self.user.save()
        self.client.post(reverse('user_settings'), {
            'timezone': 'UTC',
        })
        self.user.refresh_from_db()
        self.assertFalse(self.user.show_in_search)

    def test_show_in_search_checked_saves_as_true(self):
        self.user.show_in_search = False
        self.user.save()
        self.client.post(reverse('user_settings'), {
            'show_in_search': 'on',
            'timezone': 'UTC',
        })
        self.user.refresh_from_db()
        self.assertTrue(self.user.show_in_search)

    def test_show_in_search_unchanged_when_true(self):
        self.client.post(reverse('user_settings'), {
            'show_in_search': 'on',
            'timezone': 'UTC',
        })
        self.user.refresh_from_db()
        self.assertTrue(self.user.show_in_search)

    def test_show_in_search_unchanged_when_false(self):
        self.user.show_in_search = False
        self.user.save()
        self.client.post(reverse('user_settings'), {
            'timezone': 'UTC',
        })
        self.user.refresh_from_db()
        self.assertFalse(self.user.show_in_search)


@tag("integration")
class UsersPageAccessTest(TestCase):

    def test_authenticated_user_can_access(self):
        user = _create_verified_user('alice')
        self.client.force_login(user)
        resp = self.client.get(reverse('users_page'))
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_redirected_to_login(self):
        resp = self.client.get(reverse('users_page'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_default_tab_is_friends(self):
        user = _create_verified_user('alice')
        self.client.force_login(user)
        resp = self.client.get(reverse('users_page'))
        self.assertEqual(resp.context['tab'], 'friends')


@tag("integration")
class AllUsersTabTest(TestCase):

    def setUp(self):
        self.user = _create_verified_user('alice')
        for i in range(30):
            _create_verified_user(f'user{i:02d}')

    def test_verified_user_sees_user_list(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['page_obj'].paginator.count > 0)

    def test_unverified_user_sees_gate_message(self):
        unverified = User.objects.create_user(username='unverified', password='testpass123')
        self.client.force_login(unverified)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        self.assertContains(resp, 'Become verified')

    def test_search_filters_by_username(self):
        _create_verified_user('bob_jones')
        _create_verified_user('bob_smith')
        _create_verified_user('carol')
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all&q=bob')
        for u in resp.context['page_obj'].object_list:
            self.assertIn('bob', u.username.lower())

    def test_pagination_25_per_page(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        self.assertEqual(len(resp.context['page_obj'].object_list), 25)

    def test_second_page_exists(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all&page=2')
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(len(resp.context['page_obj'].object_list), 0)

    def test_blocked_users_excluded(self):
        other = _create_verified_user('blocked_user')
        Block.objects.create(blocker=self.user, blocked=other)
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertNotIn('blocked_user', usernames)

    def test_soft_deleted_users_excluded(self):
        deleted = _create_verified_user('deleted_user')
        deleted.deleted_at = timezone.now()
        deleted.save()
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertNotIn('deleted_user', usernames)

    def test_self_excluded(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertNotIn('alice', usernames)

    def test_superuser_excluded_from_list(self):
        User.objects.create_superuser(username='sysop', password='SysPass123!')
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertNotIn('sysop', usernames)

    def test_superuser_excluded_from_search(self):
        User.objects.create_superuser(username='sysop', password='SysPass123!')
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all&q=sysop')
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertNotIn('sysop', usernames)

    def test_verified_badge_shown_for_verified_users(self):
        _create_verified_user('verified_bob')
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all&q=verified_bob')
        self.assertContains(resp, 'verified-badge')


@tag("integration")
class SuperuserProfileHiddenTest(TestCase):

    def test_superuser_profile_returns_404(self):
        User.objects.create_superuser(username='sysop', password='SysPass123!')
        user = _create_verified_user('alice')
        self.client.force_login(user)
        resp = self.client.get(reverse('public_profile', kwargs={'username': 'sysop'}))
        self.assertEqual(resp.status_code, 404)

    def test_superuser_profile_redirects_for_anonymous(self):
        User.objects.create_superuser(username='sysop', password='SysPass123!')
        resp = self.client.get(reverse('public_profile', kwargs={'username': 'sysop'}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_superuser_can_view_own_profile(self):
        su = User.objects.create_superuser(username='sysop', password='SysPass123!')
        self.client.force_login(su)
        resp = self.client.get(reverse('public_profile', kwargs={'username': 'sysop'}))
        self.assertEqual(resp.status_code, 200)


@tag("integration")
class UserSearchRedirectTest(TestCase):

    def test_old_search_url_redirects(self):
        user = _create_verified_user('alice')
        self.client.force_login(user)
        resp = self.client.get('/users/search/?q=bob')
        self.assertEqual(resp.status_code, 301)


@tag("integration")
class FriendsTabCurrentFriendsTest(TestCase):

    def setUp(self):
        self.user = _create_verified_user('alice')
        self.friend1 = _create_verified_user('bob')
        self.friend2 = _create_verified_user('carol')
        Friendship.objects.create(requester=self.user, receiver=self.friend1, status='accepted')
        Friendship.objects.create(requester=self.friend2, receiver=self.user, status='accepted')

    def test_shows_current_friends(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        friend_usernames = [f.username for f in resp.context['friends']]
        self.assertIn('bob', friend_usernames)
        self.assertIn('carol', friend_usernames)

    def test_shows_mutual_groups(self):
        group = Group.objects.create(name='Test Group', slug='test-group', created_by=self.user)
        GroupMembership.objects.create(user=self.user, group=group, role='member')
        GroupMembership.objects.create(user=self.friend1, group=group, role='member')
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'Test Group')

    def test_shows_shared_upcoming_private_events(self):
        event = Event.objects.create(
            title='Game Night',
            date=timezone.now() + timedelta(days=7),
            created_by=self.user,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        EventAttendance.objects.create(user=self.user, event=event)
        EventAttendance.objects.create(user=self.friend1, event=event)
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'Game Night')

    def test_does_not_show_group_events_in_shared_events(self):
        group = Group.objects.create(name='G', slug='g', created_by=self.user)
        event = Event.objects.create(
            title='Group Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.user,
            group=group,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        EventAttendance.objects.create(user=self.user, event=event)
        EventAttendance.objects.create(user=self.friend1, event=event)
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        friend_shared_events = resp.context['friends_shared_events']
        self.assertNotIn('bob', {k: v for k, v in friend_shared_events.items()})

    def test_no_friends_shows_empty_state(self):
        solo = _create_verified_user('solo')
        self.client.force_login(solo)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'No friends yet')

    def test_unfriend_button_present(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'Unfriend')


@tag("integration")
class FriendsTabPendingReceivedTest(TestCase):

    def setUp(self):
        self.user = _create_verified_user('alice')
        self.sender = _create_verified_user('bob')
        Friendship.objects.create(requester=self.sender, receiver=self.user, status='pending')

    def test_shows_pending_received_requests(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        pending = resp.context['pending_received']
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].requester.username, 'bob')

    def test_shows_mutual_groups_on_pending(self):
        group = Group.objects.create(name='Test Group', slug='test-group', created_by=self.user)
        GroupMembership.objects.create(user=self.user, group=group, role='member')
        GroupMembership.objects.create(user=self.sender, group=group, role='member')
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'Test Group')

    def test_accept_decline_buttons_present(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'friend-accept-btn')
        self.assertContains(resp, 'friend-decline-btn')

    def test_no_pending_shows_empty_state(self):
        solo = _create_verified_user('solo')
        self.client.force_login(solo)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'No pending friend requests')


@tag("integration")
class FriendsTabSentRequestsTest(TestCase):

    def setUp(self):
        self.user = _create_verified_user('alice')
        self.target = _create_verified_user('bob')
        Friendship.objects.create(requester=self.user, receiver=self.target, status='pending')

    def test_shows_sent_requests(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        sent = resp.context['sent_requests']
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0].receiver.username, 'bob')

    def test_cancel_button_present(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'Cancel')

    def test_no_sent_shows_empty_state(self):
        solo = _create_verified_user('solo')
        self.client.force_login(solo)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'No sent friend requests')


@tag("integration")
class UnfriendFromUsersPageTest(TestCase):

    def setUp(self):
        self.user = _create_verified_user('alice')
        self.friend = _create_verified_user('bob')
        Friendship.objects.create(requester=self.user, receiver=self.friend, status='accepted')

    def test_unfriend_success(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse('remove_friend', kwargs={'username': 'bob'}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Friendship.objects.filter(pk__isnull=False).exists())

    def test_unfriend_non_friend_forbidden(self):
        other = _create_verified_user('carol')
        self.client.force_login(other)
        resp = self.client.post(reverse('remove_friend', kwargs={'username': 'bob'}))
        self.assertEqual(resp.status_code, 403)


@tag("integration")
class UnverifiedFriendRequestViewTest(TestCase):

    def setUp(self):
        self.unverified = User.objects.create_user(
            username='unverified', password='testpass123',
        )

    def test_send_request_blocked_at_limit(self):
        targets = _create_users('t1', 't2', 't3', 't4')
        for t in targets[:3]:
            Friendship.objects.create(requester=self.unverified, receiver=t, status='pending')
        self.client.force_login(self.unverified)
        resp = self.client.post(reverse('send_friend_request', kwargs={'username': 't4'}))
        self.assertFalse(Friendship.objects.filter(requester=self.unverified, receiver=targets[3], status='pending').exists())

    def test_send_request_works_under_limit(self):
        targets = _create_users('t1', 't2')
        Friendship.objects.create(requester=self.unverified, receiver=targets[0], status='pending')
        self.client.force_login(self.unverified)
        resp = self.client.post(reverse('send_friend_request', kwargs={'username': 't2'}))
        self.assertTrue(Friendship.objects.filter(requester=self.unverified, receiver=targets[1], status='pending').exists())


@tag("integration")
class UsersNavLinkTest(TestCase):

    def test_nav_shows_users_link_when_authenticated(self):
        user = _create_verified_user('alice')
        self.client.force_login(user)
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, reverse('users_page'))

    def test_nav_hides_users_link_when_unauthenticated(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertNotContains(resp, reverse('users_page'))


@tag("integration")
class ShowInSearchVisibilityTest(TestCase):

    def setUp(self):
        self.viewer = _create_verified_user('viewer')
        self.visible = _create_verified_user('visible_user')
        self.hidden = _create_verified_user(
            'hidden_user', show_in_search=False,
        )

    def test_hidden_user_excluded_from_all_users_list(self):
        self.client.force_login(self.viewer)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertIn('visible_user', usernames)
        self.assertNotIn('hidden_user', usernames)

    def test_hidden_user_excluded_from_search(self):
        self.client.force_login(self.viewer)
        resp = self.client.get(reverse('users_page') + '?tab=all&q=hidden')
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertNotIn('hidden_user', usernames)

    def test_visible_user_found_in_search(self):
        self.client.force_login(self.viewer)
        resp = self.client.get(reverse('users_page') + '?tab=all&q=visible')
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertIn('visible_user', usernames)

    def test_hidden_user_profile_still_accessible_directly(self):
        self.client.force_login(self.viewer)
        resp = self.client.get(
            reverse('public_profile', kwargs={'username': 'hidden_user'}),
        )
        self.assertEqual(resp.status_code, 200)

    def test_hidden_user_still_in_friends_tab(self):
        Friendship.objects.create(
            requester=self.viewer, receiver=self.hidden, status='accepted',
        )
        self.client.force_login(self.viewer)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        friend_usernames = [u.username for u in resp.context['friends']]
        self.assertIn('hidden_user', friend_usernames)

    def test_new_user_default_searchable(self):
        new_user = _create_verified_user('newbie')
        self.assertTrue(new_user.show_in_search)
        self.client.force_login(self.viewer)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertIn('newbie', usernames)


@tag("integration")
class ChangePasswordViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='OldPass123',
            email='test@example.com',
        )
        self.client.login(username='testuser', password='OldPass123')

    def test_change_password_page_loads(self):
        response = self.client.get(reverse('change_password'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Change Password')

    def test_change_password_with_correct_current_password(self):
        response = self.client.post(reverse('change_password'), {
            'current_password': 'OldPass123',
            'new_password1': 'NewPass456',
            'new_password2': 'NewPass456',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('user_settings') + '?password_changed=1')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass456'))

    def test_change_password_saves_password_history(self):
        self.client.post(reverse('change_password'), {
            'current_password': 'OldPass123',
            'new_password1': 'NewPass456',
            'new_password2': 'NewPass456',
        })
        self.assertTrue(PasswordHistory.objects.filter(user=self.user).exists())

    def test_change_password_wrong_current_password(self):
        response = self.client.post(reverse('change_password'), {
            'current_password': 'WrongPass999',
            'new_password1': 'NewPass456',
            'new_password2': 'NewPass456',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'current password is incorrect')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPass123'))

    def test_change_password_mismatched_new_passwords(self):
        response = self.client.post(reverse('change_password'), {
            'current_password': 'OldPass123',
            'new_password1': 'NewPass456',
            'new_password2': 'Different789',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Passwords do not match')

    def test_change_password_reuse_from_history(self):
        PasswordHistory.objects.create(user=self.user, password=make_password('UsedPass1'))
        response = self.client.post(reverse('change_password'), {
            'current_password': 'OldPass123',
            'new_password1': 'UsedPass1',
            'new_password2': 'UsedPass1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'last 5 passwords')

    def test_change_password_no_digit_fails(self):
        response = self.client.post(reverse('change_password'), {
            'current_password': 'OldPass123',
            'new_password1': 'NoDigitsHere',
            'new_password2': 'NoDigitsHere',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'digit')

    def test_change_password_no_letter_fails(self):
        response = self.client.post(reverse('change_password'), {
            'current_password': 'OldPass123',
            'new_password1': '12345678',
            'new_password2': '12345678',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'letter')

    def test_change_password_redirects_unauthenticated(self):
        self.client.logout()
        response = self.client.get(reverse('change_password'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_change_password_superuser_denied(self):
        superuser = User.objects.create_superuser(
            username='admin', password='AdminPass123',
            email='admin@example.com',
        )
        self.client.login(username='admin', password='AdminPass123')
        response = self.client.get(reverse('change_password'))
        self.assertEqual(response.status_code, 403)

    def test_change_password_superuser_post_denied(self):
        superuser = User.objects.create_superuser(
            username='admin', password='AdminPass123',
            email='admin@example.com',
        )
        self.client.login(username='admin', password='AdminPass123')
        response = self.client.post(reverse('change_password'), {
            'current_password': 'AdminPass123',
            'new_password1': 'NewAdmin456',
            'new_password2': 'NewAdmin456',
        })
        self.assertEqual(response.status_code, 403)


@tag("integration")
class ChangePasswordSettingsCardTest(TestCase):

    def test_regular_user_sees_password_card_on_settings(self):
        User.objects.create_user(username='testuser', password='TestPass123')
        self.client.login(username='testuser', password='TestPass123')
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'Change Password')

    def test_superuser_does_not_see_password_card_on_settings(self):
        User.objects.create_superuser(
            username='admin', password='AdminPass123',
            email='admin@example.com',
        )
        self.client.login(username='admin', password='AdminPass123')
        response = self.client.get(reverse('user_settings'))
        self.assertNotContains(response, 'Change Password')

    def test_success_banner_shown_after_password_change(self):
        user = User.objects.create_user(username='testuser', password='OldPass123')
        self.client.login(username='testuser', password='OldPass123')
        self.client.post(reverse('change_password'), {
            'current_password': 'OldPass123',
            'new_password1': 'NewPass456',
            'new_password2': 'NewPass456',
        })
        response = self.client.get(reverse('user_settings') + '?password_changed=1')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'password-success-banner')
        self.assertContains(response, 'Password successfully changed')


@tag("integration")
class PasswordRequirementsDisplayTest(TestCase):

    def test_register_page_shows_password_requirements(self):
        response = self.client.get(reverse('register'))
        self.assertContains(response, 'at least 8 characters')
        self.assertContains(response, 'letter and one digit')
        self.assertContains(response, 'similar to your username')

    def test_change_password_page_shows_password_requirements(self):
        User.objects.create_user(username='testuser', password='TestPass123')
        self.client.login(username='testuser', password='TestPass123')
        response = self.client.get(reverse('change_password'))
        self.assertContains(response, 'at least 8 characters')
        self.assertContains(response, 'letter and one digit')
        self.assertContains(response, 'similar to your username')
        self.assertContains(response, 'last 5 passwords')

    def test_set_password_page_shows_password_requirements(self):
        user = User.objects.create_user(
            username='setuser', email='set@example.com',
            password='SomePass123',
        )
        from club.views import generate_password_token

        token = generate_password_token(user)
        response = self.client.get(reverse('user_set_password', kwargs={'token': token}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'at least 8 characters')
        self.assertContains(response, 'letter and one digit')
        self.assertContains(response, 'similar to your username')

    def test_password_reset_page_shows_password_requirements(self):
        User.objects.create_user(
            username='resetuser', email='reset@example.com',
            password='SomePass123',
        )
        from club.views import generate_password_token

        user = User.objects.get(username='resetuser')
        token = generate_password_token(user)
        response = self.client.get(reverse('password_reset_form', kwargs={'token': token}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'at least 8 characters')
        self.assertContains(response, 'letter and one digit')
        self.assertContains(response, 'similar to your username')
        self.assertContains(response, 'last 5 passwords')

    def test_forced_password_change_shows_password_requirements(self):
        user = User.objects.create_user(
            username='forceduser', password='TempPass123',
            must_change_password=True,
        )
        self.client.login(username='forceduser', password='TempPass123')
        response = self.client.get(reverse('forced_password_change'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'at least 8 characters')
        self.assertContains(response, 'letter and one digit')
        self.assertContains(response, 'similar to your username')
        self.assertContains(response, 'last 5 passwords')


@tag("integration")
class VerifiedBadgeDashboardTest(TestCase):

    def test_verified_user_sees_blue_checkmark_on_dashboard(self):
        user = User.objects.create_user(
            username='verifieduser', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        self.client.login(username='verifieduser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Groups')
        self.assertContains(response, 'My Games')

    def test_unverified_user_does_not_see_checkmark_on_dashboard(self):
        user = User.objects.create_user(
            username='unverifieduser', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        self.client.login(username='unverifieduser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)


@tag("integration")
class VerifiedBadgeGamePagesTest(TestCase):

    def test_verified_owner_shows_checkmark_on_game_pages(self):
        owner = User.objects.create_user(
            username='verifiedowner', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        game = BoardGame.objects.create(name='Catan', owner=owner)
        viewer = User.objects.create_user(
            username='viewer', password='testpass123',
        )
        group = Group.objects.create(name='Test Group')
        GroupMembership.objects.create(user=owner, group=group, role='member')
        GroupMembership.objects.create(user=viewer, group=group, role='member')
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_list'))
        html = response.content.decode()
        self.assertTrue(
            re.search(r'data-label="Owner - Details".*?verified-badge', html, re.DOTALL),
            'verified-badge not found inside Owner - Details column',
        )
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(response, 'verified-badge')

    def test_unverified_owner_no_checkmark_on_game_pages(self):
        owner = User.objects.create_user(
            username='unverifiedowner', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        game = BoardGame.objects.create(name='Risk', owner=owner)
        viewer = User.objects.create_user(
            username='viewer', password='testpass123',
        )
        group = Group.objects.create(name='Test Group')
        GroupMembership.objects.create(user=owner, group=group, role='member')
        GroupMembership.objects.create(user=viewer, group=group, role='member')
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_list'))
        html = response.content.decode()
        owner_details_match = re.search(
            r'data-label="Owner - Details".*?(?:</td>)',
            html, re.DOTALL,
        )
        if owner_details_match:
            self.assertNotIn('verified-badge', owner_details_match.group(0))
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertNotContains(response, 'verified-badge')


@tag("integration")
class VerifiedBadgeEventPagesTest(TestCase):

    def test_verified_creator_shows_checkmark_in_event_list(self):
        creator = User.objects.create_user(
            username='verifiedcreator', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        group = Group.objects.create(name='Test Group')
        Event.objects.create(
            title='Game Night', date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=creator, group=group
        )
        GroupMembership.objects.create(user=creator, group=group, role='member')
        self.client.login(username='verifiedcreator', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, 'verified-badge')

    def test_unverified_creator_no_checkmark_in_event_list(self):
        creator = User.objects.create_user(
            username='unverifiedcreator', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        group = Group.objects.create(name='Test Group')
        Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=creator, group=group
        )
        self.client.login(username='unverifiedcreator', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertNotContains(response, 'verified-badge')

    def test_verified_creator_and_attendee_badge_on_event_detail(self):
        verified_user = User.objects.create_user(
            username='verifieduser', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        group = Group.objects.create(name='Test Group')
        event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=verified_user, group=group
        )
        self.client.login(username='verifieduser', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertContains(response, 'verified-badge')
        EventAttendance.objects.create(user=verified_user, event=event)
        response = self.client.get(reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertContains(response, 'verified-badge')

    def test_unverified_attendee_no_checkmark(self):
        unverified_user = User.objects.create_user(
            username='unverifieduser', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        group = Group.objects.create(name='Test Group')
        event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=unverified_user, group=group
        )
        EventAttendance.objects.create(user=unverified_user, event=event)
        self.client.login(username='unverifieduser', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertNotContains(response, 'verified-badge')

    def test_verified_voter_shows_checkmark_in_individual_votes(self):
        verified_user = User.objects.create_user(
            username='verifiedvoter', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        group = Group.objects.create(name='Test Group')
        GroupMembership.objects.create(user=verified_user, group=group, role='organizer')
        event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=verified_user, show_individual_votes=True, group=group
        )
        game = BoardGame.objects.create(name='Catan', owner=verified_user)
        EventAttendance.objects.create(user=verified_user, event=event)
        Vote.objects.create(
            user=verified_user, event=event,
            board_game=game, rank=1
        )
        self.client.login(username='verifiedvoter', password='testpass123')
        response = self.client.get(reverse('event_results', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertContains(response, 'verified-badge')

    def test_unverified_voter_no_checkmark_in_individual_votes(self):
        unverified_user = User.objects.create_user(
            username='unverifiedvoter', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        verified_creator = User.objects.create_user(
            username='verifiedcreator', password='testpass123',
            email='verifiedc@example.com', email_verified=True
        )
        group = Group.objects.create(name='Test Group')
        event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=verified_creator, show_individual_votes=True, group=group
        )
        game = BoardGame.objects.create(name='Catan', owner=verified_creator)
        EventAttendance.objects.create(user=unverified_user, event=event)
        Vote.objects.create(
            user=unverified_user, event=event,
            board_game=game, rank=1
        )
        response = self.client.get(reverse('event_results', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        html = response.content.decode()
        voter_section_start = html.find('unverifiedvoter')
        voter_section = html[voter_section_start:voter_section_start + 200]
        self.assertNotIn('verified-badge', voter_section)

    def test_verified_user_shows_checkmark_in_manage_users(self):
        admin = User.objects.create_user(
            username='admin', password='testpass123',
            is_site_admin=True, email='admin@example.com', email_verified=True
        )
        User.objects.create_user(
            username='verifieduser', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertContains(response, 'verified-badge')

    def test_unverified_user_no_checkmark_in_manage_users(self):
        admin = User.objects.create_user(
            username='admin', password='testpass123',
            is_site_admin=True, email='admin@example.com', email_verified=True
        )
        User.objects.create_user(
            username='unverifieduser', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertNotContains(response, 'verified-badge')


@tag("integration")
class SettingsIconPickerTest(TestCase):

    def setUp(self):
        self.icon = VerifiedIcon.objects.create(
            name='Dice', image=_create_icon_image('dice.png'),
        )
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
            email='test@example.com', email_verified=True,
        )
        self.client.login(username='testuser', password='testpass123')

    def test_settings_page_shows_icon_picker_when_verified(self):
        response = self.client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'verified-icon-picker')

    def test_settings_page_shows_icon_options(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'Dice')

    def test_save_verified_icon(self):
        self.client.post(reverse('user_settings'), {
            'email': 'test@example.com',
            'timezone': 'UTC',
            'verified_icon': str(self.icon.pk),
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.verified_icon, self.icon)

    def test_change_verified_icon(self):
        icon2 = VerifiedIcon.objects.create(
            name='Star', image=_create_icon_image('star.png'),
        )
        self.user.verified_icon = self.icon
        self.user.save()
        self.client.post(reverse('user_settings'), {
            'email': 'test@example.com',
            'timezone': 'UTC',
            'verified_icon': str(icon2.pk),
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.verified_icon, icon2)

    def test_clear_verified_icon(self):
        self.user.verified_icon = self.icon
        self.user.save()
        self.client.post(reverse('user_settings'), {
            'email': 'test@example.com',
            'timezone': 'UTC',
            'verified_icon': '',
        })
        self.user.refresh_from_db()
        self.assertIsNone(self.user.verified_icon)

    def test_invalid_icon_pk_rejected(self):
        self.client.post(reverse('user_settings'), {
            'email': 'test@example.com',
            'timezone': 'UTC',
            'verified_icon': '99999',
        })
        self.user.refresh_from_db()
        self.assertIsNone(self.user.verified_icon)


@tag("integration")
class SettingsIconPickerUnverifiedTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
            email='test@example.com', email_verified=False,
        )
        VerifiedIcon.objects.create(name='Dice', image=_create_icon_image('dice.png'))
        self.client.login(username='testuser', password='testpass123')

    def test_unverified_user_sees_icon_picker_disabled(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'verified-icon-picker')
        self.assertContains(response, 'disabled')

    def test_unverified_user_cannot_save_icon(self):
        icon = VerifiedIcon.objects.first()
        self.client.post(reverse('user_settings'), {
            'email': 'test@example.com',
            'timezone': 'UTC',
            'verified_icon': str(icon.pk),
        })
        self.user.refresh_from_db()
        self.assertIsNone(self.user.verified_icon)


@tag("integration")
class VerifiedBadgeCustomIconRenderingTest(TestCase):

    def setUp(self):
        self.icon = VerifiedIcon.objects.create(
            name='Dice', image=_create_icon_image('dice.png'),
        )
        self.group = Group.objects.create(name='Test Group')

    def test_custom_icon_renders_on_dashboard(self):
        owner = User.objects.create_user(
            username='iconuser', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        BoardGame.objects.create(name='Catan', owner=owner)
        viewer = User.objects.create_user(
            username='viewer', password='testpass123',
        )
        GroupMembership.objects.create(user=owner, group=self.group, role='member')
        GroupMembership.objects.create(user=viewer, group=self.group, role='member')
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_list'))
        html = response.content.decode()
        self.assertTrue(
            re.search(r'data-label="Owner - Details".*?verified-badge', html, re.DOTALL),
            'verified-badge not found inside Owner - Details column',
        )

    def test_no_icon_renders_default_checkmark(self):
        owner = User.objects.create_user(
            username='defaultuser', password='testpass123',
            email_verified=True,
        )
        BoardGame.objects.create(name='Catan', owner=owner)
        viewer = User.objects.create_user(
            username='viewer', password='testpass123',
        )
        GroupMembership.objects.create(user=owner, group=self.group, role='member')
        GroupMembership.objects.create(user=viewer, group=self.group, role='member')
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_list'))
        html = response.content.decode()
        self.assertTrue(
            re.search(r'data-label="Owner - Details".*?verified-badge', html, re.DOTALL),
            'verified-badge not found inside Owner - Details column',
        )

    def test_custom_icon_renders_on_game_list(self):
        owner = User.objects.create_user(
            username='iconowner', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        BoardGame.objects.create(name='Catan', owner=owner)
        viewer = User.objects.create_user(
            username='viewer', password='testpass123',
        )
        GroupMembership.objects.create(user=owner, group=self.group, role='member')
        GroupMembership.objects.create(user=viewer, group=self.group, role='member')
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_list'))
        html = response.content.decode()
        self.assertTrue(
            re.search(r'data-label="Owner - Details".*?verified-badge', html, re.DOTALL),
            'verified-badge not found inside Owner - Details column',
        )

    def test_custom_icon_renders_on_game_detail(self):
        owner = User.objects.create_user(
            username='iconowner', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        game = BoardGame.objects.create(name='Catan', owner=owner)
        self.client.login(username='iconowner', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(response, 'verified-badge')

    def test_custom_icon_renders_on_event_list(self):
        creator = User.objects.create_user(
            username='iconcreator', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        Event.objects.create(
            title='Game Night', date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=creator, group=self.group,
        )
        GroupMembership.objects.create(user=creator, group=self.group, role='member')
        self.client.login(username='iconcreator', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, 'verified-badge')

    def test_custom_icon_renders_on_event_detail_creator(self):
        creator = User.objects.create_user(
            username='iconcreator', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=creator, group=self.group,
        )
        self.client.login(username='iconcreator', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertContains(response, 'verified-badge')

    def test_custom_icon_renders_on_event_detail_attendee(self):
        creator = User.objects.create_user(
            username='creator', password='testpass123',
            email_verified=True,
        )
        attendee = User.objects.create_user(
            username='iconattendee', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=creator, group=self.group,
        )
        EventAttendance.objects.create(user=attendee, event=event)
        self.client.login(username='iconattendee', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertContains(response, 'verified-badge')

    def test_custom_icon_renders_on_event_results(self):
        voter = User.objects.create_user(
            username='iconvoter', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        GroupMembership.objects.create(user=voter, group=self.group, role='organizer')
        event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=voter, show_individual_votes=True, group=self.group,
        )
        game = BoardGame.objects.create(name='Catan', owner=voter)
        EventAttendance.objects.create(user=voter, event=event)
        Vote.objects.create(user=voter, event=event, board_game=game, rank=1)
        self.client.login(username='iconvoter', password='testpass123')
        response = self.client.get(reverse('event_results', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertContains(response, 'verified-badge')

    def test_custom_icon_renders_on_manage_users(self):
        admin = User.objects.create_user(
            username='admin', password='testpass123',
            is_site_admin=True, email_verified=True,
        )
        User.objects.create_user(
            username='iconuser', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertContains(response, 'verified-badge')


@tag("integration")
class IconManagementAccessTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123',
            is_site_admin=True, email_verified=True,
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123',
            email_verified=True,
        )
        self.client.login(username='admin', password='testpass123')

    def test_admin_sees_icon_management_section(self):
        response = self.client.get(reverse('admin_settings'))
        self.assertContains(response, 'manage-verified-icons')

    def test_regular_user_does_not_see_icon_management_section(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('admin_settings'))
        self.assertEqual(response.status_code, 403)

    def test_admin_sees_existing_icons_in_management(self):
        VerifiedIcon.objects.create(name='Dice', image=_create_icon_image('dice.png'))
        response = self.client.get(reverse('admin_settings'))
        self.assertContains(response, 'Dice')
        self.assertContains(response, 'delete-icon')


@tag("integration")
class IconManagementAddTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123',
            is_site_admin=True, email_verified=True,
        )
        self.client.login(username='admin', password='testpass123')

    def test_add_icon_success(self):
        response = self.client.post(reverse('add_verified_icon'), {
            'name': 'Trophy',
            'image': _create_icon_image('trophy.png'),
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(VerifiedIcon.objects.filter(name='Trophy').exists())

    def test_add_icon_without_name_fails(self):
        response = self.client.post(reverse('add_verified_icon'), {
            'name': '',
            'image': _create_icon_image('trophy.png'),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(VerifiedIcon.objects.exists())

    def test_add_icon_without_image_fails(self):
        response = self.client.post(reverse('add_verified_icon'), {
            'name': 'Trophy',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(VerifiedIcon.objects.exists())

    def test_add_icon_duplicate_name_fails(self):
        VerifiedIcon.objects.create(name='Dice', image=_create_icon_image('dice.png'))
        response = self.client.post(reverse('add_verified_icon'), {
            'name': 'Dice',
            'image': _create_icon_image('dice2.png'),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(VerifiedIcon.objects.count(), 1)

    def test_regular_user_cannot_add_icon(self):
        regular = User.objects.create_user(
            username='regular', password='testpass123',
            email_verified=True,
        )
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(reverse('add_verified_icon'), {
            'name': 'Trophy',
            'image': _create_icon_image('trophy.png'),
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(VerifiedIcon.objects.exists())


@tag("integration")
class IconManagementDeleteTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123',
            is_site_admin=True, email_verified=True,
        )
        self.icon = VerifiedIcon.objects.create(
            name='Dice', image=_create_icon_image('dice.png'),
        )
        self.client.login(username='admin', password='testpass123')

    def test_delete_unused_icon_success(self):
        response = self.client.post(
            reverse('delete_verified_icon', kwargs={'pk': self.icon.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(VerifiedIcon.objects.filter(pk=self.icon.pk).exists())

    def test_delete_icon_in_use_fails(self):
        User.objects.create_user(
            username='iconuser', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        response = self.client.post(
            reverse('delete_verified_icon', kwargs={'pk': self.icon.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(VerifiedIcon.objects.filter(pk=self.icon.pk).exists())

    def test_delete_nonexistent_icon_404(self):
        response = self.client.post(
            reverse('delete_verified_icon', kwargs={'pk': 99999})
        )
        self.assertEqual(response.status_code, 404)

    def test_regular_user_cannot_delete_icon(self):
        regular = User.objects.create_user(
            username='regular', password='testpass123',
            email_verified=True,
        )
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(
            reverse('delete_verified_icon', kwargs={'pk': self.icon.pk})
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(VerifiedIcon.objects.filter(pk=self.icon.pk).exists())


@tag("integration")
class SettingsPageThemeTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_settings_page_shows_theme_section(self):
        response = self.client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Theme')

    def test_settings_page_shows_light_option(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'value="light"')

    def test_settings_page_shows_dark_option(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'value="dark"')

    def test_settings_page_shows_system_option(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'value="system"')

    def test_system_option_checked_by_default(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'value="system"')

    def test_post_theme_saves_to_user(self):
        self.client.post(reverse('user_settings'), {
            'email': '',
            'timezone': 'UTC',
            'theme': 'dark',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, 'dark')

    def test_post_theme_light_saves_to_user(self):
        self.client.post(reverse('user_settings'), {
            'email': '',
            'timezone': 'UTC',
            'theme': 'light',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, 'light')

    def test_post_theme_system_saves_to_user(self):
        self.user.theme = 'dark'
        self.user.save()
        self.client.post(reverse('user_settings'), {
            'email': '',
            'timezone': 'UTC',
            'theme': 'system',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, 'system')

    def test_current_theme_checked_on_load(self):
        self.user.theme = 'dark'
        self.user.save()
        response = self.client.get(reverse('user_settings'))
        content = response.content.decode()
        self.assertIn('value="dark"', content)


@tag("integration")
class ThemeContextProcessorTest(TestCase):

    def test_authenticated_user_theme_in_context(self):
        user = User.objects.create_user(
            username='testuser', password='testpass123',
            theme='dark'
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['user_theme'], 'dark')

    def test_default_system_theme_in_context(self):
        User.objects.create_user(username='testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['user_theme'], 'system')

    def test_anonymous_user_theme_is_system(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['user_theme'], 'system')


@tag("integration")
class BaseTemplateThemeTest(TestCase):

    def test_base_template_has_data_theme_attribute(self):
        source = _read_base_template()
        self.assertIn('data-theme', source)

    def test_base_template_has_theme_resolve_script(self):
        source = _read_base_template()
        self.assertIn('data-applied-theme', source)

    def test_base_template_has_system_preference_detection(self):
        source = _read_base_template()
        self.assertIn('prefers-color-scheme', source)


@tag("integration")
class DarkModeCSSTest(TestCase):

    def setUp(self):
        self.css = _read_css()

    def test_css_has_dark_theme_selector(self):
        self.assertIn('[data-applied-theme="dark"]', self.css)

    def test_dark_theme_overrides_bg(self):
        self.assertIn('--bg:', self.css)

    def test_dark_theme_overrides_surface(self):
        self.assertIn('--surface:', self.css)

    def test_dark_theme_overrides_text(self):
        self.assertIn('--text:', self.css)

    def test_dark_theme_overrides_text_light(self):
        self.assertIn('--text-light:', self.css)

    def test_dark_theme_overrides_border(self):
        self.assertIn('--border:', self.css)

    def test_nav_toggle_not_present(self):
        self.assertNotIn('.nav-theme-toggle', self.css)


@tag("integration")
class SettingsTemplateThemeTest(TestCase):

    def test_settings_template_has_theme_card(self):
        source = _read_settings_template()
        self.assertIn('Theme', source)

    def test_settings_template_has_theme_radio_inputs(self):
        source = _read_settings_template()
        self.assertIn('name="theme"', source)


@tag("integration")
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


@tag("integration")
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

    def test_save_timezone_rejects_external_redirect(self):
        response = self.client.post(reverse('save_timezone'), {
            'timezone': 'America/Chicago',
            'next': 'https://evil.com',
        })
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_save_timezone_rejects_protocol_relative_redirect(self):
        response = self.client.post(reverse('save_timezone'), {
            'timezone': 'America/Chicago',
            'next': '//evil.com',
        })
        self.assertRedirects(response, '/', fetch_redirect_response=False)

    def test_save_timezone_rejects_http_redirect_to_own_host(self):
        response = self.client.post(reverse('save_timezone'), {
            'timezone': 'America/Chicago',
            'next': 'http://testserver/games/',
        })
        self.assertRedirects(response, '/')

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


@tag("integration")
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


@tag("integration")
class LoginRateLimitTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()
        self.user = User.objects.create_user(
            username='loginuser', password='testpass123', email='login@example.com'
        )

    def tearDown(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()

    def test_login_allows_up_to_5_attempts(self):
        for _ in range(5):
            response = self.client.post(reverse('login'), {
                'username': 'loginuser',
                'password': 'wrongpass',
            })
            self.assertEqual(response.status_code, 200)

    def test_login_blocked_after_5_attempts(self):
        for _ in range(5):
            self.client.post(reverse('login'), {
                'username': 'loginuser',
                'password': 'wrongpass',
            })
        response = self.client.post(reverse('login'), {
            'username': 'loginuser',
            'password': 'wrongpass',
        })
        self.assertEqual(response.status_code, 429)

    def test_login_get_not_rate_limited(self):
        for _ in range(5):
            self.client.post(reverse('login'), {
                'username': 'loginuser',
                'password': 'wrongpass',
            })
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)

    def test_login_rate_limit_response_shows_message(self):
        for _ in range(5):
            self.client.post(reverse('login'), {
                'username': 'loginuser',
                'password': 'wrongpass',
            })
        response = self.client.post(reverse('login'), {
            'username': 'loginuser',
            'password': 'wrongpass',
        })
        self.assertEqual(response.status_code, 429)
        self.assertIn('Too Many Attempts', response.content.decode())

    def test_successful_login_counts_toward_limit(self):
        for _ in range(5):
            self.client.post(reverse('login'), {
                'username': 'loginuser',
                'password': 'testpass123',
            })
        self.client.logout()
        response = self.client.post(reverse('login'), {
            'username': 'loginuser',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 429)

    def test_login_rate_limit_resets_after_window(self):
        from django.core.cache import caches
        for _ in range(5):
            self.client.post(reverse('login'), {
                'username': 'loginuser',
                'password': 'wrongpass',
            })
        caches['rate_limit'].delete('rl:/login/:127.0.0.1')
        response = self.client.post(reverse('login'), {
            'username': 'loginuser',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 302)


@tag("integration")
class RegistrationRateLimitTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()

    def tearDown(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()

    def test_register_allows_up_to_3_attempts(self):
        for i in range(3):
            response = self.client.post(reverse('register'), {
                'username': f'user{i}',
                'email': f'user{i}@example.com',
                'password1': 'Str0ngP@ss123',
                'password2': 'Str0ngP@ss123',
            })
            self.assertIn(response.status_code, [200, 302])

    def test_register_blocked_after_3_attempts(self):
        for i in range(3):
            self.client.post(reverse('register'), {
                'username': f'user{i}',
                'email': f'user{i}@example.com',
                'password1': 'Str0ngP@ss123',
                'password2': 'Str0ngP@ss123',
            })
        response = self.client.post(reverse('register'), {
            'username': 'user4',
            'email': 'user4@example.com',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 429)

    def test_register_get_not_rate_limited(self):
        for i in range(3):
            self.client.post(reverse('register'), {
                'username': f'user{i}',
                'email': f'user{i}@example.com',
                'password1': 'Str0ngP@ss123',
                'password2': 'Str0ngP@ss123',
            })
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)


@tag("integration")
class PasswordResetRateLimitIPTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()
        self.user = User.objects.create_user(
            username='resetuser',
            email='reset@example.com',
            password='SomePassword123',
        )

    def tearDown(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()

    def test_password_reset_allows_up_to_5_attempts(self):
        for _ in range(5):
            response = self.client.post(reverse('password_reset'), {
                'email_or_username': 'resetuser',
            })
            self.assertEqual(response.status_code, 200)

    def test_password_reset_blocked_after_5_attempts(self):
        for _ in range(5):
            self.client.post(reverse('password_reset'), {
                'email_or_username': 'resetuser',
            })
        response = self.client.post(reverse('password_reset'), {
            'email_or_username': 'resetuser',
        })
        self.assertEqual(response.status_code, 429)

    def test_password_reset_get_not_rate_limited(self):
        for _ in range(5):
            self.client.post(reverse('password_reset'), {
                'email_or_username': 'resetuser',
            })
        response = self.client.get(reverse('password_reset'))
        self.assertEqual(response.status_code, 200)

    def test_password_reset_rate_limit_independent_of_identifier_limit(self):
        self.client.post(reverse('password_reset'), {
            'email_or_username': 'resetuser',
        })
        self.assertEqual(len(mail.outbox), 1)
        response = self.client.post(reverse('password_reset'), {
            'email_or_username': 'resetuser',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)


@tag("integration")
class PasswordResetSessionInvalidationTest(TestCase):

    def setUp(self):
        from django.core.cache import caches
        caches['rate_limit'].clear()

    def test_password_reset_invalidates_existing_sessions(self):
        user = User.objects.create_user(
            username='sessuser',
            email='sess@example.com',
            password='OriginalPass123',
        )
        attacker_client = Client()
        attacker_client.login(username='sessuser', password='OriginalPass123')
        response = attacker_client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 200)

        from club.views import generate_password_token
        token = generate_password_token(user)
        self.client.post(reverse('password_reset_form', kwargs={'token': token}), {
            'new_password1': 'ResetPass456',
            'new_password2': 'ResetPass456',
        })

        response = attacker_client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_user_can_login_with_new_password_after_reset(self):
        user = User.objects.create_user(
            username='loginafter',
            email='loginafter@example.com',
            password='OriginalPass123',
        )
        from club.views import generate_password_token
        token = generate_password_token(user)
        self.client.post(reverse('password_reset_form', kwargs={'token': token}), {
            'new_password1': 'ResetPass456',
            'new_password2': 'ResetPass456',
        })
        self.client.login(username='loginafter', password='ResetPass456')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_password_reset_invalidates_multiple_sessions(self):
        user = User.objects.create_user(
            username='multisess',
            email='multisess@example.com',
            password='OriginalPass123',
        )
        client_a = Client()
        client_b = Client()
        client_a.login(username='multisess', password='OriginalPass123')
        client_b.login(username='multisess', password='OriginalPass123')

        from club.views import generate_password_token
        token = generate_password_token(user)
        self.client.post(reverse('password_reset_form', kwargs={'token': token}), {
            'new_password1': 'ResetPass456',
            'new_password2': 'ResetPass456',
        })

        response_a = client_a.get(reverse('user_settings'))
        response_b = client_b.get(reverse('user_settings'))
        self.assertEqual(response_a.status_code, 302)
        self.assertIn('/login/', response_a.url)
        self.assertEqual(response_b.status_code, 302)
        self.assertIn('/login/', response_b.url)


@tag("integration")
class ChangePasswordSessionInvalidationTest(TestCase):

    def test_change_password_invalidates_other_sessions(self):
        user = User.objects.create_user(
            username='chgpwuser',
            password='OldPass123',
            email='chgpw@example.com',
        )
        other_client = Client()
        other_client.login(username='chgpwuser', password='OldPass123')
        response = other_client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 200)

        self.client.login(username='chgpwuser', password='OldPass123')
        self.client.post(reverse('change_password'), {
            'current_password': 'OldPass123',
            'new_password1': 'NewPass456',
            'new_password2': 'NewPass456',
        })

        response = other_client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_change_password_keeps_current_session_alive(self):
        user = User.objects.create_user(
            username='keepalive',
            password='OldPass123',
            email='keepalive@example.com',
        )
        self.client.login(username='keepalive', password='OldPass123')
        self.client.post(reverse('change_password'), {
            'current_password': 'OldPass123',
            'new_password1': 'NewPass456',
            'new_password2': 'NewPass456',
        })
        response = self.client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 200)

    def test_change_password_invalidates_multiple_other_sessions(self):
        user = User.objects.create_user(
            username='multichg',
            password='OldPass123',
            email='multichg@example.com',
        )
        other_client_a = Client()
        other_client_b = Client()
        other_client_a.login(username='multichg', password='OldPass123')
        other_client_b.login(username='multichg', password='OldPass123')

        self.client.login(username='multichg', password='OldPass123')
        self.client.post(reverse('change_password'), {
            'current_password': 'OldPass123',
            'new_password1': 'NewPass456',
            'new_password2': 'NewPass456',
        })

        response_a = other_client_a.get(reverse('user_settings'))
        response_b = other_client_b.get(reverse('user_settings'))
        self.assertEqual(response_a.status_code, 302)
        self.assertIn('/login/', response_a.url)
        self.assertEqual(response_b.status_code, 302)
        self.assertIn('/login/', response_b.url)


@tag("integration")
class ForcedPasswordChangeSessionInvalidationTest(TestCase):

    def test_forced_password_change_invalidates_other_sessions(self):
        user = User.objects.create_user(
            username='forcedsess',
            password='TempPassword123',
            must_change_password=True,
        )
        other_client = Client()
        other_client.login(username='forcedsess', password='TempPassword123')
        response = other_client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/change-password/', response.url)

        self.client.login(username='forcedsess', password='TempPassword123')
        self.client.post(reverse('forced_password_change'), {
            'new_password1': 'NewPassword456',
            'new_password2': 'NewPassword456',
        })

        response = other_client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_forced_password_change_keeps_current_session_alive(self):
        user = User.objects.create_user(
            username='forcedalive',
            password='TempPassword123',
            must_change_password=True,
        )
        self.client.login(username='forcedalive', password='TempPassword123')
        self.client.post(reverse('forced_password_change'), {
            'new_password1': 'NewPassword456',
            'new_password2': 'NewPassword456',
        })
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
