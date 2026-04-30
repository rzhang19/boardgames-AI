from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, tag
from django.urls import reverse

from club.models import SiteSettings, VerifiedIcon

User = get_user_model()


def _create_svg(name='test.svg'):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/></svg>'
    return ContentFile(svg, name=name)


@tag("integration")
class AdminSettingsAccessTest(TestCase):

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

    def test_site_admin_can_access_admin_settings(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('admin_settings'))
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_access_admin_settings(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('admin_settings'))
        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_access_admin_settings(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('admin_settings'))
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_user_redirected_to_login(self):
        response = self.client.get(reverse('admin_settings'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)


@tag("integration")
class AdminSettingsContentTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123',
        )
        cls.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True,
        )
        cls.other_admin = User.objects.create_user(
            username='otheradmin', password='testpass123', is_site_admin=True,
        )

    def test_admin_settings_shows_verified_icon_management(self):
        VerifiedIcon.objects.create(name='Dice', image=_create_svg('dice.svg'))
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('admin_settings'))
        self.assertContains(response, 'manage-verified-icons')
        self.assertContains(response, 'Dice')

    def test_admin_settings_shows_voting_offset_section(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('admin_settings'))
        self.assertContains(response, 'Default Voting Deadline Offset')

    def test_admin_settings_shows_site_admin_list(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('admin_settings'))
        self.assertContains(response, 'superuser')
        self.assertContains(response, 'siteadmin')
        self.assertContains(response, 'otheradmin')

    def test_site_admin_list_has_profile_links(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('admin_settings'))
        self.assertContains(response, reverse('public_profile', kwargs={'username': 'superuser'}))
        self.assertContains(response, reverse('public_profile', kwargs={'username': 'otheradmin'}))

    def test_site_admin_list_has_no_edit_actions(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('admin_settings'))
        self.assertNotContains(response, 'remove-site-admin')
        self.assertNotContains(response, 'btn-danger')

    def test_superuser_sees_manage_site_admins_link(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('admin_settings'))
        self.assertContains(response, reverse('manage_site_admins'))

    def test_site_admin_does_not_see_manage_site_admins_link(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('admin_settings'))
        self.assertNotContains(response, reverse('manage_site_admins'))

    def test_admin_settings_shows_manage_users_link(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('admin_settings'))
        self.assertContains(response, reverse('manage_users'))


@tag("integration")
class AdminSettingsVotingOffsetTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True,
        )
        cls.regular = User.objects.create_user(
            username='regular', password='testpass123',
        )

    def test_admin_can_save_voting_offset_on_admin_settings(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post(reverse('admin_settings'), {
            'default_voting_offset_hours': '1',
            'default_voting_offset_minutes_field': '30',
        })
        self.assertEqual(response.status_code, 302)
        site_settings = SiteSettings.load()
        self.assertEqual(site_settings.default_voting_offset_minutes, 90)

    def test_voting_offset_defaults_to_zero(self):
        site_settings = SiteSettings.load()
        self.assertEqual(site_settings.default_voting_offset_minutes, 0)

    def test_admin_can_set_offset_to_zero(self):
        site_settings = SiteSettings.load()
        site_settings.default_voting_offset_minutes = 60
        site_settings.save()
        self.client.login(username='siteadmin', password='testpass123')
        self.client.post(reverse('admin_settings'), {
            'default_voting_offset_hours': '0',
            'default_voting_offset_minutes_field': '0',
        })
        site_settings.refresh_from_db()
        self.assertEqual(site_settings.default_voting_offset_minutes, 0)

    def test_regular_user_cannot_save_voting_offset(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(reverse('admin_settings'), {
            'default_voting_offset_hours': '1',
            'default_voting_offset_minutes_field': '0',
        })
        self.assertEqual(response.status_code, 403)


@tag("integration")
class PersonalSettingsNoAdminContentTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='siteadmin', password='testpass123',
            is_site_admin=True, email_verified=True,
        )

    def test_personal_settings_no_verified_icon_management(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('user_settings'))
        self.assertNotContains(response, 'manage-verified-icons')

    def test_personal_settings_no_voting_offset(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('user_settings'))
        self.assertNotContains(response, 'Default Voting Deadline Offset')

    def test_personal_settings_still_has_icon_picker(self):
        VerifiedIcon.objects.create(name='Dice', image=_create_svg('dice.svg'))
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'verified-icon-picker')

    def test_personal_settings_still_has_timezone(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'Timezone')


@tag("integration")
class AdminNavButtonTest(TestCase):

    def test_admin_button_visible_for_site_admin(self):
        User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True,
        )
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('admin_settings'))
        self.assertContains(response, 'Admin</a>')

    def test_admin_button_visible_for_superuser(self):
        User.objects.create_superuser(
            username='superuser', password='testpass123',
        )
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('admin_settings'))

    def test_admin_button_not_visible_for_regular_user(self):
        User.objects.create_user(username='regular', password='testpass123')
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, reverse('admin_settings'))

    def test_admin_button_not_visible_when_logged_out(self):
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, reverse('admin_settings'))

    def test_manage_users_not_in_main_nav(self):
        User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True,
        )
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'Manage Users')


@tag("integration")
class ManageSiteAdminsAccessTest(TestCase):

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

    def test_superuser_can_access_manage_site_admins(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('manage_site_admins'))
        self.assertEqual(response.status_code, 200)

    def test_site_admin_cannot_access_manage_site_admins(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('manage_site_admins'))
        self.assertEqual(response.status_code, 403)

    def test_regular_user_cannot_access_manage_site_admins(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('manage_site_admins'))
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_redirected_to_login(self):
        response = self.client.get(reverse('manage_site_admins'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)


@tag("integration")
class ManageSiteAdminsContentTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123',
        )
        cls.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True,
        )
        cls.other_admin = User.objects.create_user(
            username='otheradmin', password='testpass123', is_site_admin=True,
        )

    def setUp(self):
        self.client.login(username='superuser', password='testpass123')

    def test_manage_site_admins_lists_current_admins(self):
        response = self.client.get(reverse('manage_site_admins'))
        self.assertContains(response, 'siteadmin')
        self.assertContains(response, 'otheradmin')

    def test_manage_site_admins_shows_remove_buttons(self):
        response = self.client.get(reverse('manage_site_admins'))
        self.assertContains(response, 'remove-site-admin')

    def test_manage_site_admins_shows_search_bar(self):
        response = self.client.get(reverse('manage_site_admins'))
        self.assertContains(response, 'site-admin-search')

    def test_manage_site_admins_does_not_show_confirm_without_changes(self):
        response = self.client.get(reverse('manage_site_admins'))
        self.assertContains(response, 'confirm-changes')
        self.assertContains(response, 'display:none')


@tag("integration")
class ManageSiteAdminsSearchTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123',
        )
        cls.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True,
        )
        cls.regular1 = User.objects.create_user(
            username='alice', password='testpass123',
        )
        cls.regular2 = User.objects.create_user(
            username='Bob', password='testpass123',
        )

    def setUp(self):
        self.client.login(username='superuser', password='testpass123')

    def test_search_by_username_case_insensitive(self):
        response = self.client.get(reverse('manage_site_admins_search'), {'q': 'alice'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        usernames = [u['username'] for u in data['results']]
        self.assertIn('alice', usernames)

    def test_search_by_username_case_insensitive_upper(self):
        response = self.client.get(reverse('manage_site_admins_search'), {'q': 'ALICE'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        usernames = [u['username'] for u in data['results']]
        self.assertIn('alice', usernames)

    def test_search_by_id(self):
        response = self.client.get(reverse('manage_site_admins_search'), {'q': str(self.regular1.pk)})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        ids = [u['id'] for u in data['results']]
        self.assertIn(self.regular1.pk, ids)

    def test_search_excludes_current_site_admins(self):
        response = self.client.get(reverse('manage_site_admins_search'), {'q': 'siteadmin'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        usernames = [u['username'] for u in data['results']]
        self.assertNotIn('siteadmin', usernames)

    def test_search_excludes_superuser(self):
        response = self.client.get(reverse('manage_site_admins_search'), {'q': 'superuser'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        usernames = [u['username'] for u in data['results']]
        self.assertNotIn('superuser', usernames)

    def test_search_returns_empty_for_no_match(self):
        response = self.client.get(reverse('manage_site_admins_search'), {'q': 'nonexistent'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['results']), 0)

    def test_search_requires_query_param(self):
        response = self.client.get(reverse('manage_site_admins_search'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['results']), 0)

    def test_search_only_accessible_by_superuser(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('manage_site_admins_search'), {'q': 'alice'})
        self.assertEqual(response.status_code, 403)


@tag("integration")
class ManageSiteAdminsConfirmTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123',
        )
        cls.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True,
        )
        cls.other_admin = User.objects.create_user(
            username='otheradmin', password='testpass123', is_site_admin=True,
        )
        cls.regular = User.objects.create_user(
            username='regular', password='testpass123',
        )

    def setUp(self):
        self.client.login(username='superuser', password='testpass123')

    def test_superuser_can_add_site_admin(self):
        self.client.post(reverse('manage_site_admins'), {
            'add': [str(self.regular.pk)],
        })
        self.regular.refresh_from_db()
        self.assertTrue(self.regular.is_site_admin)

    def test_superuser_can_remove_site_admin(self):
        self.client.post(reverse('manage_site_admins'), {
            'remove': [str(self.site_admin.pk)],
        })
        self.site_admin.refresh_from_db()
        self.assertFalse(self.site_admin.is_site_admin)

    def test_superuser_can_add_and_remove_in_same_request(self):
        self.client.post(reverse('manage_site_admins'), {
            'add': [str(self.regular.pk)],
            'remove': [str(self.site_admin.pk)],
        })
        self.regular.refresh_from_db()
        self.site_admin.refresh_from_db()
        self.assertTrue(self.regular.is_site_admin)
        self.assertFalse(self.site_admin.is_site_admin)

    def test_add_and_remove_same_user_cancels_out(self):
        self.client.post(reverse('manage_site_admins'), {
            'add': [str(self.regular.pk)],
            'remove': [str(self.regular.pk)],
        })
        self.regular.refresh_from_db()
        self.assertFalse(self.regular.is_site_admin)

    def test_cannot_promote_superuser(self):
        other_superuser = User.objects.create_superuser(
            username='other_SU', password='testpass123',
        )
        self.client.post(reverse('manage_site_admins'), {
            'add': [str(other_superuser.pk)],
        })
        other_superuser.refresh_from_db()
        self.assertTrue(other_superuser.is_superuser)

    def test_cannot_remove_self(self):
        self.client.post(reverse('manage_site_admins'), {
            'remove': [str(self.superuser.pk)],
        })
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_superuser)

    def test_regular_user_cannot_confirm(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(reverse('manage_site_admins'), {
            'add': [str(self.regular.pk)],
        })
        self.assertEqual(response.status_code, 403)

    def test_site_admin_cannot_confirm(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post(reverse('manage_site_admins'), {
            'add': [str(self.regular.pk)],
        })
        self.assertEqual(response.status_code, 403)


@tag("integration")
class ManageUsersPageChangesTest(TestCase):

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

    def test_manage_users_shows_id_column_for_site_admin(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertContains(response, 'ID')
        self.assertContains(response, str(self.regular.pk))

    def test_manage_users_shows_id_column_for_superuser(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertContains(response, 'ID')

    def test_site_admin_no_is_site_admin_column(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertNotContains(response, 'is_site_admin')

    def test_superuser_no_is_site_admin_column(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertNotContains(response, 'is_site_admin')

    def test_site_admin_no_preview_changes_button(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertNotContains(response, 'Preview Changes')

    def test_superuser_no_preview_changes_button(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertNotContains(response, 'Preview Changes')

    def test_manage_users_has_profile_links(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertContains(response, reverse('public_profile', kwargs={'username': 'regular'}))

    def test_site_admin_cannot_see_site_admins_in_list(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertNotContains(response, 'otheradmin')
        self.assertNotContains(response, 'superuser')

    def test_superuser_can_see_site_admins_in_list(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertContains(response, 'siteadmin')


@tag("integration")
class GroupListSettingsGearTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='testuser', password='testpass123',
        )
        cls.admin_user = User.objects.create_user(
            username='groupadmin', password='testpass123',
        )
        from club.models import Group, GroupMembership
        cls.group = Group.objects.create(name='Test Group')
        GroupMembership.objects.create(
            user=cls.admin_user, group=cls.group, role='admin',
        )
        GroupMembership.objects.create(
            user=cls.user, group=cls.group, role='member',
        )

    def test_group_list_shows_settings_gear_for_admin(self):
        self.client.login(username='groupadmin', password='testpass123')
        response = self.client.get(reverse('group_list'))
        self.assertContains(response, reverse('group_settings', kwargs={'slug': self.group.slug}))

    def test_group_list_no_settings_gear_for_member(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('group_list'))
        self.assertNotContains(response, 'group-settings-btn')

    def test_group_list_no_settings_gear_for_non_member(self):
        other_user = User.objects.create_user(
            username='other', password='testpass123',
        )
        self.client.login(username='other', password='testpass123')
        response = self.client.get(reverse('group_list'))
        self.assertNotContains(response, 'group-settings-btn')
