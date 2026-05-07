import os

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from club.models import Group, GroupMembership, Event

User = get_user_model()


def _read_css():
    css_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        '..', 'static', 'css', 'style.css'
    )
    css_path = os.path.normpath(css_path)
    with open(css_path, 'r') as f:
        return f.read()


def _read_js():
    js_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        '..', 'static', 'js', 'unsaved-changes.js'
    )
    js_path = os.path.normpath(js_path)
    with open(js_path, 'r') as f:
        return f.read()


# ---------------------------------------------------------------------------
# User Settings Page
# ---------------------------------------------------------------------------

@tag("integration")
class UserSettingsBannerTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
        )
        self.client.login(username='testuser', password='testpass123')

    def test_settings_page_has_unsaved_changes_banner(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'unsaved-changes-banner')

    def test_banner_contains_unsaved_changes_text(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'You have unsaved changes')

    def test_banner_has_save_button(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'unsaved-save-btn')

    def test_settings_page_includes_unsaved_changes_js(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'unsaved-changes.js')

    def test_settings_page_no_bottom_save_button(self):
        response = self.client.get(reverse('user_settings'))
        content = response.content.decode()
        banner_end = content.find('</div>', content.find('unsaved-changes-banner'))
        after_banner = content[banner_end:]
        self.assertNotIn('>Save Settings<', after_banner)


# ---------------------------------------------------------------------------
# Group Settings Page
# ---------------------------------------------------------------------------

@tag("integration")
class GroupSettingsBannerTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='admin', password='p')
        cls.group = Group.objects.create(name='Banner Group')
        GroupMembership.objects.create(user=cls.user, group=cls.group, role='admin')

    def setUp(self):
        self.client.login(username='admin', password='p')

    def test_group_settings_has_unsaved_changes_banner(self):
        response = self.client.get(f'/groups/{self.group.slug}/settings/')
        self.assertContains(response, 'unsaved-changes-banner')

    def test_banner_contains_unsaved_changes_text(self):
        response = self.client.get(f'/groups/{self.group.slug}/settings/')
        self.assertContains(response, 'You have unsaved changes')

    def test_banner_has_save_button(self):
        response = self.client.get(f'/groups/{self.group.slug}/settings/')
        self.assertContains(response, 'unsaved-save-btn')

    def test_group_settings_includes_unsaved_changes_js(self):
        response = self.client.get(f'/groups/{self.group.slug}/settings/')
        self.assertContains(response, 'unsaved-changes.js')

    def test_group_settings_no_bottom_save_button(self):
        response = self.client.get(f'/groups/{self.group.slug}/settings/')
        content = response.content.decode()
        banner_end = content.find('</div>', content.find('unsaved-changes-banner'))
        after_banner = content[banner_end:]
        self.assertNotIn('>Save Settings<', after_banner)


# ---------------------------------------------------------------------------
# Private Event Settings Page
# ---------------------------------------------------------------------------

@tag("integration")
class PrivateEventSettingsBannerTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='creator', password='p')
        cls.event = Event.objects.create(
            title='Private Event',
            date=timezone.now() + __import__('datetime').timedelta(days=7),
            created_by=cls.user,
            voting_deadline=timezone.now() + __import__('datetime').timedelta(days=6),
        )

    def setUp(self):
        self.client.login(username='creator', password='p')

    def test_private_event_settings_has_unsaved_changes_banner(self):
        response = self.client.get(f'/events/{self.event.pk}/settings/')
        self.assertContains(response, 'unsaved-changes-banner')

    def test_banner_contains_unsaved_changes_text(self):
        response = self.client.get(f'/events/{self.event.pk}/settings/')
        self.assertContains(response, 'You have unsaved changes')

    def test_banner_has_save_button(self):
        response = self.client.get(f'/events/{self.event.pk}/settings/')
        self.assertContains(response, 'unsaved-save-btn')

    def test_private_event_settings_includes_unsaved_changes_js(self):
        response = self.client.get(f'/events/{self.event.pk}/settings/')
        self.assertContains(response, 'unsaved-changes.js')

    def test_private_event_settings_no_bottom_save_button(self):
        response = self.client.get(f'/events/{self.event.pk}/settings/')
        content = response.content.decode()
        banner_end = content.find('</div>', content.find('unsaved-changes-banner'))
        after_banner = content[banner_end:]
        self.assertNotIn('>Save Settings<', after_banner)


# ---------------------------------------------------------------------------
# Static Files
# ---------------------------------------------------------------------------

@tag("integration")
class UnsavedChangesStaticFilesTest(TestCase):

    def test_js_file_exists(self):
        js = _read_js()
        self.assertTrue(len(js) > 0)

    def test_js_has_form_snapshot_logic(self):
        js = _read_js()
        self.assertIn('snapshot', js)

    def test_js_has_dirty_check_logic(self):
        js = _read_js()
        self.assertIn('isDirty', js)

    def test_js_has_beforeunload_handler(self):
        js = _read_js()
        self.assertIn('beforeunload', js)

    def test_js_has_banner_toggle(self):
        js = _read_js()
        self.assertIn('unsaved-banner', js)
        self.assertIn('classList', js)
        self.assertIn('active', js)

    def test_css_has_banner_styles(self):
        css = _read_css()
        self.assertIn('.unsaved-changes-banner', css)

    def test_css_has_fixed_position(self):
        css = _read_css()
        self.assertIn('position: fixed', css)

    def test_css_banner_has_dark_theme_support(self):
        css = _read_css()
        self.assertIn('[data-applied-theme="dark"] .unsaved-changes-banner', css)
