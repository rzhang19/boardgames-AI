import io
import os
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings, tag
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from club.models import BoardGame, Event, EventAttendance

User = get_user_model()


def _create_image(filename='test.jpg', size=(100, 100), fmt='JPEG'):
    img = Image.new('RGB', size, color='red')
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return SimpleUploadedFile(filename, buf.read(), content_type='image/jpeg')


@tag("integration")
class ProfileViewAccessTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
        )
        self.other = User.objects.create_user(
            username='otheruser', password='testpass123',
        )

    def test_profile_page_returns_200(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'otheruser'})
        )
        self.assertEqual(response.status_code, 200)

    def test_own_profile_returns_200(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'testuser'})
        )
        self.assertEqual(response.status_code, 200)

    def test_profile_shows_username(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'otheruser'})
        )
        self.assertContains(response, 'otheruser')

    def test_profile_shows_bio(self):
        self.other.bio = 'Hello, I love board games!'
        self.other.save()
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'otheruser'})
        )
        self.assertContains(response, 'Hello, I love board games!')

    def test_profile_404_for_nonexistent_user(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'nobody'})
        )
        self.assertEqual(response.status_code, 404)

    def test_profile_redirects_for_anonymous(self):
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'testuser'})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_own_profile_shows_edit_link(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'testuser'})
        )
        self.assertContains(response, 'Edit Profile')

    def test_other_profile_does_not_show_edit_link(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'otheruser'})
        )
        self.assertNotContains(response, 'Edit Profile')


@tag("integration")
class ProfilePrivacyTest(TestCase):

    def setUp(self):
        self.viewer = User.objects.create_user(
            username='viewer', password='testpass123',
        )
        self.owner = User.objects.create_user(
            username='owner', password='testpass123',
        )
        self.game = BoardGame.objects.create(
            name='Catan', owner=self.owner, complexity='medium',
        )
        self.event = Event.objects.create(
            title='Game Night',
            date=timezone.now() + timedelta(days=7),
            created_by=self.owner,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        EventAttendance.objects.create(user=self.owner, event=self.event)

    def test_games_visible_when_show_games_true(self):
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertContains(response, 'Catan')

    def test_games_hidden_when_show_games_false(self):
        self.owner.show_games = False
        self.owner.save()
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertNotContains(response, 'Catan')

    def test_events_visible_when_show_events_true(self):
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertContains(response, 'Game Night')

    def test_events_hidden_when_show_events_false(self):
        self.owner.show_events = False
        self.owner.save()
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertNotContains(response, 'Game Night')

    def test_date_joined_visible_when_show_true(self):
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertContains(response, 'Joined')

    def test_date_joined_hidden_when_show_false(self):
        self.owner.show_date_joined = False
        self.owner.save()
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertNotContains(response, 'Joined')

    def test_owner_sees_own_games_regardless_of_privacy(self):
        self.owner.show_games = False
        self.owner.save()
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertContains(response, 'Catan')

    def test_owner_sees_own_events_regardless_of_privacy(self):
        self.owner.show_events = False
        self.owner.save()
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertContains(response, 'Game Night')

    def test_owner_sees_own_date_joined_regardless_of_privacy(self):
        self.owner.show_date_joined = False
        self.owner.save()
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(
            reverse('public_profile', kwargs={'username': 'owner'})
        )
        self.assertContains(response, 'Joined')


@tag("integration")
class ProfilePictureUploadTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
        )
        self.client.login(username='testuser', password='testpass123')

    @override_settings(MEDIA_ROOT=os.path.join(settings.BASE_DIR, 'test_media'))
    def test_can_upload_profile_picture(self):
        image = _create_image()
        response = self.client.post(reverse('user_settings'), {
            'email': '',
            'timezone': 'UTC',
            'bio': '',
            'profile_picture': image,
            'show_games': True,
            'show_events': True,
            'show_date_joined': True,
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.profile_picture)

    def test_rejects_image_over_2mb(self):
        big_file = SimpleUploadedFile(
            'big.jpg', b'x' * (2 * 1024 * 1024 + 1),
            content_type='image/jpeg',
        )
        response = self.client.post(reverse('user_settings'), {
            'email': '',
            'timezone': 'UTC',
            'bio': '',
            'profile_picture': big_file,
            'show_games': True,
            'show_events': True,
            'show_date_joined': True,
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.profile_picture)

    @override_settings(MEDIA_ROOT=os.path.join(settings.BASE_DIR, 'test_media'))
    def test_can_update_bio(self):
        response = self.client.post(reverse('user_settings'), {
            'email': '',
            'timezone': 'UTC',
            'bio': 'I love Catan!',
            'show_games': True,
            'show_events': True,
            'show_date_joined': True,
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.bio, 'I love Catan!')

    @override_settings(MEDIA_ROOT=os.path.join(settings.BASE_DIR, 'test_media'))
    def test_can_toggle_privacy_settings(self):
        response = self.client.post(reverse('user_settings'), {
            'email': '',
            'timezone': 'UTC',
            'bio': '',
            'show_games': False,
            'show_events': False,
            'show_date_joined': False,
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.show_games)
        self.assertFalse(self.user.show_events)
        self.assertFalse(self.user.show_date_joined)


@tag("integration")
class ProfileLinkTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
        )
        self.client.login(username='testuser', password='testpass123')

    def test_dashboard_username_links_to_profile(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(
            response,
            reverse('public_profile', kwargs={'username': 'testuser'}),
        )

    def test_game_detail_owner_links_to_profile(self):
        game = BoardGame.objects.create(
            name='Catan', owner=self.user, complexity='medium',
        )
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(
            response,
            reverse('public_profile', kwargs={'username': 'testuser'}),
        )
