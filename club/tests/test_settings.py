from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.signing import TimestampSigner
from django.test import TestCase, override_settings, tag
from django.urls import reverse

from club.models import SiteSettings, VerifiedIcon

User = get_user_model()


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
