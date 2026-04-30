import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from club.models import (
    BoardGame, Event, EventAttendance, Group, GroupMembership, Vote,
)

User = get_user_model()


def _make_admin(user, group):
    return GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_member(user, group):
    return GroupMembership.objects.create(user=user, group=group, role='member')


def _create_image(width=800, height=800):
    img = Image.new('RGB', (width, height), color='red')
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)
    buf.name = 'test.jpg'
    return buf


# ---------------------------------------------------------------------------
# 9a — Full lifecycle integration test
# ---------------------------------------------------------------------------

@tag("system")
class FullGroupLifecycleTest(TestCase):

    def setUp(self):
        self.creator = User.objects.create_user(
            username='creator', password='testpass123',
        )
        self.joiner = User.objects.create_user(
            username='joiner', password='testpass123',
        )

    def test_full_open_group_lifecycle(self):
        # 1. Create group
        self.client.login(username='creator', password='testpass123')
        resp = self.client.post(reverse('group_create'), {
            'name': 'Lifecycle Group',
            'description': 'Testing the full lifecycle',
            'join_policy': 'open',
            'discoverable': True,
        })
        self.assertEqual(resp.status_code, 302)
        group = Group.objects.get(name='Lifecycle Group')
        self.assertTrue(GroupMembership.objects.filter(
            user=self.creator, group=group, role='admin',
        ).exists())

        # 2. Another user joins (open policy)
        self.client.login(username='joiner', password='testpass123')
        resp = self.client.post(reverse('group_join', kwargs={'slug': group.slug}))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(GroupMembership.objects.filter(
            user=self.joiner, group=group, role='member',
        ).exists(), 'Joiner should be a member after joining')

        # 3. Creator adds an event
        self.client.login(username='creator', password='testpass123')
        future = (timezone.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        resp = self.client.post(reverse('event_add', kwargs={'slug': group.slug}), {
            'title': 'Lifecycle Event',
            'date': future,
            'time': '19:00',
            'location': 'Test Location',
        })
        self.assertEqual(resp.status_code, 302)
        event = Event.objects.get(title='Lifecycle Event')
        self.assertEqual(event.group, group)

        # 4. Both RSVP
        for user in [self.creator, self.joiner]:
            self.client.login(username=user.username, password='testpass123')
            resp = self.client.post(reverse('event_rsvp', kwargs={'slug': event.group.slug, 'pk': event.pk}))
            self.assertEqual(resp.status_code, 302)
        self.assertTrue(EventAttendance.objects.filter(
            user=self.joiner, event=event,
        ).exists())
        self.assertTrue(EventAttendance.objects.filter(
            user=self.creator, event=event,
        ).exists())

        # 5. Both users vote
        game1 = BoardGame.objects.create(name='Catan', owner=self.creator)
        game2 = BoardGame.objects.create(name='Chess', owner=self.creator)
        event.is_active = True
        event.voting_open = True
        event.save()

        for user, game in [(self.creator, game1), (self.joiner, game2)]:
            self.client.login(username=user.username, password='testpass123')
            resp = self.client.post(reverse('event_vote', kwargs={'slug': event.group.slug, 'pk': event.pk}), {
                'form-TOTAL_FORMS': '1',
                'form-INITIAL_FORMS': '0',
                'form-MIN_NUM_FORMS': '0',
                'form-MAX_NUM_FORMS': '1000',
                'form-0-board_game': str(game.pk),
                'form-0-rank': '1',
            })
            self.assertEqual(resp.status_code, 302)
        self.assertEqual(Vote.objects.filter(event=event).count(), 2)

        # 6. View results
        self.client.login(username='creator', password='testpass123')
        resp = self.client.get(reverse('event_results', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Catan')
        self.assertContains(resp, 'Chess')

        # 7. Joiner leaves
        self.client.login(username='joiner', password='testpass123')
        resp = self.client.post(reverse('group_leave', kwargs={'slug': group.slug}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(GroupMembership.objects.filter(
            user=self.joiner, group=group,
        ).exists())
        self.assertFalse(EventAttendance.objects.filter(
            user=self.joiner, event=event,
        ).exists())

        # 8. Creator leaves (last member) → disbands
        self.client.login(username='creator', password='testpass123')
        resp = self.client.post(reverse('group_leave', kwargs={'slug': group.slug}))
        self.assertEqual(resp.status_code, 302)
        group.refresh_from_db()
        self.assertTrue(group.is_disbanded)

    def test_request_join_lifecycle(self):
        group = Group.objects.create(
            name='Request Group', join_policy='request',
            discoverable=True,
        )
        _make_admin(self.creator, group)

        # Joiner submits request
        self.client.login(username='joiner', password='testpass123')
        resp = self.client.post(reverse('group_join', kwargs={'slug': group.slug}))
        self.assertEqual(resp.status_code, 200)
        from club.models import GroupJoinRequest
        req = GroupJoinRequest.objects.get(user=self.joiner, group=group)
        self.assertEqual(req.status, 'pending')

        # Creator approves
        self.client.login(username='creator', password='testpass123')
        resp = self.client.post(reverse('group_join_request_manage', kwargs={'slug': group.slug}), {
            'request_id': str(req.pk),
            'action': 'approve',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(GroupMembership.objects.filter(
            user=self.joiner, group=group, role='member',
        ).exists())

    def test_invite_lifecycle(self):
        group = Group.objects.create(
            name='Invite Group', join_policy='invite_only',
            discoverable=False,
        )
        _make_admin(self.creator, group)

        # Creator generates invite
        self.client.login(username='creator', password='testpass123')
        resp = self.client.post(reverse('group_invite_create', kwargs={'slug': group.slug}))
        self.assertEqual(resp.status_code, 200)
        from club.models import GroupInvite
        invite = GroupInvite.objects.get(group=group)

        # Joiner accepts invite
        self.client.login(username='joiner', password='testpass123')
        resp = self.client.get(reverse('group_invite_accept', kwargs={'token': invite.token}))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(GroupMembership.objects.filter(
            user=self.joiner, group=group, role='member',
        ).exists())


# ---------------------------------------------------------------------------
# 9e — Image upload with Pillow compression
# ---------------------------------------------------------------------------

@tag("integration")
class GroupImageCompressionTest(TestCase):

    def setUp(self):
        self.creator = User.objects.create_user(
            username='creator', password='testpass123',
        )
        self.client.login(username='creator', password='testpass123')

    def test_create_group_resizes_large_image(self):
        large_img = _create_image(2000, 2000)
        resp = self.client.post(reverse('group_create'), {
            'name': 'Image Group',
            'join_policy': 'open',
            'discoverable': True,
            'image': large_img,
        })
        self.assertEqual(resp.status_code, 302)
        group = Group.objects.get(name='Image Group')
        self.assertTrue(group.image)
        img = Image.open(group.image)
        self.assertLessEqual(img.width, 600)
        self.assertLessEqual(img.height, 600)

    def test_create_group_small_image_unchanged(self):
        small_img = _create_image(100, 100)
        resp = self.client.post(reverse('group_create'), {
            'name': 'Small Image Group',
            'join_policy': 'open',
            'discoverable': True,
            'image': small_img,
        })
        self.assertEqual(resp.status_code, 302)
        group = Group.objects.get(name='Small Image Group')
        self.assertTrue(group.image)

    def test_create_group_without_image(self):
        resp = self.client.post(reverse('group_create'), {
            'name': 'No Image Group',
            'join_policy': 'open',
            'discoverable': True,
        })
        self.assertEqual(resp.status_code, 302)
        group = Group.objects.get(name='No Image Group')
        self.assertFalse(bool(group.image))

    def test_settings_update_resizes_image(self):
        group = Group.objects.create(name='Settings Group')
        _make_admin(self.creator, group)
        large_img = _create_image(1500, 1500)
        resp = self.client.post(reverse('group_settings', kwargs={'slug': group.slug}), {
            'name': 'Settings Group',
            'join_policy': 'open',
            'discoverable': True,
            'max_members': 50,
            'image': large_img,
        })
        self.assertEqual(resp.status_code, 302)
        group.refresh_from_db()
        self.assertTrue(group.image)
        img = Image.open(group.image)
        self.assertLessEqual(img.width, 600)
        self.assertLessEqual(img.height, 600)


# ---------------------------------------------------------------------------
# 9c/9g — Disbanding cascade: Votes + EventAttendance
# ---------------------------------------------------------------------------

@tag("unit")
class DisbandingCascadeTest(TestCase):

    def test_cleanup_deletes_votes_and_attendance(self):
        user = User.objects.create_user(username='cascade', password='testpass123')
        group = Group.objects.create(name='Cascade')
        GroupMembership.objects.create(user=user, group=group)
        event = Event.objects.create(
            title='Cascade Event',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=user,
            group=group,
        )
        EventAttendance.objects.create(user=user, event=event)
        game = BoardGame.objects.create(name='Catan', owner=user)
        Vote.objects.create(user=user, event=event, board_game=game, rank=1)

        self.assertEqual(Vote.objects.filter(event=event).count(), 1)
        self.assertEqual(EventAttendance.objects.filter(event=event).count(), 1)

        group.disbanded_at = timezone.now() - timedelta(days=31)
        group.save()

        from django.core.management import call_command
        from io import StringIO
        call_command('cleanup_disbanded_groups', stdout=StringIO())

        self.assertFalse(Group.objects.filter(pk=group.pk).exists())
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())
        self.assertFalse(Vote.objects.filter(event__pk=event.pk).exists())
        self.assertFalse(EventAttendance.objects.filter(event__pk=event.pk).exists())
        self.assertFalse(GroupMembership.objects.filter(group__pk=group.pk).exists())
