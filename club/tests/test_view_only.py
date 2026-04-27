import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings, tag
from django.urls import reverse

from club.models import BoardGame, Group, GroupMembership

User = get_user_model()


@tag("unit")
class IsViewOnlyFieldTest(TestCase):

    def test_defaults_to_false(self):
        user = User.objects.create_user(username='normal', password='p')
        self.assertFalse(user.is_view_only)

    def test_can_set_true(self):
        user = User.objects.create_user(username='viewer', password='p', is_view_only=True)
        self.assertTrue(user.is_view_only)

    def test_existing_user_has_false(self):
        user = User.objects.create_user(username='existing', password='p')
        user.refresh_from_db()
        self.assertFalse(user.is_view_only)


@tag("unit")
class ViewOnlyContextProcessorTest(TestCase):

    def test_view_only_user_has_is_view_only_true(self):
        user = User.objects.create_user(username='viewer', password='p', is_view_only=True)
        self.client.login(username='viewer', password='p')
        response = self.client.get(reverse('dashboard'))
        self.assertTrue(response.context['is_view_only'])

    def test_regular_user_has_is_view_only_false(self):
        user = User.objects.create_user(username='regular', password='p')
        self.client.login(username='regular', password='p')
        response = self.client.get(reverse('dashboard'))
        self.assertFalse(response.context['is_view_only'])

    def test_anonymous_user_has_is_view_only_false(self):
        response = self.client.get(reverse('dashboard'))
        self.assertFalse(response.context['is_view_only'])


@tag("unit")
class ViewOnlyMiddlewareBlockTest(TestCase):

    def setUp(self):
        self.viewer = User.objects.create_user(
            username='viewer', password='p', is_view_only=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='p'
        )

    def test_post_blocked_for_view_only_user(self):
        self.client.login(username='viewer', password='p')
        response = self.client.post(reverse('game_add'), {
            'name': 'Test Game',
        })
        self.assertEqual(response.status_code, 403)

    def test_get_allowed_for_view_only_user(self):
        self.client.login(username='viewer', password='p')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_post_allowed_for_regular_user(self):
        self.client.login(username='regular', password='p')
        response = self.client.post(reverse('game_add'), {
            'name': 'Test Game',
        })
        self.assertNotEqual(response.status_code, 403)

    def test_logout_post_allowed_for_view_only_user(self):
        self.client.login(username='viewer', password='p')
        response = self.client.post(reverse('logout'))
        self.assertNotEqual(response.status_code, 403)

    def test_login_post_allowed_for_view_only_user(self):
        response = self.client.post(reverse('login'), {
            'username': 'viewer',
            'password': 'p',
        })
        self.assertNotEqual(response.status_code, 403)


@tag("unit")
class ViewOnlyMiddlewareMessageTest(TestCase):

    def setUp(self):
        self.viewer = User.objects.create_user(
            username='viewer', password='p', is_view_only=True
        )

    def test_blocked_post_returns_forbidden_message(self):
        self.client.login(username='viewer', password='p')
        response = self.client.post(reverse('game_add'), {
            'name': 'Test Game',
        })
        self.assertEqual(response.status_code, 403)
        self.assertIn(
            'This action is not available in view-only mode.',
            response.content.decode(),
        )


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


@tag("unit")
class SeedStagingViewOnlyTest(TestCase):

    @patch.dict(os.environ, {'SEED_USER_PASSWORD': 'testpw'})
    @override_settings(VIEW_ONLY_PASSWORD='ViewerPass123!')
    def test_creates_view_only_user_when_password_set(self):
        from django.core.management import call_command
        call_command('seed_staging')
        viewer = User.objects.filter(username='testviewer').first()
        self.assertIsNotNone(viewer)
        self.assertTrue(viewer.is_view_only)
        self.assertTrue(viewer.email_verified)

    @patch.dict(os.environ, {'SEED_USER_PASSWORD': 'testpw'})
    @override_settings(VIEW_ONLY_PASSWORD='ViewerPass123!')
    def test_view_only_user_in_public_group(self):
        from django.core.management import call_command
        call_command('seed_staging')
        viewer = User.objects.get(username='testviewer')
        membership = GroupMembership.objects.filter(
            user=viewer, group__name='Public Board Games Group',
        ).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, 'member')

    @patch.dict(os.environ, {'SEED_USER_PASSWORD': 'testpw'})
    @override_settings(VIEW_ONLY_PASSWORD='ViewerPass123!')
    def test_view_only_user_not_in_private_group(self):
        from django.core.management import call_command
        call_command('seed_staging')
        viewer = User.objects.get(username='testviewer')
        membership = GroupMembership.objects.filter(
            user=viewer, group__name='Workday Boardgames',
        ).first()
        self.assertIsNone(membership)

    @patch.dict(os.environ, {'SEED_USER_PASSWORD': 'testpw'})
    @override_settings(VIEW_ONLY_PASSWORD='')
    def test_skips_view_only_user_when_password_not_set(self):
        from django.core.management import call_command
        call_command('seed_staging')
        self.assertFalse(User.objects.filter(username='testviewer').exists())

    @patch.dict(os.environ, {'SEED_USER_PASSWORD': 'testpw'})
    @override_settings(
        VIEW_ONLY_USERNAME='customviewer',
        VIEW_ONLY_PASSWORD='CustomPass123!',
    )
    def test_uses_custom_username(self):
        from django.core.management import call_command
        call_command('seed_staging')
        self.assertTrue(User.objects.filter(username='customviewer').exists())
