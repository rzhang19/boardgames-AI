from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.signing import TimestampSigner
from django.urls import reverse

User = get_user_model()


class RegistrationTest(TestCase):

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
        self.assertFalse(new_user.is_organizer)
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


class LoginTest(TestCase):

    def setUp(self):
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

    def test_login_with_nonexistent_user(self):
        response = self.client.post(reverse('login'), {
            'username': 'ghost',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 200)

    def test_authenticated_user_sees_username_on_dashboard(self):
        self.client.login(username='loginuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'loginuser')

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


class AdminBadgeTest(TestCase):

    def setUp(self):
        self.organizer_user = User.objects.create_user(
            username='organizeruser', password='testpass123', is_organizer=True
        )
        self.site_admin_user = User.objects.create_user(
            username='siteadminuser', password='testpass123', is_site_admin=True
        )
        self.regular_user = User.objects.create_user(
            username='regularuser', password='testpass123'
        )

    def test_organizer_sees_organizer_badge_on_dashboard(self):
        self.client.login(username='organizeruser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Organizer')

    def test_site_admin_sees_site_admin_badge_on_dashboard(self):
        self.client.login(username='siteadminuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Site Admin')

    def test_regular_user_does_not_see_any_badge(self):
        self.client.login(username='regularuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'Organizer')
        self.assertNotContains(response, 'Site Admin')


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


@override_settings(REQUIRE_EMAIL_VERIFICATION=True)
class EmailVerificationRegistrationTest(TestCase):

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


@override_settings(REQUIRE_EMAIL_VERIFICATION=True, DEBUG=False)
class EmailVerificationLoginBlockTest(TestCase):

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


class UsernameValidationTest(TestCase):

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
