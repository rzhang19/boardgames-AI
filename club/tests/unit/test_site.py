import os
from io import BytesIO, StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings, tag
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from club.models import BoardGame, Group, GroupMembership, SiteSettings, VerifiedIcon

User = get_user_model()


def _create_image(name='test.png'):
    img = Image.new('RGB', (1, 1), color='red')
    buffer = BytesIO()
    fmt = name.rsplit('.', 1)[-1].upper()
    if fmt == 'JPG':
        fmt = 'JPEG'
    img.save(buffer, format=fmt)
    return ContentFile(buffer.getvalue(), name=name)


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


@tag("unit")
class EnsureSuperuserTests(TestCase):

    def setUp(self):
        self.out = StringIO()

    @override_settings(SUPERUSER_USERNAME='operator', SUPERUSER_PASSWORD='TempPass123!')
    def test_creates_superuser_when_none_exists(self):
        call_command('ensure_superuser', stdout=self.out)

        user = User.objects.get(username='operator')
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_site_admin)
        self.assertTrue(user.check_password('TempPass123!'))
        self.assertIn('created', self.out.getvalue().lower())

    @override_settings(SUPERUSER_USERNAME='', SUPERUSER_PASSWORD='')
    def test_skips_when_env_vars_empty(self):
        call_command('ensure_superuser', stdout=self.out)

        self.assertFalse(User.objects.filter(username='operator').exists())
        self.assertIn('must be set', self.out.getvalue())

    @override_settings(SUPERUSER_USERNAME='operator', SUPERUSER_PASSWORD='')
    def test_skips_when_only_username_set(self):
        call_command('ensure_superuser', stdout=self.out)

        self.assertFalse(User.objects.filter(username='operator').exists())
        self.assertIn('must be set', self.out.getvalue())

    @override_settings(SUPERUSER_USERNAME='', SUPERUSER_PASSWORD='TempPass123!')
    def test_skips_when_only_password_set(self):
        call_command('ensure_superuser', stdout=self.out)

        self.assertFalse(User.objects.filter(is_superuser=True).exists())
        self.assertIn('must be set', self.out.getvalue())

    @override_settings(SUPERUSER_USERNAME='operator', SUPERUSER_PASSWORD='TempPass123!')
    def test_does_not_overwrite_existing_superuser_password(self):
        User.objects.create_superuser(
            username='operator', password='OriginalPass456!'
        )

        call_command('ensure_superuser', stdout=self.out)

        user = User.objects.get(username='operator')
        self.assertTrue(user.check_password('OriginalPass456!'))
        self.assertFalse(user.check_password('TempPass123!'))
        self.assertIn('already exists', self.out.getvalue())

    @override_settings(SUPERUSER_USERNAME='operator', SUPERUSER_PASSWORD='NewPass789!')
    def test_force_deletes_and_recreates(self):
        User.objects.create_superuser(
            username='operator', password='OldPass111!'
        )

        call_command('ensure_superuser', '--force', stdout=self.out)

        user = User.objects.get(username='operator')
        self.assertTrue(user.check_password('NewPass789!'))
        self.assertFalse(user.check_password('OldPass111!'))
        self.assertIn('--force', self.out.getvalue())

    @override_settings(SUPERUSER_USERNAME='', SUPERUSER_PASSWORD='')
    def test_force_with_no_env_vars_does_not_create(self):
        call_command('ensure_superuser', '--force', stdout=self.out)

        self.assertFalse(User.objects.filter(is_superuser=True).exists())
        self.assertIn('must be set', self.out.getvalue())

    @override_settings(SUPERUSER_USERNAME='operator', SUPERUSER_PASSWORD='TempPass123!')
    def test_force_creates_when_no_user_exists(self):
        call_command('ensure_superuser', '--force', stdout=self.out)

        user = User.objects.get(username='operator')
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password('TempPass123!'))


@tag("unit")
class VerifiedIconModelTest(TestCase):

    def test_create_verified_icon(self):
        icon = VerifiedIcon.objects.create(name='Dice', image=_create_image('dice.png'))
        self.assertEqual(icon.name, 'Dice')
        self.assertTrue(icon.image.name.startswith('verified_icons/'))
        self.assertTrue(icon.image.name.endswith('.png'))

    def test_verified_icon_str(self):
        icon = VerifiedIcon.objects.create(name='Dice', image=_create_image('dice.png'))
        self.assertEqual(str(icon), 'Dice')

    def test_user_verified_icon_fk(self):
        icon = VerifiedIcon.objects.create(name='Dice', image=_create_image('dice.png'))
        user = User.objects.create_user(
            username='testuser', password='testpass123',
            email_verified=True, verified_icon=icon,
        )
        self.assertEqual(user.verified_icon, icon)

    def test_user_verified_icon_nullable(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        self.assertIsNone(user.verified_icon)


@tag("unit")
class VerifiedIconFormValidationTest(TestCase):

    def setUp(self):
        from club.forms import VerifiedIconForm
        self.form_class = VerifiedIconForm

    def _make_svg(self, name='test.svg'):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="10"/></svg>'
        return ContentFile(svg, name=name)

    def test_svg_upload_rejected(self):
        form = self.form_class(
            data={'name': 'Icon'},
            files={'image': self._make_svg('icon.svg')},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('image', form.errors)

    def test_invalid_extension_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        img = Image.new('RGB', (1, 1), color='red')
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        file = SimpleUploadedFile('icon.exe', buffer.getvalue(), content_type='application/octet-stream')
        form = self.form_class(
            data={'name': 'Icon'},
            files={'image': file},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('image', form.errors)

    def test_valid_png_accepted(self):
        img = Image.new('RGB', (1, 1), color='red')
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        file = ContentFile(buffer.getvalue(), name='icon.png')
        form = self.form_class(
            data={'name': 'Icon'},
            files={'image': file},
        )
        self.assertTrue(form.is_valid())

    def test_valid_jpeg_accepted(self):
        img = Image.new('RGB', (1, 1), color='red')
        buffer = BytesIO()
        img.save(buffer, format='JPEG')
        file = ContentFile(buffer.getvalue(), name='icon.jpg')
        form = self.form_class(
            data={'name': 'Icon'},
            files={'image': file},
        )
        self.assertTrue(form.is_valid())

    def test_valid_gif_accepted(self):
        img = Image.new('RGB', (1, 1), color='red')
        buffer = BytesIO()
        img.save(buffer, format='GIF')
        file = ContentFile(buffer.getvalue(), name='icon.gif')
        form = self.form_class(
            data={'name': 'Icon'},
            files={'image': file},
        )
        self.assertTrue(form.is_valid())

    def test_valid_webp_accepted(self):
        img = Image.new('RGB', (1, 1), color='red')
        buffer = BytesIO()
        img.save(buffer, format='WEBP')
        file = ContentFile(buffer.getvalue(), name='icon.webp')
        form = self.form_class(
            data={'name': 'Icon'},
            files={'image': file},
        )
        self.assertTrue(form.is_valid())

    def test_mime_mismatch_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        file = SimpleUploadedFile('icon.png', b'not image data', content_type='application/pdf')
        form = self.form_class(
            data={'name': 'Icon'},
            files={'image': file},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('image', form.errors)

    def test_oversized_file_rejected(self):
        from unittest.mock import MagicMock
        img = Image.new('RGB', (1, 1), color='red')
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        file = ContentFile(buffer.getvalue(), name='icon.png')
        file.size = 3 * 1024 * 1024
        form = self.form_class(
            data={'name': 'Icon'},
            files={'image': file},
        )
        self.assertFalse(form.is_valid())
        self.assertIn('image', form.errors)


@tag("unit")
class FeedbackConnectionTest(TestCase):

    def test_send_real_emails_false_returns_none(self):
        from club.views import _get_feedback_connection
        with self.settings(SEND_REAL_EMAILS=False):
            self.assertIsNone(_get_feedback_connection())

    def test_send_real_emails_true_returns_smtp_connection(self):
        from django.core.mail.backends.smtp import EmailBackend
        from club.views import _get_feedback_connection
        with self.settings(SEND_REAL_EMAILS=True):
            connection = _get_feedback_connection()
            self.assertIsInstance(connection, EmailBackend)


@tag("unit")
class FeedbackFormTest(TestCase):

    def test_feedback_type_choices(self):
        from club.forms import FeedbackForm
        form = FeedbackForm()
        choice_values = [c[0] for c in form.fields['feedback_type'].choices]
        self.assertEqual(choice_values, ['bug', 'feature', 'admin', 'community', 'other'])

    def test_message_max_length(self):
        from club.forms import FeedbackForm
        form = FeedbackForm(data={
            'feedback_type': 'bug',
            'email': 'test@example.com',
            'message': 'x' * 1001,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('message', form.errors)

    def test_email_field_required(self):
        from club.forms import FeedbackForm
        form = FeedbackForm(data={
            'feedback_type': 'bug',
            'email': '',
            'message': 'Hello',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_message_field_required(self):
        from club.forms import FeedbackForm
        form = FeedbackForm(data={
            'feedback_type': 'bug',
            'email': 'test@example.com',
            'message': '',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('message', form.errors)

    def test_valid_form(self):
        from club.forms import FeedbackForm
        form = FeedbackForm(data={
            'feedback_type': 'feature',
            'email': 'test@example.com',
            'message': 'I would love a dark mode!',
        })
        self.assertTrue(form.is_valid())

    def test_invalid_email_rejected(self):
        from club.forms import FeedbackForm
        form = FeedbackForm(data={
            'feedback_type': 'bug',
            'email': 'not-an-email',
            'message': 'Hello',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
