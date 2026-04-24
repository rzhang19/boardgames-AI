from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, tag
from django.urls import reverse

from club.models import BoardGame, Event, EventAttendance, Group, VerifiedIcon, Vote

User = get_user_model()


def _create_svg(name='test.svg'):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/></svg>'
    return ContentFile(svg, name=name)


@tag("unit")
class VerifiedIconModelTest(TestCase):

    def test_create_verified_icon(self):
        icon = VerifiedIcon.objects.create(name='Dice', image=_create_svg('dice.svg'))
        self.assertEqual(icon.name, 'Dice')
        self.assertTrue(icon.image.name.startswith('verified_icons/'))
        self.assertTrue(icon.image.name.endswith('.svg'))

    def test_verified_icon_str(self):
        icon = VerifiedIcon.objects.create(name='Dice', image=_create_svg('dice.svg'))
        self.assertEqual(str(icon), 'Dice')

    def test_user_verified_icon_fk(self):
        icon = VerifiedIcon.objects.create(name='Dice', image=_create_svg('dice.svg'))
        user = User.objects.create_user(
            username='testuser', password='testpass123',
            email_verified=True, verified_icon=icon,
        )
        self.assertEqual(user.verified_icon, icon)

    def test_user_verified_icon_nullable(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        self.assertIsNone(user.verified_icon)


@tag("integration")
class SettingsIconPickerTest(TestCase):

    def setUp(self):
        self.icon = VerifiedIcon.objects.create(
            name='Dice', image=_create_svg('dice.svg'),
        )
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
            email='test@example.com', email_verified=True,
        )
        self.client.login(username='testuser', password='testpass123')

    def test_settings_page_shows_icon_picker_when_verified(self):
        response = self.client.get(reverse('user_settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'verified-icon-picker')

    def test_settings_page_shows_icon_options(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'Dice')

    def test_save_verified_icon(self):
        self.client.post(reverse('user_settings'), {
            'email': 'test@example.com',
            'timezone': 'UTC',
            'verified_icon': str(self.icon.pk),
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.verified_icon, self.icon)

    def test_change_verified_icon(self):
        icon2 = VerifiedIcon.objects.create(
            name='Star', image=_create_svg('star.svg'),
        )
        self.user.verified_icon = self.icon
        self.user.save()
        self.client.post(reverse('user_settings'), {
            'email': 'test@example.com',
            'timezone': 'UTC',
            'verified_icon': str(icon2.pk),
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.verified_icon, icon2)

    def test_clear_verified_icon(self):
        self.user.verified_icon = self.icon
        self.user.save()
        self.client.post(reverse('user_settings'), {
            'email': 'test@example.com',
            'timezone': 'UTC',
            'verified_icon': '',
        })
        self.user.refresh_from_db()
        self.assertIsNone(self.user.verified_icon)

    def test_invalid_icon_pk_rejected(self):
        self.client.post(reverse('user_settings'), {
            'email': 'test@example.com',
            'timezone': 'UTC',
            'verified_icon': '99999',
        })
        self.user.refresh_from_db()
        self.assertIsNone(self.user.verified_icon)


@tag("integration")
class SettingsIconPickerUnverifiedTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
            email='test@example.com', email_verified=False,
        )
        VerifiedIcon.objects.create(name='Dice', image=_create_svg('dice.svg'))
        self.client.login(username='testuser', password='testpass123')

    def test_unverified_user_sees_icon_picker_disabled(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'verified-icon-picker')
        self.assertContains(response, 'disabled')

    def test_unverified_user_cannot_save_icon(self):
        icon = VerifiedIcon.objects.first()
        self.client.post(reverse('user_settings'), {
            'email': 'test@example.com',
            'timezone': 'UTC',
            'verified_icon': str(icon.pk),
        })
        self.user.refresh_from_db()
        self.assertIsNone(self.user.verified_icon)


@tag("integration")
class VerifiedBadgeCustomIconRenderingTest(TestCase):

    def setUp(self):
        self.icon = VerifiedIcon.objects.create(
            name='Dice', image=_create_svg('dice.svg'),
        )
        self.group = Group.objects.create(name='Test Group')

    def test_custom_icon_renders_on_dashboard(self):
        user = User.objects.create_user(
            username='iconuser', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        BoardGame.objects.create(name='Catan', owner=user)
        self.client.login(username='iconuser', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'verified-badge')

    def test_no_icon_renders_default_checkmark(self):
        user = User.objects.create_user(
            username='defaultuser', password='testpass123',
            email_verified=True,
        )
        BoardGame.objects.create(name='Catan', owner=user)
        self.client.login(username='defaultuser', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'verified-badge')

    def test_custom_icon_renders_on_game_list(self):
        owner = User.objects.create_user(
            username='iconowner', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        BoardGame.objects.create(name='Catan', owner=owner)
        self.client.login(username='iconowner', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'verified-badge')

    def test_custom_icon_renders_on_game_detail(self):
        owner = User.objects.create_user(
            username='iconowner', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        game = BoardGame.objects.create(name='Catan', owner=owner)
        self.client.login(username='iconowner', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(response, 'verified-badge')

    def test_custom_icon_renders_on_event_list(self):
        creator = User.objects.create_user(
            username='iconcreator', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=creator, group=self.group,
        )
        self.client.login(username='iconcreator', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, 'verified-badge')

    def test_custom_icon_renders_on_event_detail_creator(self):
        creator = User.objects.create_user(
            username='iconcreator', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=creator, group=self.group,
        )
        self.client.login(username='iconcreator', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertContains(response, 'verified-badge')

    def test_custom_icon_renders_on_event_detail_attendee(self):
        creator = User.objects.create_user(
            username='creator', password='testpass123',
            email_verified=True,
        )
        attendee = User.objects.create_user(
            username='iconattendee', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=creator, group=self.group,
        )
        EventAttendance.objects.create(user=attendee, event=event)
        self.client.login(username='iconattendee', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertContains(response, 'verified-badge')

    def test_custom_icon_renders_on_event_results(self):
        voter = User.objects.create_user(
            username='iconvoter', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=voter, show_individual_votes=True, group=self.group,
        )
        game = BoardGame.objects.create(name='Catan', owner=voter)
        EventAttendance.objects.create(user=voter, event=event)
        Vote.objects.create(user=voter, event=event, board_game=game, rank=1)
        response = self.client.get(reverse('event_results', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertContains(response, 'verified-badge')

    def test_custom_icon_renders_on_manage_users(self):
        admin = User.objects.create_user(
            username='admin', password='testpass123',
            is_site_admin=True, email_verified=True,
        )
        User.objects.create_user(
            username='iconuser', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertContains(response, 'verified-badge')


@tag("integration")
class IconManagementAccessTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123',
            is_site_admin=True, email_verified=True,
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123',
            email_verified=True,
        )
        self.client.login(username='admin', password='testpass123')

    def test_admin_sees_icon_management_section(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'manage-verified-icons')

    def test_regular_user_does_not_see_icon_management_section(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(reverse('user_settings'))
        self.assertNotContains(response, 'manage-verified-icons')

    def test_admin_sees_existing_icons_in_management(self):
        VerifiedIcon.objects.create(name='Dice', image=_create_svg('dice.svg'))
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'Dice')
        self.assertContains(response, 'delete-icon')


@tag("integration")
class IconManagementAddTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123',
            is_site_admin=True, email_verified=True,
        )
        self.client.login(username='admin', password='testpass123')

    def test_add_icon_success(self):
        response = self.client.post(reverse('add_verified_icon'), {
            'name': 'Trophy',
            'image': _create_svg('trophy.svg'),
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(VerifiedIcon.objects.filter(name='Trophy').exists())

    def test_add_icon_without_name_fails(self):
        response = self.client.post(reverse('add_verified_icon'), {
            'name': '',
            'image': _create_svg('trophy.svg'),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(VerifiedIcon.objects.exists())

    def test_add_icon_without_image_fails(self):
        response = self.client.post(reverse('add_verified_icon'), {
            'name': 'Trophy',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(VerifiedIcon.objects.exists())

    def test_add_icon_duplicate_name_fails(self):
        VerifiedIcon.objects.create(name='Dice', image=_create_svg('dice.svg'))
        response = self.client.post(reverse('add_verified_icon'), {
            'name': 'Dice',
            'image': _create_svg('dice2.svg'),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(VerifiedIcon.objects.count(), 1)

    def test_regular_user_cannot_add_icon(self):
        regular = User.objects.create_user(
            username='regular', password='testpass123',
            email_verified=True,
        )
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(reverse('add_verified_icon'), {
            'name': 'Trophy',
            'image': _create_svg('trophy.svg'),
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(VerifiedIcon.objects.exists())


@tag("integration")
class IconManagementDeleteTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', password='testpass123',
            is_site_admin=True, email_verified=True,
        )
        self.icon = VerifiedIcon.objects.create(
            name='Dice', image=_create_svg('dice.svg'),
        )
        self.client.login(username='admin', password='testpass123')

    def test_delete_unused_icon_success(self):
        response = self.client.post(
            reverse('delete_verified_icon', kwargs={'pk': self.icon.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(VerifiedIcon.objects.filter(pk=self.icon.pk).exists())

    def test_delete_icon_in_use_fails(self):
        User.objects.create_user(
            username='iconuser', password='testpass123',
            email_verified=True, verified_icon=self.icon,
        )
        response = self.client.post(
            reverse('delete_verified_icon', kwargs={'pk': self.icon.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(VerifiedIcon.objects.filter(pk=self.icon.pk).exists())

    def test_delete_nonexistent_icon_404(self):
        response = self.client.post(
            reverse('delete_verified_icon', kwargs={'pk': 99999})
        )
        self.assertEqual(response.status_code, 404)

    def test_regular_user_cannot_delete_icon(self):
        regular = User.objects.create_user(
            username='regular', password='testpass123',
            email_verified=True,
        )
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(
            reverse('delete_verified_icon', kwargs={'pk': self.icon.pk})
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(VerifiedIcon.objects.filter(pk=self.icon.pk).exists())
