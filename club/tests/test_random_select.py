import json
from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from club.models import (
    BoardGame, Event, EventAttendance, EventPresence,
    Group, GroupMembership,
)

User = get_user_model()


def _make_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_member(user, group):
    GroupMembership.objects.create(user=user, group=group, role='member')


@tag("integration")
class RandomSelectTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        self.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        self.group = Group.objects.create(name='Random Group')
        _make_organizer(self.organizer, self.group)
        _make_member(self.member, self.group)
        self.event = Event.objects.create(
            title='Random Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.member, event=self.event)

    def test_random_select_from_pool(self):
        EventPresence.objects.create(
            event=self.event, user=self.member, marked_by=self.organizer
        )
        game1 = BoardGame.objects.create(name='Catan', owner=self.member, bgg_id=13)
        game2 = BoardGame.objects.create(name='Wingspan', owner=self.member, bgg_id=300)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(data['name'], ['Catan', 'Wingspan'])

    def test_random_select_deduplicated(self):
        EventPresence.objects.create(
            event=self.event, user=self.member, marked_by=self.organizer
        )
        BoardGame.objects.create(name='Catan', owner=self.organizer, bgg_id=13)
        BoardGame.objects.create(name='Catan', owner=self.member, bgg_id=13)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['name'], 'Catan')

    def test_random_select_empty_pool(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('error', data)

    def test_random_select_single_game(self):
        EventPresence.objects.create(
            event=self.event, user=self.member, marked_by=self.organizer
        )
        BoardGame.objects.create(name='Only Game', owner=self.member, bgg_id=13)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['name'], 'Only Game')

    def test_random_select_requires_organizer(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.post(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_random_select_requires_login(self):
        response = self.client.post(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_random_select_get_not_allowed(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 405)

    def test_random_select_includes_owners(self):
        EventPresence.objects.create(
            event=self.event, user=self.member, marked_by=self.organizer
        )
        BoardGame.objects.create(name='Catan', owner=self.organizer, bgg_id=13)
        BoardGame.objects.create(name='Catan', owner=self.member, bgg_id=13)
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_random_select', kwargs={'pk': self.event.pk})
        )
        data = response.json()
        self.assertIn('organizer', data['owners'])
        self.assertIn('member', data['owners'])
