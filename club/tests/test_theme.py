import os

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse

User = get_user_model()


def _read_css():
    css_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        '..', 'static', 'css', 'style.css'
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
class ThemeToggleEndpointTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

    def test_toggle_theme_requires_login(self):
        self.client.logout()
        response = self.client.post(reverse('toggle_theme'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_toggle_theme_requires_post(self):
        response = self.client.get(reverse('toggle_theme'))
        self.assertEqual(response.status_code, 405)

    def test_toggle_theme_saves_dark(self):
        response = self.client.post(
            reverse('toggle_theme'),
            {'theme': 'dark'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, 'dark')

    def test_toggle_theme_saves_light(self):
        response = self.client.post(
            reverse('toggle_theme'),
            {'theme': 'light'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, 'light')

    def test_toggle_theme_saves_system(self):
        response = self.client.post(
            reverse('toggle_theme'),
            {'theme': 'system'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.theme, 'system')

    def test_toggle_theme_rejects_invalid(self):
        response = self.client.post(
            reverse('toggle_theme'),
            {'theme': 'neon'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)

    def test_toggle_theme_rejects_empty(self):
        response = self.client.post(
            reverse('toggle_theme'),
            {},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)


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

    def test_base_template_has_theme_toggle_button(self):
        source = _read_base_template()
        self.assertIn('theme-toggle', source)

    def test_base_template_has_theme_script(self):
        source = _read_base_template()
        self.assertIn('theme-toggle', source)

    def test_base_template_has_nav_theme_toggle_class(self):
        source = _read_base_template()
        self.assertIn('nav-theme-toggle', source)


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

    def test_dark_theme_has_nav_toggle_styles(self):
        self.assertIn('.nav-theme-toggle', self.css)

    def test_nav_toggle_hidden_on_mobile(self):
        blocks_start = self.css.find('@media (max-width: 600px)')
        self.assertNotEqual(blocks_start, -1)
        mobile_css = self.css[blocks_start:]
        self.assertIn('nav-theme-toggle', mobile_css)


@tag("integration")
class SettingsTemplateThemeTest(TestCase):

    def test_settings_template_has_theme_card(self):
        source = _read_settings_template()
        self.assertIn('Theme', source)

    def test_settings_template_has_theme_radio_inputs(self):
        source = _read_settings_template()
        self.assertIn('name="theme"', source)
