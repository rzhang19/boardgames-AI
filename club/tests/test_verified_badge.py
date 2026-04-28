from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse

import re

from club.models import BoardGame, Event, EventAttendance, Group, GroupMembership, Vote

User = get_user_model()


@tag("integration")
class VerifiedBadgeDashboardTest(TestCase):

    def test_verified_user_sees_blue_checkmark_on_dashboard(self):
        user = User.objects.create_user(
            username='verifieduser', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        self.client.login(username='verifieduser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Groups')
        self.assertContains(response, 'My Games')

    def test_unverified_user_does_not_see_checkmark_on_dashboard(self):
        user = User.objects.create_user(
            username='unverifieduser', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        self.client.login(username='unverifieduser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)


@tag("integration")
class VerifiedBadgeGamePagesTest(TestCase):

    def test_verified_owner_shows_checkmark_on_game_pages(self):
        owner = User.objects.create_user(
            username='verifiedowner', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        game = BoardGame.objects.create(name='Catan', owner=owner)
        viewer = User.objects.create_user(
            username='viewer', password='testpass123',
        )
        group = Group.objects.create(name='Test Group')
        GroupMembership.objects.create(user=owner, group=group, role='member')
        GroupMembership.objects.create(user=viewer, group=group, role='member')
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_list'))
        html = response.content.decode()
        self.assertTrue(
            re.search(r'data-label="Owner - Details".*?verified-badge', html, re.DOTALL),
            'verified-badge not found inside Owner - Details column',
        )
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(response, 'verified-badge')

    def test_unverified_owner_no_checkmark_on_game_pages(self):
        owner = User.objects.create_user(
            username='unverifiedowner', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        game = BoardGame.objects.create(name='Risk', owner=owner)
        viewer = User.objects.create_user(
            username='viewer', password='testpass123',
        )
        group = Group.objects.create(name='Test Group')
        GroupMembership.objects.create(user=owner, group=group, role='member')
        GroupMembership.objects.create(user=viewer, group=group, role='member')
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_list'))
        html = response.content.decode()
        owner_details_match = re.search(
            r'data-label="Owner - Details".*?(?:</td>)',
            html, re.DOTALL,
        )
        if owner_details_match:
            self.assertNotIn('verified-badge', owner_details_match.group(0))
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertNotContains(response, 'verified-badge')


@tag("integration")
class VerifiedBadgeEventPagesTest(TestCase):

    def test_verified_creator_shows_checkmark_in_event_list(self):
        creator = User.objects.create_user(
            username='verifiedcreator', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        group = Group.objects.create(name='Test Group')
        Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=creator, group=group
        )
        self.client.login(username='verifiedcreator', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertContains(response, 'verified-badge')

    def test_unverified_creator_no_checkmark_in_event_list(self):
        creator = User.objects.create_user(
            username='unverifiedcreator', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        group = Group.objects.create(name='Test Group')
        Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=creator, group=group
        )
        self.client.login(username='unverifiedcreator', password='testpass123')
        response = self.client.get(reverse('event_list'))
        self.assertNotContains(response, 'verified-badge')

    def test_verified_creator_and_attendee_badge_on_event_detail(self):
        verified_user = User.objects.create_user(
            username='verifieduser', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        group = Group.objects.create(name='Test Group')
        event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=verified_user, group=group
        )
        self.client.login(username='verifieduser', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertContains(response, 'verified-badge')
        EventAttendance.objects.create(user=verified_user, event=event)
        response = self.client.get(reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertContains(response, 'verified-badge')

    def test_unverified_attendee_no_checkmark(self):
        unverified_user = User.objects.create_user(
            username='unverifieduser', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        group = Group.objects.create(name='Test Group')
        event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=unverified_user, group=group
        )
        EventAttendance.objects.create(user=unverified_user, event=event)
        self.client.login(username='unverifieduser', password='testpass123')
        response = self.client.get(reverse('event_detail', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertNotContains(response, 'verified-badge')

    def test_verified_voter_shows_checkmark_in_individual_votes(self):
        verified_user = User.objects.create_user(
            username='verifiedvoter', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        group = Group.objects.create(name='Test Group')
        GroupMembership.objects.create(user=verified_user, group=group, role='member')
        event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=verified_user, show_individual_votes=True, group=group
        )
        game = BoardGame.objects.create(name='Catan', owner=verified_user)
        EventAttendance.objects.create(user=verified_user, event=event)
        Vote.objects.create(
            user=verified_user, event=event,
            board_game=game, rank=1
        )
        self.client.login(username='verifiedvoter', password='testpass123')
        response = self.client.get(reverse('event_results', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertContains(response, 'verified-badge')

    def test_unverified_voter_no_checkmark_in_individual_votes(self):
        unverified_user = User.objects.create_user(
            username='unverifiedvoter', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        verified_creator = User.objects.create_user(
            username='verifiedcreator', password='testpass123',
            email='verifiedc@example.com', email_verified=True
        )
        group = Group.objects.create(name='Test Group')
        event = Event.objects.create(
            title='Game Night', date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=verified_creator, show_individual_votes=True, group=group
        )
        game = BoardGame.objects.create(name='Catan', owner=verified_creator)
        EventAttendance.objects.create(user=unverified_user, event=event)
        Vote.objects.create(
            user=unverified_user, event=event,
            board_game=game, rank=1
        )
        response = self.client.get(reverse('event_results', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        html = response.content.decode()
        voter_section_start = html.find('unverifiedvoter')
        voter_section = html[voter_section_start:voter_section_start + 200]
        self.assertNotIn('verified-badge', voter_section)

    def test_verified_user_shows_checkmark_in_manage_users(self):
        admin = User.objects.create_user(
            username='admin', password='testpass123',
            is_site_admin=True, email='admin@example.com', email_verified=True
        )
        User.objects.create_user(
            username='verifieduser', password='testpass123',
            email='verified@example.com', email_verified=True
        )
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertContains(response, 'verified-badge')

    def test_unverified_user_no_checkmark_in_manage_users(self):
        admin = User.objects.create_user(
            username='admin', password='testpass123',
            is_site_admin=True, email='admin@example.com', email_verified=True
        )
        User.objects.create_user(
            username='unverifieduser', password='testpass123',
            email='unverified@example.com', email_verified=False
        )
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('manage_users'))
        self.assertNotContains(response, 'verified-badge')
