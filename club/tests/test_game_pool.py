from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from club.models import (
    BoardGame, Event, EventAttendance, EventGameOverride,
    EventPresence, Group, GroupMembership,
)
from club.game_pool import compute_game_pool

User = get_user_model()


def _make_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_member(user, group):
    GroupMembership.objects.create(user=user, group=group, role='member')


@tag("unit")
class EventGameOverrideModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='user', password='pass')
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.group = Group.objects.create(name='Override Group')
        _make_organizer(self.admin, self.group)
        self.event = Event.objects.create(
            title='Override Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.admin,
            group=self.group,
        )
        self.game = BoardGame.objects.create(name='Catan', owner=self.admin)

    def test_create_override(self):
        override = EventGameOverride.objects.create(
            event=self.event,
            board_game=self.game,
            is_available=True,
            modified_by=self.admin,
        )
        self.assertTrue(override.is_available)
        self.assertEqual(override.event, self.event)
        self.assertEqual(override.board_game, self.game)

    def test_unique_constraint(self):
        EventGameOverride.objects.create(
            event=self.event, board_game=self.game,
            is_available=True, modified_by=self.admin,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            EventGameOverride.objects.create(
                event=self.event, board_game=self.game,
                is_available=False, modified_by=self.admin,
            )


@tag("unit")
class GamePoolDeduplicationTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='pass')
        self.bob = User.objects.create_user(username='bob', password='pass')
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.group = Group.objects.create(name='Dedup Group')
        _make_organizer(self.admin, self.group)
        _make_member(self.alice, self.group)
        _make_member(self.bob, self.group)
        self.event = Event.objects.create(
            title='Dedup Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.admin,
            group=self.group,
        )

    def test_games_with_same_bgg_id_are_deduplicated(self):
        game1 = BoardGame.objects.create(
            name='Catan', owner=self.alice, bgg_id=13
        )
        game2 = BoardGame.objects.create(
            name='Catan', owner=self.bob, bgg_id=13
        )
        pool = compute_game_pool(self.event)
        catan_entries = [k for k, v in pool.items() if v['name'] == 'Catan']
        self.assertEqual(len(catan_entries), 1)
        entry = pool[catan_entries[0]]
        self.assertEqual(len(entry['copies']), 2)
        self.assertIn('alice', entry['owners'])
        self.assertIn('bob', entry['owners'])

    def test_games_without_bgg_id_are_not_deduplicated(self):
        game1 = BoardGame.objects.create(
            name='MyGame', owner=self.alice, bgg_id=None
        )
        game2 = BoardGame.objects.create(
            name='MyGame', owner=self.bob, bgg_id=None
        )
        pool = compute_game_pool(self.event)
        mygame_entries = [k for k, v in pool.items() if v['name'] == 'MyGame']
        self.assertEqual(len(mygame_entries), 2)

    def test_different_bgg_ids_are_not_deduplicated(self):
        game1 = BoardGame.objects.create(
            name='Space Base', owner=self.alice, bgg_id=100
        )
        game2 = BoardGame.objects.create(
            name='Space Base', owner=self.bob, bgg_id=200
        )
        pool = compute_game_pool(self.event)
        sb_entries = [k for k, v in pool.items() if v['name'] == 'Space Base']
        self.assertEqual(len(sb_entries), 2)

    def test_mixed_bgg_id_and_none_not_deduplicated(self):
        game1 = BoardGame.objects.create(
            name='Catan', owner=self.alice, bgg_id=13
        )
        game2 = BoardGame.objects.create(
            name='Catan', owner=self.bob, bgg_id=None
        )
        pool = compute_game_pool(self.event)
        catan_entries = [k for k, v in pool.items() if v['name'] == 'Catan']
        self.assertEqual(len(catan_entries), 2)

    def test_single_owner_shows_owner_name(self):
        BoardGame.objects.create(name='Wingspan', owner=self.alice, bgg_id=300)
        pool = compute_game_pool(self.event)
        ws_entries = [v for v in pool.values() if v['name'] == 'Wingspan']
        self.assertEqual(len(ws_entries), 1)
        self.assertEqual(ws_entries[0]['owners'], ['alice'])

    def test_complexity_is_simplest_among_duplicates(self):
        game1 = BoardGame.objects.create(
            name='Catan', owner=self.alice, bgg_id=13,
            complexity='heavy',
        )
        game2 = BoardGame.objects.create(
            name='Catan', owner=self.bob, bgg_id=13,
            complexity='light',
        )
        pool = compute_game_pool(self.event)
        catan_entries = [v for v in pool.values() if v['name'] == 'Catan']
        self.assertEqual(catan_entries[0]['complexity'], 'light')

    def test_group_owned_game_shows_group_library(self):
        BoardGame.objects.create(name='Group Game', group=self.group, bgg_id=500)
        pool = compute_game_pool(self.event)
        gg = [v for v in pool.values() if v['name'] == 'Group Game']
        self.assertEqual(len(gg), 1)
        self.assertIn('Group Library', gg[0]['owners'])


@tag("unit")
class GamePoolAvailabilityTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='pass')
        self.bob = User.objects.create_user(username='bob', password='pass')
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.group = Group.objects.create(name='Avail Group')
        _make_organizer(self.admin, self.group)
        _make_member(self.alice, self.group)
        _make_member(self.bob, self.group)
        self.event = Event.objects.create(
            title='Avail Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.admin,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.alice, event=self.event)
        EventAttendance.objects.create(user=self.bob, event=self.event)
        self.game_alice = BoardGame.objects.create(
            name='Catan', owner=self.alice, bgg_id=13
        )
        self.game_bob = BoardGame.objects.create(
            name='Wingspan', owner=self.bob, bgg_id=300
        )

    def test_game_unavailable_when_no_owners_present(self):
        pool = compute_game_pool(self.event)
        for entry in pool.values():
            self.assertFalse(entry['is_available'])

    def test_game_available_when_owner_present(self):
        EventPresence.objects.create(
            event=self.event, user=self.alice, marked_by=self.admin
        )
        pool = compute_game_pool(self.event)
        catan = [v for v in pool.values() if v['name'] == 'Catan'][0]
        self.assertTrue(catan['is_available'])

    def test_deduplicated_game_available_if_any_copy_owner_present(self):
        game2 = BoardGame.objects.create(
            name='Catan', owner=self.bob, bgg_id=13
        )
        EventPresence.objects.create(
            event=self.event, user=self.bob, marked_by=self.admin
        )
        pool = compute_game_pool(self.event)
        catan = [v for v in pool.values() if v['name'] == 'Catan'][0]
        self.assertTrue(catan['is_available'])

    def test_override_forces_available(self):
        EventGameOverride.objects.create(
            event=self.event, board_game=self.game_alice,
            is_available=True, modified_by=self.admin,
        )
        pool = compute_game_pool(self.event)
        catan = [v for v in pool.values() if v['name'] == 'Catan'][0]
        self.assertTrue(catan['is_available'])
        self.assertTrue(catan['overridden'])

    def test_override_forces_unavailable(self):
        EventPresence.objects.create(
            event=self.event, user=self.alice, marked_by=self.admin
        )
        EventGameOverride.objects.create(
            event=self.event, board_game=self.game_alice,
            is_available=False, modified_by=self.admin,
        )
        pool = compute_game_pool(self.event)
        catan = [v for v in pool.values() if v['name'] == 'Catan'][0]
        self.assertFalse(catan['is_available'])
        self.assertTrue(catan['overridden'])


@tag("integration")
class GamePoolViewTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        self.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        self.group = Group.objects.create(name='Pool View Group')
        _make_organizer(self.organizer, self.group)
        _make_member(self.member, self.group)
        self.event = Event.objects.create(
            title='Pool View Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.member, event=self.event)
        BoardGame.objects.create(
            name='Catan', owner=self.organizer, bgg_id=13
        )

    def test_organizer_can_view_game_pool(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_game_pool', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_member_cannot_view_game_pool(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('event_game_pool', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_cannot_view_game_pool(self):
        response = self.client.get(
            reverse('event_game_pool', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_game_pool_contains_game(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_game_pool', kwargs={'pk': self.event.pk})
        )
        self.assertContains(response, 'Catan')


@tag("integration")
class PoolOverrideViewTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        self.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        self.group = Group.objects.create(name='Override View Group')
        _make_organizer(self.organizer, self.group)
        _make_member(self.member, self.group)
        self.event = Event.objects.create(
            title='Override View Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.organizer,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.member, event=self.event)
        self.game = BoardGame.objects.create(
            name='Catan', owner=self.organizer, bgg_id=13
        )

    def test_organizer_can_create_override(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_pool_override', kwargs={'pk': self.event.pk}),
            {'board_game_id': self.game.pk, 'is_available': 'true'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            EventGameOverride.objects.filter(
                event=self.event, board_game=self.game, is_available=True
            ).exists()
        )

    def test_organizer_can_delete_override(self):
        EventGameOverride.objects.create(
            event=self.event, board_game=self.game,
            is_available=True, modified_by=self.organizer,
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('event_pool_override', kwargs={'pk': self.event.pk}),
            {'board_game_id': self.game.pk, 'is_available': 'false'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            EventGameOverride.objects.filter(
                event=self.event, board_game=self.game
            ).exists()
        )

    def test_member_cannot_override(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.post(
            reverse('event_pool_override', kwargs={'pk': self.event.pk}),
            {'board_game_id': self.game.pk, 'is_available': 'true'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)
