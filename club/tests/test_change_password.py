from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.test import TestCase, tag
from django.urls import reverse

from club.models import PasswordHistory
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
