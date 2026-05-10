import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, tag, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from club.models import (
    BoardGame,
    Event,
    EventAttendance,
    EventGameOverride,
    EventPresence,
    Group,
    GroupMembership,
)
from club.game_pool import compute_game_pool

User = get_user_model()


def _make_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_member(user, group):
    GroupMembership.objects.create(user=user, group=group, role='member')


@tag("integration")
class GameListViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='gameowner', password='testpass123'
        )
        cls.other_user = User.objects.create_user(
            username='otherplayer', password='testpass123'
        )
        cls.group = Group.objects.create(name='Test Group', created_by=cls.user)
        GroupMembership.objects.create(user=cls.user, group=cls.group, role='admin')
        GroupMembership.objects.create(user=cls.other_user, group=cls.group, role='member')
        cls.game1 = BoardGame.objects.create(
            name='Catan', owner=cls.user, min_players=3, max_players=4,
            image_url='https://cf.geekdo-images.com/pic123.png',
        )
        cls.game2 = BoardGame.objects.create(
            name='Chess', owner=cls.user
        )
        cls.game3 = BoardGame.objects.create(
            name='Risk', owner=cls.other_user, min_players=2, max_players=6
        )

    def test_game_list_displays_all_visible_games(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Catan')
        self.assertContains(response, 'Chess')
        self.assertContains(response, 'Risk')
        self.assertNotContains(response, 'bgg-thumbnail')

    def test_game_list_displays_complexity(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Complexity')

    def test_game_list_requires_login(self):
        response = self.client.get(reverse('game_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_my_tab_shows_only_current_user_games(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_list'), {'tab': 'my'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Catan')
        self.assertContains(response, 'Chess')
        self.assertNotContains(response, 'Risk')

    def test_my_tab_empty_state_shows_add_game_button(self):
        User.objects.create_user(username='nogames', password='testpass123')
        self.client.login(username='nogames', password='testpass123')
        response = self.client.get(reverse('game_list'), {'tab': 'my'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'You currently own no games.')
        self.assertContains(response, 'Click here to add a game')

    def test_game_list_has_filter_button(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'filter-modal-btn')

    def test_game_list_has_filter_modal(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'filter-modal-overlay')
        self.assertContains(response, 'filter-modal-close')
        self.assertContains(response, 'filter-apply-btn')

    def test_game_list_filter_button_shows_active_count(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_list'), {'owner': 'myself', 'players': '4'})
        self.assertContains(response, 'filter-modal-btn')
        self.assertEqual(response.context['active_filter_count'], 2)

    def test_game_list_no_active_filters_shows_zero_count(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertEqual(response.context['active_filter_count'], 0)


@tag("integration")
class GameListFilterTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='gameowner', password='testpass123'
        )
        cls.other_user = User.objects.create_user(
            username='otherplayer', password='testpass123'
        )
        cls.third_user = User.objects.create_user(
            username='thirdplayer', password='testpass123'
        )
        cls.group = Group.objects.create(name='Test Group', created_by=cls.user)
        GroupMembership.objects.create(user=cls.user, group=cls.group, role='admin')
        GroupMembership.objects.create(user=cls.other_user, group=cls.group, role='member')
        cls.game1 = BoardGame.objects.create(
            name='Catan', owner=cls.user, min_players=3, max_players=4
        )
        cls.game2 = BoardGame.objects.create(
            name='Risk', owner=cls.other_user, min_players=2, max_players=6
        )
        cls.game3 = BoardGame.objects.create(
            name='Pandemic', owner=cls.third_user
        )

    def test_filter_by_myself_shows_only_own_games(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_list'), {'owner': 'myself'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Catan')
        self.assertNotContains(response, 'Risk')
        self.assertNotContains(response, 'Pandemic')

    def test_filter_by_other_user_shows_their_games(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_list'), {'owner': 'otherplayer'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Risk')
        self.assertNotContains(response, 'Catan')
        self.assertNotContains(response, 'Pandemic')

    def test_filter_by_multiple_owners(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_list'), {'owner': ['gameowner', 'otherplayer']})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Catan')
        self.assertContains(response, 'Risk')
        self.assertNotContains(response, 'Pandemic')


@tag("integration")
class GameListPlayerFilterTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='gameowner', password='testpass123'
        )
        cls.game1 = BoardGame.objects.create(
            name='Catan', owner=cls.user, min_players=3, max_players=4
        )
        cls.game2 = BoardGame.objects.create(
            name='Risk', owner=cls.user, min_players=2, max_players=6
        )
        cls.game3 = BoardGame.objects.create(
            name='Chess', owner=cls.user
        )

    def test_filter_by_player_count_shows_matching_games(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_list'), {'players': '4'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Catan')
        self.assertContains(response, 'Risk')
        self.assertNotContains(response, 'Chess')

    def test_filter_excludes_games_with_null_players(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_list'), {'players': '3'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Catan')
        self.assertNotContains(response, 'Chess')

    def test_invalid_player_count_is_ignored(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_list'), {'players': 'abc'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Catan')
        self.assertContains(response, 'Risk')
        self.assertContains(response, 'Chess')


@tag("integration")
class GameListSortTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='alice', password='testpass123'
        )
        cls.other_user = User.objects.create_user(
            username='bob', password='testpass123'
        )
        cls.group = Group.objects.create(name='Test Group', created_by=cls.user)
        GroupMembership.objects.create(user=cls.user, group=cls.group, role='admin')
        GroupMembership.objects.create(user=cls.other_user, group=cls.group, role='member')
        cls.game1 = BoardGame.objects.create(
            name='Catan', owner=cls.user, min_players=3, max_players=4
        )
        cls.game2 = BoardGame.objects.create(
            name='Azul', owner=cls.other_user, min_players=2, max_players=4
        )
        cls.game3 = BoardGame.objects.create(
            name='Risk', owner=cls.user, min_players=2, max_players=6
        )

    def test_sort_by_name_ascending(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'), {'sort': 'name_asc'})
        self.assertEqual(response.status_code, 200)
        names = [g.name for g in response.context['games']]
        self.assertEqual(names, sorted(names))

    def test_sort_by_name_descending(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'), {'sort': 'name_desc'})
        self.assertEqual(response.status_code, 200)
        names = [g.name for g in response.context['games']]
        self.assertEqual(names, sorted(names, reverse=True))

    def test_sort_by_min_players_ascending(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'), {'sort': 'min_players_asc'})
        self.assertEqual(response.status_code, 200)
        games = list(response.context['games'])
        min_players = [g.min_players or 0 for g in games]
        self.assertEqual(min_players, sorted(min_players))

    def test_sort_by_min_players_descending(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'), {'sort': 'min_players_desc'})
        self.assertEqual(response.status_code, 200)
        games = list(response.context['games'])
        min_players = [g.min_players or 0 for g in games]
        self.assertEqual(min_players, sorted(min_players, reverse=True))

    def test_sort_by_max_players_ascending(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'), {'sort': 'max_players_asc'})
        self.assertEqual(response.status_code, 200)
        games = list(response.context['games'])
        max_players = [g.max_players or 0 for g in games]
        self.assertEqual(max_players, sorted(max_players))

    def test_sort_by_max_players_descending(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'), {'sort': 'max_players_desc'})
        self.assertEqual(response.status_code, 200)
        games = list(response.context['games'])
        max_players = [g.max_players or 0 for g in games]
        self.assertEqual(max_players, sorted(max_players, reverse=True))

    def test_sort_by_owner_ascending(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'), {'sort': 'owner_asc'})
        self.assertEqual(response.status_code, 200)
        games = list(response.context['games'])
        owners = [g.owner.username for g in games]
        self.assertEqual(owners, sorted(owners))

    def test_sort_by_owner_descending(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'), {'sort': 'owner_desc'})
        self.assertEqual(response.status_code, 200)
        games = list(response.context['games'])
        owners = [g.owner.username for g in games]
        self.assertEqual(owners, sorted(owners, reverse=True))


@tag("integration")
class GameCreateViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='creator', password='testpass123'
        )

    def test_create_page_requires_login(self):
        response = self.client.get(reverse('game_add'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_create_game_with_all_fields(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Pandemic',
            'description': 'Cooperative disease game',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Pandemic')
        self.assertEqual(game.owner, self.user)
        self.assertEqual(game.min_players, 2)
        self.assertEqual(game.max_players, 4)
        self.assertEqual(response.url, reverse('game_detail', kwargs={'pk': game.pk}))

    def test_create_game_with_required_fields_only(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Ticket to Ride',
            'min_players': 2,
            'max_players': 5,
            'complexity': 'light',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Ticket to Ride')
        self.assertEqual(game.owner, self.user)
        self.assertEqual(game.description, '')

    def test_create_game_without_name_fails(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoardGame.objects.exists())

    def test_create_game_with_bgg_id(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Catan',
            'description': 'Resource management',
            'min_players': 3,
            'max_players': 4,
            'bgg_id': 13,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Catan')
        self.assertEqual(game.bgg_id, 13)

    def test_create_game_without_bgg_id_still_works(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Chess',
            'min_players': 2,
            'max_players': 2,
            'complexity': 'unknown',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Chess')
        self.assertIsNone(game.bgg_id)

    def test_create_game_with_manual_complexity(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Pandemic',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Pandemic')
        self.assertEqual(game.complexity, 'medium')

    def test_create_game_without_complexity_fails(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'No Complexity Game',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoardGame.objects.filter(name='No Complexity Game').exists())

    def test_create_game_without_min_players_fails(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'No Min',
            'max_players': 4,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoardGame.objects.filter(name='No Min').exists())

    def test_create_game_without_max_players_or_unlimited_fails(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'No Max',
            'min_players': 2,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoardGame.objects.filter(name='No Max').exists())

    def test_create_game_with_min_players_zero_fails(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Zero Min',
            'min_players': 0,
            'max_players': 4,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoardGame.objects.filter(name='Zero Min').exists())

    def test_create_game_with_max_below_min_fails(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Inverted',
            'min_players': 4,
            'max_players': 2,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoardGame.objects.filter(name='Inverted').exists())

    def test_create_game_with_unlimited_max_players(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Unlimited Game',
            'min_players': 2,
            'max_players_unlimited': 'on',
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Unlimited Game')
        self.assertEqual(game.max_players, 0)

    def test_create_game_with_valid_min_max(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Valid Game',
            'min_players': 2,
            'max_players': 6,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Valid Game')
        self.assertEqual(game.min_players, 2)
        self.assertEqual(game.max_players, 6)


@tag("integration")
class GameDetailViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='owner', password='testpass123'
        )
        cls.game = BoardGame.objects.create(
            name='Catan', owner=cls.user,
            description='Resource management',
            min_players=3, max_players=4
        )

    def test_game_detail_displays_game_info(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Catan')
        self.assertContains(response, 'Resource management')
        self.assertContains(response, 'owner')

    def test_game_detail_requires_login(self):
        response = self.client.get(reverse('game_detail', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_game_detail_nonexistent_game_returns_not_available(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': 9999}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')

    def test_game_detail_shows_edit_link_for_owner(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': self.game.pk}))
        self.assertContains(response, reverse('game_edit', kwargs={'pk': self.game.pk}))

    def test_game_detail_hides_edit_link_for_non_owner(self):
        group = Group.objects.create(name='Edit Test Group')
        GroupMembership.objects.create(user=self.user, group=group, role='admin')
        other_user = User.objects.create_user(username='other', password='testpass123')
        GroupMembership.objects.create(user=other_user, group=group, role='member')
        self.client.login(username='other', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': self.game.pk}))
        self.assertNotContains(response, reverse('game_edit', kwargs={'pk': self.game.pk}))

    def test_game_detail_displays_complexity(self):
        self.game.complexity = 'medium'
        self.game.save()
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': self.game.pk}))
        self.assertContains(response, 'Medium')

    def test_superuser_sees_edit_and_delete_links_on_others_game(self):
        superuser = User.objects.create_superuser(
            username='admin', password='adminpass123'
        )
        self.client.login(username='admin', password='adminpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': self.game.pk}))
        self.assertContains(response, reverse('game_edit', kwargs={'pk': self.game.pk}))
        self.assertContains(response, reverse('game_delete', kwargs={'pk': self.game.pk}))


@tag("integration")
class GameUpdateViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='owner', password='testpass123'
        )
        cls.other_user = User.objects.create_user(
            username='other', password='testpass123'
        )
        cls.game = BoardGame.objects.create(
            name='Catan', owner=cls.owner
        )

    def test_edit_page_requires_login(self):
        response = self.client.get(reverse('game_edit', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_owner_can_access_edit_page(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('game_edit', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 200)

    def test_non_owner_cannot_access_edit_page(self):
        self.client.login(username='other', password='testpass123')
        response = self.client.get(reverse('game_edit', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')

    def test_owner_can_update_game(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.post(reverse('game_edit', kwargs={'pk': self.game.pk}), {
            'name': 'Catan: Seafarers',
            'description': 'Expanded edition',
            'min_players': 3,
            'max_players': 6,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        self.game.refresh_from_db()
        self.assertEqual(self.game.name, 'Catan: Seafarers')
        self.assertEqual(self.game.description, 'Expanded edition')
        self.assertEqual(self.game.max_players, 6)
        self.assertEqual(self.game.owner, self.owner)

    def test_non_owner_cannot_update_game(self):
        self.client.login(username='other', password='testpass123')
        response = self.client.post(reverse('game_edit', kwargs={'pk': self.game.pk}), {
            'name': 'Hacked Name',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')
        self.game.refresh_from_db()
        self.assertEqual(self.game.name, 'Catan')

    def test_owner_can_update_complexity(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.post(reverse('game_edit', kwargs={'pk': self.game.pk}), {
            'name': 'Catan',
            'min_players': 3,
            'max_players': 4,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        self.game.refresh_from_db()
        self.assertEqual(self.game.complexity, 'medium')

    def test_superuser_can_access_edit_page_for_others_game(self):
        superuser = User.objects.create_superuser(
            username='admin', password='adminpass123'
        )
        self.client.login(username='admin', password='adminpass123')
        response = self.client.get(reverse('game_edit', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_edit_others_game(self):
        superuser = User.objects.create_superuser(
            username='admin', password='adminpass123'
        )
        self.client.login(username='admin', password='adminpass123')
        response = self.client.post(reverse('game_edit', kwargs={'pk': self.game.pk}), {
            'name': 'Catan: Super Edition',
            'description': 'Admin edited',
            'min_players': 3,
            'max_players': 5,
            'complexity': 'heavy',
        })
        self.assertEqual(response.status_code, 302)
        self.game.refresh_from_db()
        self.assertEqual(self.game.name, 'Catan: Super Edition')
        self.assertEqual(self.game.description, 'Admin edited')

    def test_superuser_edit_of_own_game_skips_confirmation(self):
        superuser = User.objects.create_superuser(
            username='admin', password='adminpass123'
        )
        own_game = BoardGame.objects.create(name='Admin Game', owner=superuser)
        self.client.login(username='admin', password='adminpass123')
        response = self.client.get(reverse('game_edit', kwargs={'pk': own_game.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Edit Game')

    def test_edit_to_set_unlimited_max_players(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.post(reverse('game_edit', kwargs={'pk': self.game.pk}), {
            'name': 'Catan',
            'min_players': 3,
            'max_players_unlimited': 'on',
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        self.game.refresh_from_db()
        self.assertEqual(self.game.max_players, 0)

    def test_edit_to_remove_unlimited_and_set_value(self):
        self.game.max_players = 0
        self.game.save()
        self.client.login(username='owner', password='testpass123')
        response = self.client.post(reverse('game_edit', kwargs={'pk': self.game.pk}), {
            'name': 'Catan',
            'min_players': 3,
            'max_players': 6,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        self.game.refresh_from_db()
        self.assertEqual(self.game.max_players, 6)

    def test_edit_with_max_below_min_fails(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.post(reverse('game_edit', kwargs={'pk': self.game.pk}), {
            'name': 'Catan',
            'min_players': 5,
            'max_players': 2,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 200)
        self.game.refresh_from_db()
        self.assertEqual(self.game.name, 'Catan')


@tag("integration")
class GameDeleteViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='owner', password='testpass123'
        )
        cls.other_user = User.objects.create_user(
            username='other', password='testpass123'
        )
        cls.game = BoardGame.objects.create(
            name='Catan', owner=cls.owner
        )

    def test_delete_page_requires_login(self):
        response = self.client.get(reverse('game_delete', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_owner_can_access_delete_page(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('game_delete', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 200)

    def test_non_owner_cannot_access_delete_page(self):
        self.client.login(username='other', password='testpass123')
        response = self.client.get(reverse('game_delete', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')

    def test_owner_can_delete_game(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.post(reverse('game_delete', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BoardGame.objects.filter(pk=self.game.pk).exists())
        self.assertEqual(response.url, reverse('game_list'))

    def test_non_owner_cannot_delete_game(self):
        self.client.login(username='other', password='testpass123')
        response = self.client.post(reverse('game_delete', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')
        self.assertTrue(BoardGame.objects.filter(pk=self.game.pk).exists())

    def test_superuser_can_access_delete_page_for_others_game(self):
        User.objects.create_superuser(
            username='admin', password='adminpass123'
        )
        self.client.login(username='admin', password='adminpass123')
        response = self.client.get(reverse('game_delete', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_delete_others_game(self):
        User.objects.create_superuser(
            username='admin', password='adminpass123'
        )
        self.client.login(username='admin', password='adminpass123')
        response = self.client.post(reverse('game_delete', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BoardGame.objects.filter(pk=self.game.pk).exists())

    def test_superuser_delete_page_shows_owner_warning(self):
        User.objects.create_superuser(
            username='admin', password='adminpass123'
        )
        self.client.login(username='admin', password='adminpass123')
        response = self.client.get(reverse('game_delete', kwargs={'pk': self.game.pk}))
        self.assertContains(response, 'owner')


@tag("integration")
class GameListVisibilityTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='alice', password='testpass123'
        )
        cls.group_member = User.objects.create_user(
            username='bob', password='testpass123'
        )
        cls.outsider = User.objects.create_user(
            username='charlie', password='testpass123'
        )
        cls.group = Group.objects.create(name='Game Group', created_by=cls.user)
        GroupMembership.objects.create(user=cls.user, group=cls.group, role='admin')
        GroupMembership.objects.create(user=cls.group_member, group=cls.group, role='member')
        cls.own_game = BoardGame.objects.create(
            name='Catan', owner=cls.user, min_players=3, max_players=4,
            complexity='medium',
        )
        cls.member_game = BoardGame.objects.create(
            name='Risk', owner=cls.group_member, min_players=2, max_players=6,
            complexity='medium',
        )
        cls.group_game = BoardGame.objects.create(
            name='Pandemic', group=cls.group, min_players=2, max_players=4,
            complexity='light',
        )
        cls.outsider_game = BoardGame.objects.create(
            name='Chess', owner=cls.outsider, min_players=2, max_players=2,
            complexity='heavy',
        )

    def test_user_sees_own_games(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'Catan')

    def test_user_sees_group_member_games(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'Risk')

    def test_user_sees_group_owned_games(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'Pandemic')

    def test_user_does_not_see_outsider_games(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertNotContains(response, 'Chess')

    def test_user_not_in_group_sees_only_own_games(self):
        self.client.login(username='charlie', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'Chess')
        self.assertNotContains(response, 'Catan')
        self.assertNotContains(response, 'Risk')
        self.assertNotContains(response, 'Pandemic')

    def test_superuser_sees_all_games(self):
        superuser = User.objects.create_superuser(
            username='admin', password='adminpass123'
        )
        self.client.login(username='admin', password='adminpass123')
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'Catan')
        self.assertContains(response, 'Risk')
        self.assertContains(response, 'Pandemic')
        self.assertContains(response, 'Chess')

    def test_site_admin_sees_all_games(self):
        admin = User.objects.create_user(
            username='siteadmin', password='adminpass123', is_site_admin=True
        )
        self.client.login(username='siteadmin', password='adminpass123')
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'Catan')
        self.assertContains(response, 'Risk')
        self.assertContains(response, 'Pandemic')
        self.assertContains(response, 'Chess')


@tag("integration")
class GameListOwnedByColumnTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='alice', password='testpass123'
        )
        cls.other_user = User.objects.create_user(
            username='bob', password='testpass123'
        )
        cls.group = Group.objects.create(name='Game Club', created_by=cls.user)
        GroupMembership.objects.create(user=cls.user, group=cls.group, role='admin')
        GroupMembership.objects.create(user=cls.other_user, group=cls.group, role='member')
        cls.own_game = BoardGame.objects.create(
            name='Catan', owner=cls.user, min_players=3, max_players=4,
            complexity='medium',
        )
        cls.member_game = BoardGame.objects.create(
            name='Risk', owner=cls.other_user, min_players=2, max_players=6,
            complexity='medium',
        )
        cls.group_game = BoardGame.objects.create(
            name='Pandemic', group=cls.group, min_players=2, max_players=4,
            complexity='light',
        )

    def test_self_owned_game_shows_self(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        catan_row_start = content.find('Catan')
        self.assertGreater(catan_row_start, 0)
        self.assertIn('Self', content)

    def test_other_user_game_shows_others(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertIn('Others', response.content.decode())

    def test_group_owned_game_shows_others(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'))
        content = response.content.decode()
        pandemic_count = content.count('Pandemic')
        self.assertGreaterEqual(pandemic_count, 1)
        self.assertIn('Group Owned', content)

    def test_other_user_game_shows_owner_details(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'))
        content = response.content.decode()
        self.assertIn('Game Club', content)
        self.assertIn('bob', content)

    def test_group_owned_game_shows_group_owned_label(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'))
        content = response.content.decode()
        self.assertIn('Group Owned', content)

    def test_self_owned_game_has_no_details(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'))
        content = response.content.decode()
        self.assertNotContains(response, 'owner-detail-toggle')


@tag("integration")
class GameListOwnedByMultiGroupTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='alice', password='testpass123'
        )
        cls.other_user = User.objects.create_user(
            username='bob', password='testpass123'
        )
        cls.group_a = Group.objects.create(name='Alpha Group', created_by=cls.user)
        cls.group_b = Group.objects.create(name='Beta Group', created_by=cls.user)
        GroupMembership.objects.create(user=cls.user, group=cls.group_a, role='admin')
        GroupMembership.objects.create(user=cls.user, group=cls.group_b, role='organizer')
        GroupMembership.objects.create(user=cls.other_user, group=cls.group_a, role='member')
        GroupMembership.objects.create(user=cls.other_user, group=cls.group_b, role='member')
        cls.shared_game = BoardGame.objects.create(
            name='Risk', owner=cls.other_user, min_players=2, max_players=6,
            complexity='medium',
        )

    def test_game_visible_through_multiple_groups_shows_more_button(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'))
        content = response.content.decode()
        self.assertIn('More (+1)', content)

    def test_deterministic_order_shows_admin_group_first(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'))
        content = response.content.decode()
        alpha_pos = content.find('Alpha Group')
        beta_pos = content.find('Beta Group')
        self.assertGreater(alpha_pos, 0)
        self.assertGreater(beta_pos, 0)
        self.assertLess(alpha_pos, beta_pos)


@tag("integration")
class GameListGroupFilterTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='alice', password='testpass123'
        )
        cls.other_user = User.objects.create_user(
            username='bob', password='testpass123'
        )
        cls.group = Group.objects.create(name='Game Club', created_by=cls.user)
        GroupMembership.objects.create(user=cls.user, group=cls.group, role='admin')
        GroupMembership.objects.create(user=cls.other_user, group=cls.group, role='member')
        cls.own_game = BoardGame.objects.create(
            name='Catan', owner=cls.user, min_players=3, max_players=4,
            complexity='medium',
        )
        cls.member_game = BoardGame.objects.create(
            name='Risk', owner=cls.other_user, min_players=2, max_players=6,
            complexity='medium',
        )
        cls.group_game = BoardGame.objects.create(
            name='Pandemic', group=cls.group, min_players=2, max_players=4,
            complexity='light',
        )

    def test_filter_self_owned_shows_only_own_games(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'), {'group': 'self'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Catan')
        self.assertNotContains(response, 'Risk')
        self.assertNotContains(response, 'Pandemic')

    def test_filter_by_group_shows_group_games(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'), {'group': self.group.slug})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Risk')
        self.assertContains(response, 'Pandemic')

    def test_filter_by_group_excludes_non_group_games(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'), {'group': self.group.slug})
        self.assertNotContains(response, 'Catan')

    def test_filter_modal_has_group_select(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'filter-group')
        self.assertContains(response, 'Self-owned')

    def test_group_filter_counts_toward_active_filters(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'), {'group': 'self'})
        self.assertEqual(response.context['active_filter_count'], 1)

    def test_owner_filter_dropdown_scoped_to_visible_users(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'))
        owner_usernames = list(response.context['all_owners'])
        self.assertIn('bob', owner_usernames)
        self.assertNotIn('alice', owner_usernames)


@tag("integration")
class GameListOwnerFilterScopingTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='alice', password='testpass123'
        )
        cls.group_member = User.objects.create_user(
            username='bob', password='testpass123'
        )
        cls.outsider = User.objects.create_user(
            username='charlie', password='testpass123'
        )
        cls.group = Group.objects.create(name='Game Group', created_by=cls.user)
        GroupMembership.objects.create(user=cls.user, group=cls.group, role='admin')
        GroupMembership.objects.create(user=cls.group_member, group=cls.group, role='member')
        BoardGame.objects.create(
            name='Catan', owner=cls.user, min_players=3, max_players=4,
            complexity='medium',
        )
        BoardGame.objects.create(
            name='Risk', owner=cls.group_member, min_players=2, max_players=6,
            complexity='medium',
        )
        BoardGame.objects.create(
            name='Chess', owner=cls.outsider, min_players=2, max_players=2,
            complexity='heavy',
        )

    def test_owner_dropdown_excludes_outsider(self):
        self.client.login(username='alice', password='testpass123')
        response = self.client.get(reverse('game_list'))
        owner_usernames = list(response.context['all_owners'])
        self.assertNotIn('charlie', owner_usernames)


@tag("integration")
class GameDetailVisibilityTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='gameowner', password='testpass123'
        )
        cls.group_member = User.objects.create_user(
            username='groupmember', password='testpass123'
        )
        cls.outsider = User.objects.create_user(
            username='outsider', password='testpass123'
        )
        cls.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123'
        )
        cls.site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True
        )
        cls.group = Group.objects.create(name='Visibility Group', created_by=cls.owner)
        GroupMembership.objects.create(user=cls.owner, group=cls.group, role='admin')
        GroupMembership.objects.create(
            user=cls.group_member, group=cls.group, role='member',
        )
        cls.owned_game = BoardGame.objects.create(
            name='Owned Game', owner=cls.owner,
        )
        cls.group_game = BoardGame.objects.create(
            name='Group Game', group=cls.group,
        )
        cls.other_member_game = BoardGame.objects.create(
            name='Member Game', owner=cls.group_member,
        )

    def test_owner_can_view_own_game(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.owned_game.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_group_member_can_view_game_owned_by_another_member(self):
        self.client.login(username='groupmember', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.owned_game.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_group_member_can_view_group_assigned_game(self):
        self.client.login(username='groupmember', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.group_game.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_owner_can_view_group_assigned_game(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.group_game.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_outsider_cannot_view_game_with_no_shared_group(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.owned_game.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')

    def test_outsider_cannot_view_group_assigned_game(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.group_game.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')

    def test_outsider_cannot_view_game_owned_by_group_member(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.other_member_game.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')

    def test_superuser_can_view_any_game(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.owned_game.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_site_admin_can_view_any_game(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.owned_game.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_view_group_game(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.group_game.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_site_admin_can_view_group_game(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.group_game.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_edit_nonexistent_game_returns_not_available(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(reverse('game_edit', kwargs={'pk': 9999}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')

    def test_edit_nonexistent_game_post_returns_not_available(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.post(reverse('game_edit', kwargs={'pk': 9999}), {
            'name': 'Hacked',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')

    def test_edit_non_viewable_game_returns_not_available(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(
            reverse('game_edit', kwargs={'pk': self.owned_game.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')

    def test_edit_non_viewable_game_post_returns_not_available(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.owned_game.pk}),
            {'name': 'Hacked'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')
        self.owned_game.refresh_from_db()
        self.assertEqual(self.owned_game.name, 'Owned Game')

    def test_edit_viewable_but_non_ownable_game_returns_403(self):
        self.client.login(username='groupmember', password='testpass123')
        response = self.client.get(
            reverse('game_edit', kwargs={'pk': self.owned_game.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_nonexistent_game_returns_not_available(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(reverse('game_delete', kwargs={'pk': 9999}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')

    def test_delete_nonexistent_game_post_returns_not_available(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.post(reverse('game_delete', kwargs={'pk': 9999}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')

    def test_delete_non_viewable_game_returns_not_available(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(
            reverse('game_delete', kwargs={'pk': self.owned_game.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')

    def test_delete_non_viewable_game_post_returns_not_available(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.post(
            reverse('game_delete', kwargs={'pk': self.owned_game.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')
        self.assertTrue(BoardGame.objects.filter(pk=self.owned_game.pk).exists())

    def test_delete_viewable_but_non_ownable_game_returns_403(self):
        self.client.login(username='groupmember', password='testpass123')
        response = self.client.get(
            reverse('game_delete', kwargs={'pk': self.owned_game.pk})
        )
        self.assertEqual(response.status_code, 403)


@tag("integration")
class GameListNonGroupEventVisibilityTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        from django.utils import timezone as tz

        cls.alice = User.objects.create_user(username='alice_lst', password='testpass123')
        cls.bob = User.objects.create_user(username='bob_lst', password='testpass123')
        cls.charlie = User.objects.create_user(username='charlie_lst', password='testpass123')
        cls.dave = User.objects.create_user(username='dave_lst', password='testpass123')

        cls.alice_game = BoardGame.objects.create(name='Alice List Game', owner=cls.alice)
        cls.bob_game = BoardGame.objects.create(name='Bob List Game', owner=cls.bob)
        cls.dave_game = BoardGame.objects.create(name='Dave List Game', owner=cls.dave)

        cls.future_event = Event.objects.create(
            title='Future List Event',
            date=tz.now() + tz.timedelta(days=7),
            voting_deadline=tz.now() + tz.timedelta(days=7),
            created_by=cls.charlie,
        )
        EventAttendance.objects.create(user=cls.alice, event=cls.future_event)
        EventAttendance.objects.create(user=cls.bob, event=cls.future_event)

        cls.other_event = Event.objects.create(
            title='Other List Event',
            date=tz.now() + tz.timedelta(days=7),
            voting_deadline=tz.now() + tz.timedelta(days=7),
            created_by=cls.dave,
        )

    def test_co_attendee_game_appears_in_game_list(self):
        self.client.login(username='alice_lst', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'Bob List Game')

    def test_organizer_game_appears_in_attendee_game_list(self):
        BoardGame.objects.create(name='Charlie List Game', owner=self.charlie)
        self.client.login(username='alice_lst', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'Charlie List Game')

    def test_non_co_attendee_game_not_in_game_list(self):
        self.client.login(username='alice_lst', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertNotContains(response, 'Dave List Game')


@tag("integration")
class GameDetailNonGroupEventVisibilityTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        from django.utils import timezone as tz

        cls.alice = User.objects.create_user(username='alice_evt', password='testpass123')
        cls.bob = User.objects.create_user(username='bob_evt', password='testpass123')
        cls.charlie = User.objects.create_user(username='charlie_evt', password='testpass123')
        cls.dave = User.objects.create_user(username='dave_evt', password='testpass123')

        cls.alice_game = BoardGame.objects.create(name='Alice Event Game', owner=cls.alice)
        cls.bob_game = BoardGame.objects.create(name='Bob Event Game', owner=cls.bob)
        cls.charlie_game = BoardGame.objects.create(name='Charlie Event Game', owner=cls.charlie)
        cls.dave_game = BoardGame.objects.create(name='Dave Event Game', owner=cls.dave)

        cls.future_event = Event.objects.create(
            title='Future Event',
            date=tz.now() + tz.timedelta(days=7),
            voting_deadline=tz.now() + tz.timedelta(days=7),
            created_by=cls.charlie,
        )
        EventAttendance.objects.create(user=cls.alice, event=cls.future_event)
        EventAttendance.objects.create(user=cls.bob, event=cls.future_event)

        cls.past_event = Event.objects.create(
            title='Past Event',
            date=tz.now() - tz.timedelta(days=1),
            voting_deadline=tz.now() - tz.timedelta(days=1),
            created_by=cls.charlie,
        )
        EventAttendance.objects.create(user=cls.alice, event=cls.past_event)
        EventAttendance.objects.create(user=cls.dave, event=cls.past_event)

        cls.inactive_event = Event.objects.create(
            title='Inactive Event',
            date=tz.now() + tz.timedelta(days=7),
            voting_deadline=tz.now() + tz.timedelta(days=7),
            created_by=cls.charlie,
            is_active=False,
        )
        EventAttendance.objects.create(user=cls.alice, event=cls.inactive_event)
        EventAttendance.objects.create(user=cls.dave, event=cls.inactive_event)

        cls.other_event = Event.objects.create(
            title='Other Event',
            date=tz.now() + tz.timedelta(days=7),
            voting_deadline=tz.now() + tz.timedelta(days=7),
            created_by=cls.dave,
        )
        EventAttendance.objects.create(user=cls.charlie, event=cls.other_event)

        cls.test_group = Group.objects.create(
            name='Event Visibility Group', created_by=cls.alice,
        )
        GroupMembership.objects.create(user=cls.alice, group=cls.test_group, role='admin')
        cls.group_event = Event.objects.create(
            title='Group Event',
            date=tz.now() + tz.timedelta(days=7),
            voting_deadline=tz.now() + tz.timedelta(days=7),
            created_by=cls.alice,
            group=cls.test_group,
        )
        EventAttendance.objects.create(user=cls.dave, event=cls.group_event)

    def test_co_attendees_can_view_each_others_games(self):
        self.client.login(username='alice_evt', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.bob_game.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_organizer_can_view_attendee_game(self):
        self.client.login(username='charlie_evt', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.alice_game.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_attendee_can_view_organizer_game(self):
        self.client.login(username='alice_evt', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.charlie_game.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_different_event_users_cannot_view_each_others_games(self):
        self.client.login(username='dave_evt', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.alice_game.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')

    def test_past_event_co_attendance_does_not_grant_visibility(self):
        self.client.login(username='dave_evt', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.alice_game.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')

    def test_inactive_event_co_attendance_does_not_grant_visibility(self):
        self.client.login(username='dave_evt', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.alice_game.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')

    def test_group_event_co_attendance_does_not_grant_visibility(self):
        self.client.login(username='dave_evt', password='testpass123')
        response = self.client.get(
            reverse('game_detail', kwargs={'pk': self.alice_game.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not available')


@tag("integration")
class BggSearchViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='searcher', password='testpass123'
        )

    def test_bgg_search_requires_login(self):
        response = self.client.get(reverse('bgg_search'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    @patch('club.views.search_bgg')
    def test_bgg_search_returns_json(self, mock_search):
        mock_search.return_value = [
            {'id': 13, 'name': 'Catan'},
            {'id': 278, 'name': 'Catan Card Game'},
        ]
        self.client.login(username='searcher', password='testpass123')
        response = self.client.get(reverse('bgg_search'), {'q': 'Catan'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = json.loads(response.content)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['name'], 'Catan')

    @patch('club.views.search_bgg')
    def test_bgg_search_passes_query_to_search_bgg(self, mock_search):
        mock_search.return_value = []
        self.client.login(username='searcher', password='testpass123')
        self.client.get(reverse('bgg_search'), {'q': 'Pandemic'})
        mock_search.assert_called_once_with('Pandemic')

    @patch('club.views.search_bgg')
    def test_bgg_search_returns_empty_on_api_error(self, mock_search):
        mock_search.return_value = []
        self.client.login(username='searcher', password='testpass123')
        response = self.client.get(reverse('bgg_search'), {'q': 'xyz'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data, [])

    def test_bgg_search_without_query_returns_empty(self):
        self.client.login(username='searcher', password='testpass123')
        response = self.client.get(reverse('bgg_search'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data, [])


@tag("integration")
class BggImportViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='importer', password='testpass123'
        )

    def test_bgg_import_requires_login(self):
        response = self.client.get(reverse('bgg_import', kwargs={'bgg_id': 13}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    @patch('club.views.fetch_bgg_game')
    def test_bgg_import_returns_json(self, mock_fetch):
        mock_fetch.return_value = {
            'bgg_id': 13,
            'name': 'Catan',
            'description': 'Resource management',
            'min_players': 3,
            'max_players': 4,
            'bgg_link': 'https://boardgamegeek.com/boardgame/13/catan',
            'image_url': 'https://cf.geekdo-images.com/pic123.png',
        }
        self.client.login(username='importer', password='testpass123')
        response = self.client.get(reverse('bgg_import', kwargs={'bgg_id': 13}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = json.loads(response.content)
        self.assertEqual(data['name'], 'Catan')
        self.assertEqual(data['min_players'], 3)

    @patch('club.views.fetch_bgg_weight')
    @patch('club.views.fetch_bgg_game')
    def test_bgg_import_returns_weight_and_complexity(self, mock_fetch, mock_weight):
        mock_fetch.return_value = {
            'bgg_id': 13,
            'name': 'Catan',
            'description': 'Resource management',
            'min_players': 3,
            'max_players': 4,
            'bgg_link': 'https://boardgamegeek.com/boardgame/13/catan',
            'image_url': 'https://cf.geekdo-images.com/pic123.png',
        }
        mock_weight.return_value = Decimal('2.28')
        self.client.login(username='importer', password='testpass123')
        response = self.client.get(reverse('bgg_import', kwargs={'bgg_id': 13}))
        data = json.loads(response.content)
        self.assertEqual(data['bgg_weight'], '2.28')
        self.assertEqual(data['suggested_complexity'], 'medium')

    @patch('club.views.fetch_bgg_game')
    def test_bgg_import_returns_error_on_failure(self, mock_fetch):
        mock_fetch.return_value = None
        self.client.login(username='importer', password='testpass123')
        response = self.client.get(reverse('bgg_import', kwargs={'bgg_id': 999999}))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('error', data)


@tag("integration")
class GameAddWithBggTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='creator', password='testpass123'
        )

    @patch('club.views.fetch_bgg_game')
    def test_create_game_with_bgg_id_fetches_and_saves_data(self, mock_fetch):
        mock_fetch.return_value = {
            'bgg_id': 13,
            'name': 'Catan',
            'description': 'Resource management',
            'min_players': 3,
            'max_players': 4,
            'bgg_link': 'https://boardgamegeek.com/boardgame/13/catan',
            'image_url': 'https://cf.geekdo-images.com/pic123.png',
        }
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Catan',
            'description': 'Resource management',
            'min_players': 3,
            'max_players': 4,
            'bgg_id': 13,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Catan')
        self.assertEqual(game.bgg_id, 13)
        self.assertEqual(game.bgg_link, 'https://boardgamegeek.com/boardgame/13/catan')
        self.assertEqual(game.image_url, 'https://cf.geekdo-images.com/pic123.png')
        self.assertIsNotNone(game.bgg_last_synced)
        mock_fetch.assert_called_once_with(13)

    @patch('club.views.fetch_bgg_game')
    def test_create_game_without_bgg_id_does_not_fetch(self, mock_fetch):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Chess',
            'min_players': 2,
            'max_players': 2,
            'complexity': 'unknown',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Chess')
        self.assertIsNone(game.bgg_id)
        self.assertEqual(game.bgg_link, '')
        mock_fetch.assert_not_called()

    @patch('club.views.fetch_bgg_game')
    def test_create_game_with_bgg_id_handles_fetch_failure(self, mock_fetch):
        mock_fetch.return_value = None
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Catan',
            'bgg_id': 13,
            'min_players': 3,
            'max_players': 4,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Catan')
        self.assertEqual(game.bgg_id, 13)
        self.assertEqual(game.bgg_link, '')

    @patch('club.views.fetch_bgg_weight')
    @patch('club.views.fetch_bgg_game')
    def test_create_game_with_bgg_id_auto_fills_complexity(self, mock_fetch, mock_weight):
        mock_fetch.return_value = {
            'bgg_id': 13,
            'name': 'Catan',
            'description': 'Resource management',
            'min_players': 3,
            'max_players': 4,
            'bgg_link': 'https://boardgamegeek.com/boardgame/13/catan',
            'image_url': 'https://cf.geekdo-images.com/pic123.png',
        }
        mock_weight.return_value = Decimal('2.28')
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Catan',
            'description': 'Resource management',
            'min_players': 3,
            'max_players': 4,
            'bgg_id': 13,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Catan')
        self.assertEqual(game.bgg_weight, Decimal('2.28'))
        self.assertEqual(game.complexity, 'medium')

    @patch('club.views.fetch_bgg_weight')
    @patch('club.views.fetch_bgg_game')
    def test_create_game_with_bgg_weight_failure_still_saves(self, mock_fetch, mock_weight):
        mock_fetch.return_value = {
            'bgg_id': 13,
            'name': 'Catan',
            'description': 'Resource management',
            'min_players': 3,
            'max_players': 4,
            'bgg_link': 'https://boardgamegeek.com/boardgame/13/catan',
            'image_url': 'https://cf.geekdo-images.com/pic123.png',
        }
        mock_weight.return_value = None
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Catan',
            'bgg_id': 13,
            'min_players': 3,
            'max_players': 4,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Catan')
        self.assertIsNone(game.bgg_weight)
        self.assertEqual(game.complexity, 'medium')


@tag("integration")
class GameEditWithBggTest(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', password='testpass123'
        )
        self.game = BoardGame.objects.create(
            name='Catan', owner=self.owner
        )

    @patch('club.views.fetch_bgg_game')
    def test_edit_game_with_bgg_id_updates_bgg_data(self, mock_fetch):
        mock_fetch.return_value = {
            'bgg_id': 13,
            'name': 'Catan',
            'description': 'Resource management',
            'min_players': 3,
            'max_players': 4,
            'bgg_link': 'https://boardgamegeek.com/boardgame/13/catan',
            'image_url': 'https://cf.geekdo-images.com/pic123.png',
        }
        self.client.login(username='owner', password='testpass123')
        response = self.client.post(reverse('game_edit', kwargs={'pk': self.game.pk}), {
            'name': 'Catan',
            'description': 'Resource management',
            'min_players': 3,
            'max_players': 4,
            'bgg_id': 13,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        self.game.refresh_from_db()
        self.assertEqual(self.game.bgg_id, 13)
        self.assertEqual(self.game.bgg_link, 'https://boardgamegeek.com/boardgame/13/catan')
        self.assertEqual(self.game.image_url, 'https://cf.geekdo-images.com/pic123.png')


@tag("integration")
class GameDetailWithBggTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='viewer', password='testpass123'
        )

    def test_game_detail_shows_bgg_link(self):
        game = BoardGame.objects.create(
            name='Catan', owner=self.user,
            bgg_id=13,
            bgg_link='https://boardgamegeek.com/boardgame/13/catan',
        )
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(response, 'Link to BoardGameGeek site')
        self.assertContains(response, 'https://boardgamegeek.com/boardgame/13/catan')

    def test_game_detail_shows_bgg_image(self):
        game = BoardGame.objects.create(
            name='Catan', owner=self.user,
            bgg_id=13,
            image_url='https://cf.geekdo-images.com/pic123.png',
        )
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(response, 'pic123.png')

    def test_game_detail_without_bgg_data_hides_bgg_elements(self):
        game = BoardGame.objects.create(
            name='Chess', owner=self.user,
        )
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertNotContains(response, 'Link to BoardGameGeek site')
        self.assertNotContains(response, 'boardgamegeek.com')

    def test_game_detail_shows_bgg_weight(self):
        game = BoardGame.objects.create(
            name='Catan', owner=self.user,
            bgg_id=13,
            bgg_weight=Decimal('2.28'),
            complexity='medium',
        )
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(response, '2.28')

    def test_game_detail_shows_bgg_link_as_link_text(self):
        game = BoardGame.objects.create(
            name='Catan', owner=self.user,
            bgg_id=13,
            bgg_link='https://boardgamegeek.com/boardgame/13/catan',
        )
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(response, 'Link to BoardGameGeek site')

    def test_game_detail_bgg_link_opens_in_new_tab(self):
        game = BoardGame.objects.create(
            name='Catan', owner=self.user,
            bgg_id=13,
            bgg_link='https://boardgamegeek.com/boardgame/13/catan',
        )
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(response, 'target="_blank"')


@tag("integration")
class GameAddWithBggLinkInputTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='creator', password='testpass123'
        )

    @patch('club.views.fetch_bgg_game')
    def test_create_with_bgg_link_url(self, mock_fetch):
        mock_fetch.return_value = None
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Catan',
            'description': 'Resource management',
            'min_players': 3,
            'max_players': 4,
            'complexity': 'medium',
            'bgg_link_input': 'https://boardgamegeek.com/boardgame/13/catan',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Catan')
        self.assertEqual(game.bgg_id, 13)
        self.assertEqual(game.bgg_link, 'https://boardgamegeek.com/boardgame/13/catan')

    @patch('club.views.fetch_bgg_game')
    def test_create_with_raw_bgg_id(self, mock_fetch):
        mock_fetch.return_value = None
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Catan',
            'min_players': 3,
            'max_players': 4,
            'complexity': 'medium',
            'bgg_link_input': '13',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Catan')
        self.assertEqual(game.bgg_id, 13)
        self.assertEqual(game.bgg_link, 'https://boardgamegeek.com/boardgame/13/')

    def test_create_without_bgg_link_input(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Chess',
            'min_players': 2,
            'max_players': 2,
            'complexity': 'light',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Chess')
        self.assertIsNone(game.bgg_id)
        self.assertEqual(game.bgg_link, '')

    def test_create_with_invalid_bgg_link_input(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Chess',
            'min_players': 2,
            'max_players': 2,
            'complexity': 'light',
            'bgg_link_input': 'not a valid url or id',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoardGame.objects.filter(name='Chess').exists())

    @patch('club.views.fetch_bgg_game')
    def test_create_with_bgg_link_url_fetches_bgg_data(self, mock_fetch):
        mock_fetch.return_value = {
            'bgg_id': 13,
            'name': 'Catan',
            'description': 'Resource management',
            'min_players': 3,
            'max_players': 4,
            'bgg_link': 'https://boardgamegeek.com/boardgame/13/catan',
            'image_url': 'https://cf.geekdo-images.com/pic123.png',
        }
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Catan',
            'min_players': 3,
            'max_players': 4,
            'complexity': 'medium',
            'bgg_link_input': 'https://boardgamegeek.com/boardgame/13/catan',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Catan')
        self.assertEqual(game.image_url, 'https://cf.geekdo-images.com/pic123.png')
        mock_fetch.assert_called_once_with(13)

    def test_create_with_bgg_search_overrides_link_input(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Catan',
            'min_players': 3,
            'max_players': 4,
            'complexity': 'medium',
            'bgg_id': 278,
            'bgg_link_input': 'https://boardgamegeek.com/boardgame/13/catan',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Catan')
        self.assertEqual(game.bgg_id, 278)

    def test_add_form_shows_bgg_link_input_field(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertContains(response, 'bgg_link_input')

    def test_add_form_shows_soft_warning_without_bgg(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertContains(response, 'bgg-link-warning')

    def test_add_form_bgg_warning_uses_visibility_not_display(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertContains(response, "id=\"bgg-link-warning\"")
        content = response.content.decode()
        warning_start = content.index("id=\"bgg-link-warning\"")
        warning_tag = content[warning_start:warning_start + 300]
        self.assertIn("visibility: hidden", warning_tag)

    def test_add_form_bgg_input_cell_stacks_vertically(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.get(reverse('game_add'))
        content = response.content.decode()
        bgg_label_pos = content.index("for=\"id_bgg_link_input\"")
        input_cell_pos = content.index("input-cell", bgg_label_pos)
        self.assertIn("flex-direction: column", content[input_cell_pos:input_cell_pos + 100])


@tag("integration")
class GameEditWithBggLinkInputTest(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', password='testpass123'
        )
        self.game = BoardGame.objects.create(
            name='Catan', owner=self.owner,
            min_players=3, max_players=4,
            complexity='medium',
        )

    def test_edit_form_shows_existing_bgg_link(self):
        self.game.bgg_id = 13
        self.game.bgg_link = 'https://boardgamegeek.com/boardgame/13/catan'
        self.game.save()
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('game_edit', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'https://boardgamegeek.com/boardgame/13/catan')

    def test_edit_adds_bgg_link_via_url(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.post(reverse('game_edit', kwargs={'pk': self.game.pk}), {
            'name': 'Catan',
            'min_players': 3,
            'max_players': 4,
            'complexity': 'medium',
            'bgg_link_input': 'https://boardgamegeek.com/boardgame/13/catan',
        })
        self.assertEqual(response.status_code, 302)
        self.game.refresh_from_db()
        self.assertEqual(self.game.bgg_id, 13)
        self.assertEqual(self.game.bgg_link, 'https://boardgamegeek.com/boardgame/13/catan')

    def test_edit_removes_bgg_link_by_clearing_input(self):
        self.game.bgg_id = 13
        self.game.bgg_link = 'https://boardgamegeek.com/boardgame/13/catan'
        self.game.save()
        self.client.login(username='owner', password='testpass123')
        response = self.client.post(reverse('game_edit', kwargs={'pk': self.game.pk}), {
            'name': 'Catan',
            'min_players': 3,
            'max_players': 4,
            'complexity': 'medium',
            'bgg_link_input': '',
        })
        self.assertEqual(response.status_code, 302)
        self.game.refresh_from_db()
        self.assertIsNone(self.game.bgg_id)
        self.assertEqual(self.game.bgg_link, '')


@tag("integration")
class GameAddOwnershipDropdownTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='gameowner', password='testpass123'
        )
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.group_admin = User.objects.create_user(
            username='groupadmin', password='testpass123'
        )
        cls.group = Group.objects.create(name='Test Group')
        cls.group2 = Group.objects.create(name='Other Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )
        GroupMembership.objects.create(
            user=cls.member, group=cls.group, role='member'
        )
        GroupMembership.objects.create(
            user=cls.group_admin, group=cls.group, role='admin'
        )
        GroupMembership.objects.create(
            user=cls.group_admin, group=cls.group2, role='admin'
        )

    def test_add_page_has_ownership_dropdown(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ownership_target')

    def test_add_page_shows_self_option(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertContains(response, 'Self')

    def test_add_page_shows_groups_for_organizer(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertContains(response, 'Test Group')

    def test_add_page_no_groups_for_user_without_organizer_role(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertNotContains(response, 'data-group-slug')

    def test_add_page_shows_multiple_groups_for_multi_group_admin(self):
        self.client.login(username='groupadmin', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertContains(response, 'Test Group')
        self.assertContains(response, 'Other Group')

    def test_default_ownership_is_self(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertEqual(response.context['default_ownership'], 'self')

    def test_default_ownership_from_group_param(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('game_add'), {'group': self.group.slug}
        )
        self.assertEqual(
            response.context['default_ownership'],
            f'group:{self.group.slug}'
        )

    def test_default_ownership_from_event_param_with_group_event(self):
        self.client.login(username='organizer', password='testpass123')
        event = Event.objects.create(
            title='Test Event',
            date='2026-06-01T18:00:00Z',
            created_by=self.organizer,
            group=self.group,
            voting_deadline='2026-06-01T18:00:00Z',
        )
        response = self.client.get(
            reverse('game_add'), {'event': event.pk}
        )
        self.assertEqual(
            response.context['default_ownership'],
            f'group:{self.group.slug}'
        )

    def test_default_ownership_from_event_param_with_private_event(self):
        self.client.login(username='gameowner', password='testpass123')
        event = Event.objects.create(
            title='Private Event',
            date='2026-06-01T18:00:00Z',
            created_by=self.user,
            voting_deadline='2026-06-01T18:00:00Z',
        )
        response = self.client.get(
            reverse('game_add'), {'event': event.pk}
        )
        self.assertEqual(response.context['default_ownership'], 'self')

    def test_create_game_with_ownership_self(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'My Game',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
            'ownership_target': 'self',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='My Game')
        self.assertEqual(game.owner, self.user)
        self.assertIsNone(game.group)

    def test_create_game_with_ownership_group(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Group Game',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
            'ownership_target': f'group:{self.group.slug}',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Group Game')
        self.assertIsNone(game.owner)
        self.assertEqual(game.group, self.group)

    def test_create_game_with_ownership_group_not_organizer_fails(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Sneaky Game',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
            'ownership_target': f'group:{self.group.slug}',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoardGame.objects.filter(name='Sneaky Game').exists())

    def test_create_game_with_invalid_group_slug_fails(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Bad Group Game',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
            'ownership_target': 'group:nonexistent',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoardGame.objects.filter(name='Bad Group Game').exists())

    def test_create_game_with_invalid_ownership_format_fails(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Bad Format Game',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
            'ownership_target': 'invalid',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoardGame.objects.filter(name='Bad Format Game').exists())

    def test_create_game_with_no_ownership_defaults_to_self(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Default Game',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Default Game')
        self.assertEqual(game.owner, self.user)
        self.assertIsNone(game.group)

    def test_create_game_with_empty_ownership_defaults_to_self(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Empty Owner Game',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
            'ownership_target': '',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Empty Owner Game')
        self.assertEqual(game.owner, self.user)
        self.assertIsNone(game.group)

    def test_suggested_always_contains_self(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_add'))
        suggested = response.context.get('suggested_groups', [])
        self.assertIn('self', suggested)

    def test_suggested_contains_event_group_when_event_param(self):
        self.client.login(username='organizer', password='testpass123')
        event = Event.objects.create(
            title='Test Event',
            date='2026-06-01T18:00:00Z',
            created_by=self.organizer,
            group=self.group,
            voting_deadline='2026-06-01T18:00:00Z',
        )
        response = self.client.get(
            reverse('game_add'), {'event': event.pk}
        )
        suggested = response.context.get('suggested_groups', [])
        self.assertIn('self', suggested)
        self.assertIn(self.group.slug, suggested)


@tag("integration")
class GameEditOwnershipTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='owner', password='testpass123'
        )
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.group_admin = User.objects.create_user(
            username='groupadmin', password='testpass123'
        )
        cls.group = Group.objects.create(name='Edit Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )
        GroupMembership.objects.create(
            user=cls.member, group=cls.group, role='member'
        )
        GroupMembership.objects.create(
            user=cls.group_admin, group=cls.group, role='admin'
        )
        cls.user_game = BoardGame.objects.create(
            name='User Catan', owner=cls.owner,
            min_players=3, max_players=4, complexity='medium',
        )
        cls.group_game = BoardGame.objects.create(
            name='Group Catan', group=cls.group,
            min_players=3, max_players=4, complexity='medium',
        )

    def test_edit_page_has_ownership_dropdown(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(
            reverse('game_edit', kwargs={'pk': self.user_game.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ownership_target')

    def test_edit_page_shows_current_ownership_as_self(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(
            reverse('game_edit', kwargs={'pk': self.user_game.pk})
        )
        self.assertEqual(
            response.context['current_ownership'], 'self'
        )

    def test_edit_page_shows_current_ownership_as_group(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('game_edit', kwargs={'pk': self.group_game.pk})
        )
        self.assertEqual(
            response.context['current_ownership'],
            f'group:{self.group.slug}'
        )

    def test_owner_can_change_to_group(self):
        self.client.login(username='owner', password='testpass123')
        GroupMembership.objects.create(
            user=self.owner, group=self.group, role='organizer'
        )
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.user_game.pk}),
            {
                'name': 'User Catan',
                'min_players': 3,
                'max_players': 4,
                'complexity': 'medium',
                'ownership_target': f'group:{self.group.slug}',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user_game.refresh_from_db()
        self.assertIsNone(self.user_game.owner)
        self.assertEqual(self.user_game.group, self.group)

    def test_organizer_can_change_group_game_to_self(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.group_game.pk}),
            {
                'name': 'Group Catan',
                'min_players': 3,
                'max_players': 4,
                'complexity': 'medium',
                'ownership_target': 'self',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.group_game.refresh_from_db()
        self.assertEqual(self.group_game.owner, self.organizer)
        self.assertIsNone(self.group_game.group)

    def test_member_cannot_change_ownership(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.group_game.pk}),
            {
                'name': 'Group Catan',
                'min_players': 3,
                'max_players': 4,
                'complexity': 'medium',
                'ownership_target': 'self',
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_cannot_change_to_group_not_organizer_of(self):
        other_group = Group.objects.create(name='No Access Group')
        self.client.login(username='owner', password='testpass123')
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.user_game.pk}),
            {
                'name': 'User Catan',
                'min_players': 3,
                'max_players': 4,
                'complexity': 'medium',
                'ownership_target': f'group:{other_group.slug}',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.user_game.refresh_from_db()
        self.assertEqual(self.user_game.owner, self.owner)
        self.assertIsNone(self.user_game.group)

    def test_ownership_unchanged_does_not_require_confirmation(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.user_game.pk}),
            {
                'name': 'User Catan Updated',
                'min_players': 3,
                'max_players': 4,
                'complexity': 'medium',
                'ownership_target': 'self',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user_game.refresh_from_db()
        self.assertEqual(self.user_game.name, 'User Catan Updated')

    def test_group_admin_can_change_group_game_ownership(self):
        self.client.login(username='groupadmin', password='testpass123')
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.group_game.pk}),
            {
                'name': 'Group Catan',
                'min_players': 3,
                'max_players': 4,
                'complexity': 'medium',
                'ownership_target': 'self',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.group_game.refresh_from_db()
        self.assertEqual(self.group_game.owner, self.group_admin)
        self.assertIsNone(self.group_game.group)


@tag("integration")
class GroupGameAddRedirectTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.group = Group.objects.create(name='Redirect Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )

    def test_group_game_add_redirects_to_game_add(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': self.group.slug})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('group=', response.url)
        self.assertIn(self.group.slug, response.url)
        self.assertIn(reverse('game_add'), response.url)

    def test_group_game_add_post_still_works_via_redirect(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('group_game_add', kwargs={'slug': self.group.slug}),
            {
                'name': 'Redirect Game',
                'min_players': 2,
                'max_players': 4,
                'complexity': 'medium',
                'ownership_target': f'group:{self.group.slug}',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        game = BoardGame.objects.get(name='Redirect Game')
        self.assertEqual(game.group, self.group)
        self.assertIsNone(game.owner)

    def test_group_game_add_requires_login(self):
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': self.group.slug})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_group_game_add_nonexistent_group_404(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': 'nonexistent'})
        )
        self.assertEqual(response.status_code, 404)

    def test_group_game_add_disbanded_group_403(self):
        from django.utils import timezone as tz
        self.group.disbanded_at = tz.now()
        self.group.save()
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': self.group.slug})
        )
        self.assertEqual(response.status_code, 403)
        self.group.disbanded_at = None
        self.group.save()

    def test_group_game_add_member_forbidden(self):
        member = User.objects.create_user(
            username='member2', password='testpass123'
        )
        GroupMembership.objects.create(
            user=member, group=self.group, role='member'
        )
        self.client.login(username='member2', password='testpass123')
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': self.group.slug})
        )
        self.assertEqual(response.status_code, 403)


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
