from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.signing import TimestampSigner
from django.urls import reverse

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
class ManageUsersPreviewTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123'
        )
        self.user1 = User.objects.create_user(
            username='user1', password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='user2', password='testpass123'
        )
        self.user3 = User.objects.create_user(
            username='user3', password='testpass123'
        )
        self.client.login(username='superuser', password='testpass123')

    def test_preview_no_changes_shows_no_changes_message(self):
        data = {
            'form-TOTAL_FORMS': '3',
            'form-INITIAL_FORMS': '3',
            'form-MIN_NUM_FORMS': '0',
            'form-MAX_NUM_FORMS': '1000',
            'form-0-id': str(self.user1.pk),
            'form-1-id': str(self.user2.pk),
            'form-2-id': str(self.user3.pk),
        }
        response = self.client.post(reverse('manage_users'), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No changes')


@tag("integration")
class ManageUsersConfirmTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123'
        )
        self.user1 = User.objects.create_user(
            username='user1', password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='user2', password='testpass123'
        )
        self.client.login(username='superuser', password='testpass123')

    def test_confirm_with_no_pending_changes_does_nothing(self):
        session = self.client.session
        session['pending_role_changes'] = {}
        session.save()

        response = self.client.post(reverse('manage_users_confirm'))
        self.assertEqual(response.status_code, 302)

        self.user1.refresh_from_db()
        self.user2.refresh_from_db()
        self.assertFalse(self.user1.is_site_admin)
        self.assertFalse(self.user2.is_site_admin)

    def test_superuser_can_promote_site_admin(self):
        session = self.client.session
        session['pending_role_changes'] = {
            str(self.user1.pk): {'is_site_admin': True},
        }
        session.save()

        self.client.post(reverse('manage_users_confirm'))
        self.user1.refresh_from_db()
        self.assertTrue(self.user1.is_site_admin)


@tag("integration")
class ManageUsersCancelTest(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123'
        )
        self.user1 = User.objects.create_user(
            username='user1', password='testpass123'
        )
        self.client.login(username='superuser', password='testpass123')

    def test_cancel_clears_session_and_redirects(self):
        session = self.client.session
        session['pending_role_changes'] = {
            str(self.user1.pk): {'is_site_admin': True},
        }
        session.save()

        response = self.client.get(reverse('manage_users_cancel'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('manage_users'))

        self.user1.refresh_from_db()
        self.assertFalse(self.user1.is_site_admin)

    def test_cancel_on_form_page_redirects_to_dashboard(self):
        response = self.client.post(reverse('manage_users'), {
            'cancel': 'true',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))


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
        self.assertFalse(User.objects.filter(pk=self.target.pk).exists())

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
        session = self.client.session
        session['pending_role_changes'] = {
            str(self.site_admin.pk): {'is_site_admin': False},
        }
        session.save()

        self.client.post(reverse('manage_users_confirm'))
        self.site_admin.refresh_from_db()
        self.assertFalse(self.site_admin.is_site_admin)

    def test_site_admin_sees_site_admin_column(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Site Admin')

    def test_site_admin_can_promote_to_site_admin_via_preview_and_confirm(self):
        self.client.login(username='siteadmin', password='testpass123')
        data = _build_formset_data(
            [self.regular],
            {self.regular.pk: {'is_site_admin': True}},
        )
        response = self.client.post(reverse('manage_users'), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'regular')

        self.client.post(reverse('manage_users_confirm'))
        self.regular.refresh_from_db()
        self.assertTrue(self.regular.is_site_admin)
