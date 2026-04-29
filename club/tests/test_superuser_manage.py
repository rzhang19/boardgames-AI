from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.core.signing import TimestampSigner
from django.urls import reverse
from django.utils import timezone

User = get_user_model()


def _build_formset_data(users, overrides=None):
    data = {
        'form-TOTAL_FORMS': str(len(users)),
        'form-INITIAL_FORMS': str(len(users)),
        'form-MIN_NUM_FORMS': '0',
        'form-MAX_NUM_FORMS': '1000',
    }
    for i, user in enumerate(users):
        data[f'form-{i}-id'] = str(user.pk)
        data[f'form-{i}-is_site_admin'] = 'on' if overrides and overrides.get(user.pk, {}).get('is_site_admin', user.is_site_admin) else ''
    if overrides:
        for user_pk, vals in overrides.items():
            if vals.get('is_site_admin'):
                for i, user in enumerate(users):
                    if user.pk == user_pk:
                        data[f'form-{i}-is_site_admin'] = 'on'
    return data


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
        signer = TimestampSigner()
        token = signer.sign(user.pk)
        response = self.client.get(reverse('user_set_password', kwargs={'token': token}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Set Your Password')

    def test_valid_token_sets_password(self):
        user = User.objects.create_user(
            username='invited', password='!',
            email='invited@example.com', email_verified=False
        )
        signer = TimestampSigner()
        token = signer.sign(user.pk)
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
        signer = TimestampSigner()
        token = signer.sign(user.pk)
        response = self.client.post(reverse('user_set_password', kwargs={'token': token}), {
            'new_password1': 'Str0ngP@ss123',
            'new_password2': 'DifferentP@ss456',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Set Your Password')


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


@tag("unit")
class CleanupDeletedUsersCommandTest(TestCase):

    def test_deletes_users_past_30_days(self):
        user = User.objects.create_user(
            username='expired', password='testpass123',
            is_active=False, deleted_at=timezone.now() - timezone.timedelta(days=31),
        )
        call_command('cleanup_deleted_users')
        self.assertFalse(User.objects.filter(pk=user.pk).exists())

    def test_keeps_users_within_30_days(self):
        user = User.objects.create_user(
            username='recent', password='testpass123',
            is_active=False, deleted_at=timezone.now() - timezone.timedelta(days=15),
        )
        call_command('cleanup_deleted_users')
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

    def test_does_not_delete_active_users(self):
        user = User.objects.create_user(
            username='active', password='testpass123',
        )
        call_command('cleanup_deleted_users')
        self.assertTrue(User.objects.filter(pk=user.pk).exists())
