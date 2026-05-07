from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse

from club.models import BoardGame, SiteSettings

User = get_user_model()


@tag("unit")
class SiteSettingsLockdownFieldsTest(TestCase):

    def test_site_lockdown_defaults_to_false(self):
        settings = SiteSettings.load()
        self.assertFalse(settings.site_lockdown_active)

    def test_site_lockdown_allow_site_admins_defaults_to_false(self):
        settings = SiteSettings.load()
        self.assertFalse(settings.site_lockdown_allow_site_admins)

    def test_can_set_site_lockdown_active(self):
        settings = SiteSettings.load()
        settings.site_lockdown_active = True
        settings.save()
        settings.refresh_from_db()
        self.assertTrue(settings.site_lockdown_active)

    def test_can_set_site_lockdown_allow_site_admins(self):
        settings = SiteSettings.load()
        settings.site_lockdown_allow_site_admins = True
        settings.save()
        settings.refresh_from_db()
        self.assertTrue(settings.site_lockdown_allow_site_admins)


@tag("unit")
class SiteLockdownMiddlewarePOSTTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123',
        )
        cls.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True,
        )
        cls.regular = User.objects.create_user(
            username='regular', password='testpass123',
        )

    def test_regular_user_post_blocked_during_lockdown(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(reverse('game_add'), {'name': 'Test'})
        self.assertEqual(response.status_code, 403)

    def test_regular_user_get_allowed_during_lockdown(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_regular_user_post_allowed_when_no_lockdown(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(reverse('game_add'), {'name': 'Test'})
        self.assertNotEqual(response.status_code, 403)

    def test_superuser_post_allowed_during_lockdown(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        self.client.login(username='superuser', password='testpass123')
        response = self.client.post(reverse('admin_settings'), {
            'default_voting_offset_hours': '0',
            'default_voting_offset_minutes_field': '0',
        })
        self.assertNotEqual(response.status_code, 403)

    def test_site_admin_post_blocked_during_lockdown_by_default(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post(reverse('game_add'), {'name': 'Test'})
        self.assertEqual(response.status_code, 403)

    def test_site_admin_post_allowed_when_lockdown_allows_admins(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(
            site_lockdown_active=True,
            site_lockdown_allow_site_admins=True,
        )
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post(reverse('game_add'), {'name': 'Test'})
        self.assertNotEqual(response.status_code, 403)

    def test_anonymous_user_post_blocked_during_lockdown(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        response = self.client.post(reverse('game_add'), {'name': 'Test'})
        self.assertNotEqual(response.status_code, 200)

    def test_logout_post_allowed_during_lockdown(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(reverse('logout'))
        self.assertNotEqual(response.status_code, 403)

    def test_login_post_allowed_during_lockdown(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        response = self.client.post(reverse('login'), {
            'username': 'regular',
            'password': 'testpass123',
        })
        self.assertNotEqual(response.status_code, 403)


@tag("unit")
class SiteLockdownMiddlewareRegistrationTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123',
        )

    def test_register_get_blocked_during_lockdown(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_register_post_blocked_during_lockdown(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(username='newuser').exists())

    def test_register_allowed_when_no_lockdown(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)

    def test_superuser_register_get_allowed_during_lockdown(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)


@tag("integration")
class SiteLockdownViewToggleTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123',
        )
        cls.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True,
        )
        cls.regular = User.objects.create_user(
            username='regular', password='testpass123',
        )

    def test_superuser_can_activate_lockdown(self):
        self.client.login(username='superuser', password='testpass123')
        self.client.post(reverse('admin_settings'), {
            'site_lockdown_active': 'on',
        })
        settings = SiteSettings.load()
        self.assertTrue(settings.site_lockdown_active)

    def test_superuser_can_deactivate_lockdown(self):
        settings = SiteSettings.load()
        settings.site_lockdown_active = True
        settings.save()
        self.client.login(username='superuser', password='testpass123')
        self.client.post(reverse('admin_settings'), {
            'site_lockdown_deactivate': '1',
        })
        settings.refresh_from_db()
        self.assertFalse(settings.site_lockdown_active)

    def test_site_admin_cannot_activate_lockdown(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post(reverse('admin_settings'), {
            'site_lockdown_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        settings = SiteSettings.load()
        self.assertFalse(settings.site_lockdown_active)

    def test_regular_user_cannot_activate_lockdown(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(reverse('admin_settings'), {
            'site_lockdown_active': 'on',
        })
        self.assertEqual(response.status_code, 403)
        settings = SiteSettings.load()
        self.assertFalse(settings.site_lockdown_active)

    def test_superuser_can_toggle_allow_site_admins(self):
        settings = SiteSettings.load()
        settings.site_lockdown_active = True
        settings.save()
        self.client.login(username='superuser', password='testpass123')
        self.client.post(reverse('admin_settings'), {
            'site_lockdown_active': 'on',
            'site_lockdown_allow_site_admins': 'on',
        })
        settings.refresh_from_db()
        self.assertTrue(settings.site_lockdown_allow_site_admins)

    def test_allow_site_admins_reset_when_lockdown_deactivated(self):
        settings = SiteSettings.load()
        settings.site_lockdown_active = True
        settings.site_lockdown_allow_site_admins = True
        settings.save()
        self.client.login(username='superuser', password='testpass123')
        self.client.post(reverse('admin_settings'), {
            'site_lockdown_deactivate': '1',
        })
        settings.refresh_from_db()
        self.assertFalse(settings.site_lockdown_active)
        self.assertFalse(settings.site_lockdown_allow_site_admins)


@tag("integration")
class SiteLockdownBannerTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.regular = User.objects.create_user(
            username='regular', password='testpass123',
        )

    def test_banner_shown_during_lockdown(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'site-lockdown-banner')

    def test_banner_not_shown_when_no_lockdown(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'site-lockdown-banner')


@tag("integration")
class SiteLockdownAdminSettingsTemplateTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123',
        )
        cls.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True,
        )

    def test_superuser_sees_lockdown_section(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('admin_settings'))
        self.assertContains(response, 'Site Lockdown')

    def test_site_admin_does_not_see_lockdown_section(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('admin_settings'))
        self.assertNotContains(response, 'Site Lockdown')

    def test_superuser_sees_lockdown_confirmation_modal(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('admin_settings'))
        self.assertContains(response, 'lockdown-confirm-modal')


@tag("integration")
class SiteLockdownContextProcessorTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.regular = User.objects.create_user(
            username='regular', password='testpass123',
        )

    def test_context_has_site_lockdown_active_true(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertTrue(response.context['site_lockdown_active'])

    def test_context_has_site_lockdown_active_false(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertFalse(response.context['site_lockdown_active'])


@tag("integration")
class SiteLockdownRegisterViewDefenseTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123',
        )

    def test_register_view_redirects_during_lockdown(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 302)

    def test_register_view_post_fails_during_lockdown(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        response = self.client.post(reverse('register'), {
            'username': 'newuser',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        self.assertFalse(User.objects.filter(username='newuser').exists())
