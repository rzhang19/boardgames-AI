from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

User = get_user_model()


class RegistrationWithoutEmailTest(TestCase):

    def test_registration_without_email_succeeds(self):
        response = self.client.post(reverse('register'), {
            'username': 'noemailuser',
            'email': '',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='noemailuser').exists())

    def test_registration_without_email_auto_logins(self):
        response = self.client.post(reverse('register'), {
            'username': 'noemailuser',
            'email': '',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'noemailuser')

    def test_registration_without_email_user_is_created(self):
        self.client.post(reverse('register'), {
            'username': 'noemailuser',
            'email': '',
            'password1': 'Str0ngP@ss123',
            'password2': 'Str0ngP@ss123',
        })
        user = User.objects.get(username='noemailuser')
        self.assertEqual(user.email, '')
        self.assertFalse(user.is_organizer)
        self.assertFalse(user.is_superuser)


class RegistrationWithEmailOptionalWarningTest(TestCase):

    def test_register_page_shows_email_optional_warning(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'verified')
        self.assertContains(response, 'email')


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
