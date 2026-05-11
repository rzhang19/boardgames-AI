import hashlib

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core import mail
from django.core.signing import TimestampSigner
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from club.models import BoardGame, Group, GroupMembership, SiteSettings, VerifiedIcon

User = get_user_model()


def _create_svg(name='test.svg'):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/></svg>'
    return ContentFile(svg, name=name)


def _password_state_component(user):
    return hashlib.sha256(user.password.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# test_site_admin_settings.py — ALL classes (11)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# test_superuser_manage.py — integration-tagged classes (14)
# ---------------------------------------------------------------------------

@tag("integration")
class ManageUsersAccessTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123'
        )
        self.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )

    def test_superuser_can_access_manage_users(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertEqual(response.status_code, 200)

    def test_site_admin_can_access_manage_users(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_access_manage_users(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_user_redirected_to_login(self):
        response = self.client.get(reverse('manage_users'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)


@tag("integration")
class ManageUsersPageTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123'
        )
        self.user1 = User.objects.create_user(
            username='user1', password='testpass123'
        )
        self.client.login(username='superuser', password='testpass123')

    def test_manage_users_shows_user_list(self):
        response = self.client.get(reverse('manage_users'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'user1')

    def test_manage_users_shows_ids(self):
        response = self.client.get(reverse('manage_users'))
        self.assertContains(response, str(self.user1.pk))


@tag("integration")
class SiteAdminRestrictionTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123'
        )
        self.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True
        )
        self.other_site_admin = User.objects.create_user(
            username='otheradmin', password='testpass123', is_site_admin=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )

    def test_site_admin_cannot_see_other_site_admins(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertNotContains(response, 'otheradmin')
        self.assertNotContains(response, 'superuser')

    def test_site_admin_cannot_change_site_admin_roles_via_confirm(self):
        self.client.login(username='siteadmin', password='testpass123')
        session = self.client.session
        session['pending_role_changes'] = {
            str(self.other_site_admin.pk): {'is_site_admin': False},
        }
        session.save()

        self.client.post(reverse('manage_users_confirm'))
        self.other_site_admin.refresh_from_db()
        self.assertTrue(self.other_site_admin.is_site_admin)

    def test_superuser_can_change_site_admin_roles(self):
        self.client.login(username='superuser', password='testpass123')
        session = self.client.session
        session['pending_role_changes'] = {
            str(self.other_site_admin.pk): {'is_site_admin': False},
        }
        session.save()

        self.client.post(reverse('manage_users_confirm'))
        self.other_site_admin.refresh_from_db()
        self.assertFalse(self.other_site_admin.is_site_admin)


@tag("integration")
class ManageUsersConfirmFieldWhitelistTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123'
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )

    def test_non_whitelisted_is_staff_stripped_from_changes(self):
        self.client.login(username='superuser', password='testpass123')
        session = self.client.session
        session['pending_role_changes'] = {
            str(self.regular.pk): {'is_staff': True},
        }
        session.save()

        self.client.post(reverse('manage_users_confirm'))
        self.regular.refresh_from_db()
        self.assertFalse(self.regular.is_staff)

    def test_non_whitelisted_is_superuser_stripped_from_changes(self):
        self.client.login(username='superuser', password='testpass123')
        session = self.client.session
        session['pending_role_changes'] = {
            str(self.regular.pk): {'is_superuser': True},
        }
        session.save()

        self.client.post(reverse('manage_users_confirm'))
        self.regular.refresh_from_db()
        self.assertFalse(self.regular.is_superuser)

    def test_whitelisted_is_site_admin_still_applied(self):
        self.client.login(username='superuser', password='testpass123')
        session = self.client.session
        session['pending_role_changes'] = {
            str(self.regular.pk): {'is_site_admin': True},
        }
        session.save()

        self.client.post(reverse('manage_users_confirm'))
        self.regular.refresh_from_db()
        self.assertTrue(self.regular.is_site_admin)

    def test_mixed_whitelisted_and_non_whitelisted_only_applies_whitelisted(self):
        self.client.login(username='superuser', password='testpass123')
        session = self.client.session
        session['pending_role_changes'] = {
            str(self.regular.pk): {'is_site_admin': True, 'is_staff': True, 'is_superuser': True},
        }
        session.save()

        self.client.post(reverse('manage_users_confirm'))
        self.regular.refresh_from_db()
        self.assertTrue(self.regular.is_site_admin)
        self.assertFalse(self.regular.is_staff)
        self.assertFalse(self.regular.is_superuser)


@tag("integration")
class ManageUsersConfirmInputValidationTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123'
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )
        self.client.login(username='superuser', password='testpass123')

    def test_non_integer_user_id_in_session_is_ignored(self):
        session = self.client.session
        session['pending_role_changes'] = {
            'not_a_number': {'is_site_admin': True},
        }
        session.save()
        response = self.client.post(reverse('manage_users_confirm'))
        self.assertEqual(response.status_code, 302)

    def test_non_existent_user_id_is_ignored(self):
        session = self.client.session
        session['pending_role_changes'] = {
            '99999': {'is_site_admin': True},
        }
        session.save()
        response = self.client.post(reverse('manage_users_confirm'))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(pk=99999).exists())

    def test_deleted_user_cannot_have_roles_changed(self):
        deleted_user = User.objects.create_user(
            username='deleted', password='testpass123',
            is_active=False, deleted_at=timezone.now(), deleted_by=self.superuser,
        )
        session = self.client.session
        session['pending_role_changes'] = {
            str(deleted_user.pk): {'is_site_admin': True},
        }
        session.save()
        self.client.post(reverse('manage_users_confirm'))
        deleted_user.refresh_from_db()
        self.assertFalse(deleted_user.is_site_admin)

    def test_non_boolean_value_for_is_site_admin_is_rejected(self):
        session = self.client.session
        session['pending_role_changes'] = {
            str(self.regular.pk): {'is_site_admin': 'malicious_string'},
        }
        session.save()
        self.client.post(reverse('manage_users_confirm'))
        self.regular.refresh_from_db()
        self.assertFalse(self.regular.is_site_admin)

    def test_superuser_cannot_have_roles_changed_via_confirm(self):
        other_superuser = User.objects.create_superuser(
            username='other_super', password='testpass123'
        )
        session = self.client.session
        session['pending_role_changes'] = {
            str(other_superuser.pk): {'is_site_admin': False},
        }
        session.save()
        self.client.post(reverse('manage_users_confirm'))
        other_superuser.refresh_from_db()
        self.assertTrue(other_superuser.is_superuser)

    def test_empty_session_data_results_in_no_errors(self):
        response = self.client.post(reverse('manage_users_confirm'))
        self.assertEqual(response.status_code, 302)

    def test_get_request_to_confirm_redirects(self):
        response = self.client.get(reverse('manage_users_confirm'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('manage-users', response.url)


@tag("integration")
class UserAddTest(TestCase):

    def setUp(self):
        self.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )
        self.client.login(username='siteadmin', password='testpass123')

    def test_site_admin_can_access_add_user_page(self):
        response = self.client.get(reverse('user_add'))
        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_access_add_user(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('user_add'))
        self.assertEqual(response.status_code, 403)

    def test_site_admin_can_add_user(self):
        response = self.client.post(reverse('user_add'), {
            'username': 'newuser',
            'email': 'newuser@example.com',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='newuser').exists())
        new_user = User.objects.get(username='newuser')
        self.assertFalse(new_user.is_site_admin)

    def test_add_user_sends_email(self):
        self.client.post(reverse('user_add'), {
            'username': 'newuser',
            'email': 'newuser@example.com',
        })
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('newuser@example.com', mail.outbox[0].to)

    def test_add_user_without_email_or_temp_password_fails(self):
        response = self.client.post(reverse('user_add'), {
            'username': 'newuser',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newuser').exists())

    def test_add_user_with_both_email_and_temp_password_fails(self):
        response = self.client.post(reverse('user_add'), {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'temporary_password': 'TempP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newuser').exists())

    def test_add_user_with_temp_password_creates_user_with_must_change(self):
        response = self.client.post(reverse('user_add'), {
            'username': 'newuser',
            'temporary_password': 'TempP@ss123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='newuser').exists())
        new_user = User.objects.get(username='newuser')
        self.assertTrue(new_user.check_password('TempP@ss123'))
        self.assertTrue(new_user.must_change_password)
        self.assertEqual(len(mail.outbox), 0)

    def test_add_user_with_email_only_sends_email_no_must_change(self):
        response = self.client.post(reverse('user_add'), {
            'username': 'newuser',
            'email': 'newuser@example.com',
        })
        self.assertEqual(response.status_code, 302)
        new_user = User.objects.get(username='newuser')
        self.assertFalse(new_user.must_change_password)
        self.assertFalse(new_user.has_usable_password())
        self.assertEqual(len(mail.outbox), 1)


@tag("integration")
class UserDeleteTest(TestCase):

    def setUp(self):
        self.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True
        )
        self.target = User.objects.create_user(
            username='target', password='testpass123'
        )
        self.client.login(username='siteadmin', password='testpass123')

    def test_site_admin_can_access_delete_page(self):
        response = self.client.get(reverse('user_delete', kwargs={'pk': self.target.pk}))
        self.assertEqual(response.status_code, 200)

    def test_delete_page_shows_username_confirmation_prompt(self):
        response = self.client.get(reverse('user_delete', kwargs={'pk': self.target.pk}))
        self.assertContains(response, "type the user's username to confirm")
        self.assertContains(response, '<code>target</code>', html=True)

    def test_site_admin_can_delete_user_with_correct_username(self):
        response = self.client.post(reverse('user_delete', kwargs={'pk': self.target.pk}), {
            'confirm_username': 'target',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertIsNotNone(self.target.deleted_at)
        self.assertEqual(self.target.deleted_by, self.site_admin)

    def test_delete_fails_with_wrong_username(self):
        response = self.client.post(reverse('user_delete', kwargs={'pk': self.target.pk}), {
            'confirm_username': 'wrongname',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())
        self.assertContains(response, 'Username did not match')

    def test_delete_fails_with_blank_username(self):
        response = self.client.post(reverse('user_delete', kwargs={'pk': self.target.pk}), {
            'confirm_username': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.target.pk).exists())

    def test_site_admin_cannot_delete_self(self):
        response = self.client.post(reverse('user_delete', kwargs={'pk': self.site_admin.pk}), {
            'confirm_username': 'siteadmin',
        })
        self.assertEqual(response.status_code, 403)

    def test_site_admin_cannot_delete_superuser(self):
        superuser = User.objects.create_superuser(
            username='superuser', password='testpass123'
        )
        response = self.client.post(reverse('user_delete', kwargs={'pk': superuser.pk}), {
            'confirm_username': 'superuser',
        })
        self.assertEqual(response.status_code, 403)

    def test_regular_user_cannot_delete(self):
        self.client.login(username='target', password='testpass123')
        response = self.client.post(reverse('user_delete', kwargs={'pk': self.site_admin.pk}), {
            'confirm_username': 'siteadmin',
        })
        self.assertEqual(response.status_code, 403)


@tag("integration")
class UserSetPasswordTest(TestCase):

    def test_valid_token_shows_password_form(self):
        user = User.objects.create_user(
            username='invited', password='!',
            email='invited@example.com', email_verified=False
        )
        from club.views import generate_password_token
        token = generate_password_token(user)
        response = self.client.get(reverse('user_set_password', kwargs={'token': token}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Set Your Password')

    def test_valid_token_sets_password(self):
        user = User.objects.create_user(
            username='invited', password='!',
            email='invited@example.com', email_verified=False
        )
        from club.views import generate_password_token
        token = generate_password_token(user)
        response = self.client.post(reverse('user_set_password', kwargs={'token': token}), {
            'new_password1': 'Str0ngP@ss123',
            'new_password2': 'Str0ngP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Password Set')
        user.refresh_from_db()
        self.assertTrue(user.check_password('Str0ngP@ss123'))
        self.assertTrue(user.email_verified)

    def test_invalid_token_shows_error(self):
        response = self.client.get(reverse('user_set_password', kwargs={'token': 'bad-token'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid Link')

    def test_mismatched_passwords_fails(self):
        user = User.objects.create_user(
            username='invited', password='!',
            email='invited@example.com', email_verified=False
        )
        from club.views import generate_password_token
        token = generate_password_token(user)
        response = self.client.post(reverse('user_set_password', kwargs={'token': token}), {
            'new_password1': 'Str0ngP@ss123',
            'new_password2': 'DifferentP@ss456',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Set Your Password')

    def test_set_password_token_invalid_after_password_change(self):
        user = User.objects.create_user(
            username='tokeninval2', password='!',
            email='tokeninval2@example.com', email_verified=False
        )
        from club.views import generate_password_token
        token = generate_password_token(user)
        user.set_password('SomeNewPass123')
        user.save()
        response = self.client.get(reverse('user_set_password', kwargs={'token': token}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid Link')

    def test_set_password_old_format_token_rejected(self):
        user = User.objects.create_user(
            username='oldsetpw', password='!',
            email='oldsetpw@example.com', email_verified=False
        )
        signer = TimestampSigner()
        token = signer.sign(user.pk)
        response = self.client.get(reverse('user_set_password', kwargs={'token': token}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid Link')


@tag("integration")
class ForcedPasswordChangeTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='tempuser', password='TempP@ss123',
            must_change_password=True,
        )

    def test_must_change_password_user_redirected_from_dashboard(self):
        self.client.login(username='tempuser', password='TempP@ss123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('forced_password_change'))

    def test_must_change_password_user_can_access_change_password_page(self):
        self.client.login(username='tempuser', password='TempP@ss123')
        response = self.client.get(reverse('forced_password_change'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Change Your Password')

    def test_must_change_password_user_can_logout(self):
        self.client.login(username='tempuser', password='TempP@ss123')
        response = self.client.post(reverse('logout'))
        self.assertEqual(response.status_code, 302)

    def test_change_password_with_same_password_fails(self):
        self.client.login(username='tempuser', password='TempP@ss123')
        response = self.client.post(reverse('forced_password_change'), {
            'new_password1': 'TempP@ss123',
            'new_password2': 'TempP@ss123',
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.must_change_password)

    def test_change_password_with_different_password_succeeds(self):
        self.client.login(username='tempuser', password='TempP@ss123')
        response = self.client.post(reverse('forced_password_change'), {
            'new_password1': 'Br@ndN3wPass!',
            'new_password2': 'Br@ndN3wPass!',
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        self.assertTrue(self.user.check_password('Br@ndN3wPass!'))


@tag("integration")
class AdminOrganizerEnforcementTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123'
        )
        self.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123',
            is_site_admin=True,
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123'
        )

    def test_superuser_demoting_site_admin_to_regular(self):
        self.client.login(username='superuser', password='testpass123')
        self.client.post(reverse('manage_site_admins'), {
            'remove': [str(self.site_admin.pk)],
        })
        self.site_admin.refresh_from_db()
        self.assertFalse(self.site_admin.is_site_admin)

    def test_site_admin_does_not_see_site_admin_column(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'is_site_admin')

    def test_site_admin_cannot_promote_to_site_admin(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post(reverse('manage_users'), {
            'promote': self.regular.pk,
        })
        self.regular.refresh_from_db()
        self.assertFalse(self.regular.is_site_admin)


@tag("integration")
class DeletedUsersListTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123'
        )
        self.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True
        )
        self.active_user = User.objects.create_user(
            username='active', password='testpass123'
        )
        self.deleted_user = User.objects.create_user(
            username='deleted', password='testpass123',
            is_active=False, deleted_at=timezone.now(), deleted_by=self.site_admin,
        )

    def test_manage_users_has_active_tab(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertContains(response, 'Active Users')

    def test_manage_users_has_deleted_tab(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertContains(response, 'Deleted Users')

    def test_active_tab_excludes_soft_deleted_users(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertContains(response, 'active')
        self.assertNotContains(response, '/profile/deleted/')

    def test_deleted_tab_shows_soft_deleted_users(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('manage_users') + '?tab=deleted')
        self.assertContains(response, 'deleted')
        self.assertNotContains(response, '/profile/active/')

    def test_deleted_tab_shows_deleted_by(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('manage_users') + '?tab=deleted')
        self.assertContains(response, 'siteadmin')

    def test_deleted_tab_shows_restore_button_for_site_admin(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('manage_users') + '?tab=deleted')
        self.assertContains(response, 'Restore')

    def test_deleted_tab_shows_permanent_delete_button_for_superuser_only(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('manage_users') + '?tab=deleted')
        self.assertContains(response, 'Permanently Delete')

    def test_deleted_tab_hides_permanent_delete_for_site_admin(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('manage_users') + '?tab=deleted')
        self.assertNotContains(response, 'Permanently Delete')

    def test_regular_user_cannot_access_deleted_tab(self):
        self.client.login(username='active', password='testpass123')
        response = self.client.get(reverse('manage_users') + '?tab=deleted')
        self.assertEqual(response.status_code, 403)

    def test_site_admin_cannot_see_site_admins_in_deleted_tab(self):
        deleted_admin = User.objects.create_user(
            username='deladmin', password='testpass123', is_site_admin=True,
            is_active=False, deleted_at=timezone.now(), deleted_by=self.superuser,
        )
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('manage_users') + '?tab=deleted')
        self.assertNotContains(response, 'deladmin')

    def test_superuser_sees_site_admins_in_deleted_tab(self):
        deleted_admin = User.objects.create_user(
            username='deladmin', password='testpass123', is_site_admin=True,
            is_active=False, deleted_at=timezone.now(), deleted_by=self.superuser,
        )
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('manage_users') + '?tab=deleted')
        self.assertContains(response, 'deladmin')


@tag("integration")
class UserRestoreTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123'
        )
        self.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True
        )
        self.deleted_user = User.objects.create_user(
            username='deleted', password='testpass123',
            is_active=False, deleted_at=timezone.now(), deleted_by=self.site_admin,
        )
        self.active_user = User.objects.create_user(
            username='active', password='testpass123'
        )

    def test_site_admin_can_access_restore_page(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('user_restore', kwargs={'pk': self.deleted_user.pk}))
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_access_restore_page(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('user_restore', kwargs={'pk': self.deleted_user.pk}))
        self.assertEqual(response.status_code, 200)

    def test_site_admin_can_restore_user(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post(reverse('user_restore', kwargs={'pk': self.deleted_user.pk}))
        self.assertEqual(response.status_code, 302)
        self.deleted_user.refresh_from_db()
        self.assertTrue(self.deleted_user.is_active)
        self.assertIsNone(self.deleted_user.deleted_at)
        self.assertIsNone(self.deleted_user.deleted_by)

    def test_superuser_can_restore_user(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.post(reverse('user_restore', kwargs={'pk': self.deleted_user.pk}))
        self.assertEqual(response.status_code, 302)
        self.deleted_user.refresh_from_db()
        self.assertTrue(self.deleted_user.is_active)
        self.assertIsNone(self.deleted_user.deleted_at)

    def test_cannot_restore_active_user(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.post(reverse('user_restore', kwargs={'pk': self.active_user.pk}))
        self.assertEqual(response.status_code, 404)

    def test_regular_user_cannot_restore(self):
        self.client.login(username='active', password='testpass123')
        response = self.client.post(reverse('user_restore', kwargs={'pk': self.deleted_user.pk}))
        self.assertEqual(response.status_code, 403)

    def test_restore_page_shows_username(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('user_restore', kwargs={'pk': self.deleted_user.pk}))
        self.assertContains(response, 'deleted')


@tag("integration")
class UserPermanentDeleteTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123'
        )
        self.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True
        )
        self.deleted_user = User.objects.create_user(
            username='deleted', password='testpass123',
            is_active=False, deleted_at=timezone.now(), deleted_by=self.superuser,
        )

    def test_superuser_can_access_permanent_delete_page(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('user_permanent_delete', kwargs={'pk': self.deleted_user.pk}))
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_permanently_delete_with_correct_username(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.post(reverse('user_permanent_delete', kwargs={'pk': self.deleted_user.pk}), {
            'confirm_username': 'deleted',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.deleted_user.pk).exists())

    def test_permanent_delete_fails_with_wrong_username(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.post(reverse('user_permanent_delete', kwargs={'pk': self.deleted_user.pk}), {
            'confirm_username': 'wrongname',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(pk=self.deleted_user.pk).exists())
        self.assertContains(response, 'Username did not match')

    def test_site_admin_cannot_access_permanent_delete(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('user_permanent_delete', kwargs={'pk': self.deleted_user.pk}))
        self.assertEqual(response.status_code, 403)

    def test_cannot_permanently_delete_active_user(self):
        active = User.objects.create_user(username='active2', password='testpass123')
        self.client.login(username='superuser', password='testpass123')
        response = self.client.post(reverse('user_permanent_delete', kwargs={'pk': active.pk}), {
            'confirm_username': 'active2',
        })
        self.assertEqual(response.status_code, 404)

    def test_permanent_delete_page_shows_username_confirmation(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(reverse('user_permanent_delete', kwargs={'pk': self.deleted_user.pk}))
        self.assertContains(response, "type the user's username to confirm")
        self.assertContains(response, '<code>deleted</code>', html=True)


@tag("integration")
class DeactivatedLoginMessageTest(TestCase):

    def setUp(self):
        self.deleted_user = User.objects.create_user(
            username='deactivated', password='testpass123',
            is_active=False, deleted_at=timezone.now(),
        )

    def test_soft_deleted_user_sees_deactivated_message(self):
        response = self.client.post(reverse('login'), {
            'username': 'deactivated',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'deactivated')

    def test_active_user_with_wrong_password_sees_normal_error(self):
        User.objects.create_user(username='activeguy', password='testpass123')
        response = self.client.post(reverse('login'), {
            'username': 'activeguy',
            'password': 'wrongpass',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'deactivated')


# ---------------------------------------------------------------------------
# test_admin_confirmation.py — ALL classes (1)
# ---------------------------------------------------------------------------

@tag("integration")
class AdminConfirmationTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='testpass123')
        self.other_admin = User.objects.create_user(username='other_admin', password='testpass123')
        self.organizer = User.objects.create_user(username='organizer', password='testpass123')
        self.member = User.objects.create_user(username='member', password='testpass123')
        self.group = Group.objects.create(name='Test Group', slug='test-group')
        GroupMembership.objects.create(user=self.admin, group=self.group, role='admin')
        GroupMembership.objects.create(user=self.other_admin, group=self.group, role='admin')
        GroupMembership.objects.create(user=self.organizer, group=self.group, role='organizer')
        GroupMembership.objects.create(user=self.member, group=self.group, role='member')

    def _post_action(self, user_id, action, confirmed=None):
        data = {'user_id': user_id, 'action': action}
        if confirmed is not None:
            data['confirmed'] = confirmed
        return self.client.post(
            reverse('group_members_manage', kwargs={'slug': self.group.slug}),
            data,
        )

    def test_demoting_admin_without_confirmation_renders_confirm_page(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'demote_member')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Are you sure')
        membership = GroupMembership.objects.get(user=self.other_admin, group=self.group)
        self.assertEqual(membership.role, 'admin')

    def test_demoting_admin_with_confirmation_performs_demotion(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'demote_member', confirmed='true')
        self.assertEqual(response.status_code, 200)
        membership = GroupMembership.objects.get(user=self.other_admin, group=self.group)
        self.assertEqual(membership.role, 'member')

    def test_removing_admin_without_confirmation_renders_confirm_page(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'remove')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Are you sure')
        self.assertTrue(
            GroupMembership.objects.filter(user=self.other_admin, group=self.group, role='admin').exists()
        )

    def test_removing_admin_with_confirmation_performs_removal(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'remove', confirmed='true')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            GroupMembership.objects.filter(user=self.other_admin, group=self.group).exists()
        )

    def test_demoting_admin_to_organizer_without_confirmation(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'demote_organizer')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Are you sure')
        membership = GroupMembership.objects.get(user=self.other_admin, group=self.group)
        self.assertEqual(membership.role, 'admin')

    def test_demoting_admin_to_organizer_with_confirmation(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'demote_organizer', confirmed='true')
        self.assertEqual(response.status_code, 200)
        membership = GroupMembership.objects.get(user=self.other_admin, group=self.group)
        self.assertEqual(membership.role, 'organizer')

    def test_non_admin_demotion_works_without_confirmation(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.organizer.pk, 'demote_member')
        self.assertEqual(response.status_code, 200)
        membership = GroupMembership.objects.get(user=self.organizer, group=self.group)
        self.assertEqual(membership.role, 'member')

    def test_non_admin_removal_works_without_confirmation(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.member.pk, 'remove')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            GroupMembership.objects.filter(user=self.member, group=self.group).exists()
        )

    def test_confirmation_page_shows_removal_warning(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'remove')
        self.assertContains(response, 'votes and RSVPs')

    def test_confirmation_page_cancel_link(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'demote_member')
        self.assertContains(response, reverse('group_members_manage', kwargs={'slug': self.group.slug}))

    def test_non_admin_demote_organizer_no_confirmation(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.organizer.pk, 'demote_organizer')
        self.assertEqual(response.status_code, 200)
        membership = GroupMembership.objects.get(user=self.organizer, group=self.group)
        self.assertEqual(membership.role, 'organizer')


# ---------------------------------------------------------------------------
# test_view_only.py — integration-tagged classes (2)
# ---------------------------------------------------------------------------

@tag("integration")
class ViewOnlyUserGETAccessTest(TestCase):

    def setUp(self):
        self.viewer = User.objects.create_user(
            username='viewer', password='p', is_view_only=True,
            email_verified=True,
        )
        self.group = Group.objects.create(
            name='Test Group', discoverable=True, join_policy='open',
        )
        GroupMembership.objects.create(
            user=self.viewer, group=self.group, role='member',
        )

    def test_can_access_dashboard(self):
        self.client.login(username='viewer', password='p')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_can_access_group_list(self):
        self.client.login(username='viewer', password='p')
        response = self.client.get(reverse('group_list'))
        self.assertEqual(response.status_code, 200)

    def test_can_access_game_list(self):
        self.client.login(username='viewer', password='p')
        response = self.client.get(reverse('game_list'))
        self.assertEqual(response.status_code, 200)

    def test_can_access_event_list(self):
        self.client.login(username='viewer', password='p')
        response = self.client.get(reverse('event_list'))
        self.assertEqual(response.status_code, 200)

    def test_can_access_group_dashboard(self):
        self.client.login(username='viewer', password='p')
        response = self.client.get(
            reverse('group_dashboard', kwargs={'slug': self.group.slug})
        )
        self.assertEqual(response.status_code, 200)

    def test_banner_shown_in_response(self):
        self.client.login(username='viewer', password='p')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Welcome, View Only Visitor')

    def test_banner_not_shown_for_regular_user(self):
        regular = User.objects.create_user(username='regular', password='p')
        self.client.login(username='regular', password='p')
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'Welcome, View Only Visitor')


@tag("integration")
class ViewOnlyUserPOSTBlockedTest(TestCase):

    def setUp(self):
        self.viewer = User.objects.create_user(
            username='viewer', password='p', is_view_only=True,
            email_verified=True,
        )

    def test_cannot_add_game(self):
        self.client.login(username='viewer', password='p')
        response = self.client.post(reverse('game_add'), {
            'name': 'Catan',
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(BoardGame.objects.filter(name='Catan').exists())

    def test_cannot_save_settings(self):
        self.client.login(username='viewer', password='p')
        response = self.client.post(reverse('user_settings'), {
            'email': 'new@test.com',
            'timezone': 'UTC',
        })
        self.assertEqual(response.status_code, 403)
        self.viewer.refresh_from_db()
        self.assertNotEqual(self.viewer.email, 'new@test.com')


@tag("integration")
class SiteLockdownViewToggleTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(username='superuser', password='testpass123')
        cls.site_admin = User.objects.create_user(username='siteadmin', password='testpass123', is_site_admin=True)
        cls.regular = User.objects.create_user(username='regular', password='testpass123')

    def test_superuser_can_activate_lockdown(self):
        self.client.login(username='superuser', password='testpass123')
        self.client.post(reverse('admin_settings'), {'site_lockdown_active': 'on'})
        settings = SiteSettings.load()
        self.assertTrue(settings.site_lockdown_active)

    def test_superuser_can_deactivate_lockdown(self):
        settings = SiteSettings.load()
        settings.site_lockdown_active = True
        settings.save()
        self.client.login(username='superuser', password='testpass123')
        self.client.post(reverse('admin_settings'), {'site_lockdown_deactivate': '1'})
        settings.refresh_from_db()
        self.assertFalse(settings.site_lockdown_active)

    def test_site_admin_cannot_activate_lockdown(self):
        self.client.login(username='siteadmin', password='testpass123')
        self.client.post(reverse('admin_settings'), {'site_lockdown_active': 'on'})
        settings = SiteSettings.load()
        self.assertFalse(settings.site_lockdown_active)

    def test_regular_user_cannot_activate_lockdown(self):
        self.client.login(username='regular', password='testpass123')
        self.client.post(reverse('admin_settings'), {'site_lockdown_active': 'on'})
        settings = SiteSettings.load()
        self.assertFalse(settings.site_lockdown_active)

    def test_superuser_can_toggle_allow_site_admins(self):
        settings = SiteSettings.load()
        settings.site_lockdown_active = True
        settings.save()
        self.client.login(username='superuser', password='testpass123')
        self.client.post(reverse('admin_settings'), {'site_lockdown_active': 'on', 'site_lockdown_allow_site_admins': 'on'})
        settings.refresh_from_db()
        self.assertTrue(settings.site_lockdown_allow_site_admins)

    def test_allow_site_admins_reset_when_lockdown_deactivated(self):
        settings = SiteSettings.load()
        settings.site_lockdown_active = True
        settings.site_lockdown_allow_site_admins = True
        settings.save()
        self.client.login(username='superuser', password='testpass123')
        self.client.post(reverse('admin_settings'), {'site_lockdown_deactivate': '1'})
        settings.refresh_from_db()
        self.assertFalse(settings.site_lockdown_active)
        self.assertFalse(settings.site_lockdown_allow_site_admins)


@tag("integration")
class SiteLockdownBannerTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.regular = User.objects.create_user(username='regular', password='testpass123')

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
        cls.superuser = User.objects.create_superuser(username='superuser', password='testpass123')
        cls.site_admin = User.objects.create_user(username='siteadmin', password='testpass123', is_site_admin=True)

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
        cls.regular = User.objects.create_user(username='regular', password='testpass123')

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
        cls.superuser = User.objects.create_superuser(username='superuser', password='testpass123')

    def test_register_view_redirects_during_lockdown(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 302)

    def test_register_view_post_fails_during_lockdown(self):
        SiteSettings.load()
        SiteSettings.objects.filter(pk=1).update(site_lockdown_active=True)
        response = self.client.post(reverse('register'), {
            'username': 'newuser', 'password1': 'StrongPass123!', 'password2': 'StrongPass123!',
        })
        self.assertFalse(User.objects.filter(username='newuser').exists())
