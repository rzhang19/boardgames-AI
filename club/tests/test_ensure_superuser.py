from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from club.models import User


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
