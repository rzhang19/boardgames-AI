from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.urls import reverse

from club.models import BoardGame

User = get_user_model()


@tag("integration")
class GameListViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='gameowner', password='testpass123'
        )
        self.other_user = User.objects.create_user(
            username='otherplayer', password='testpass123'
        )
        self.game1 = BoardGame.objects.create(
            name='Catan', owner=self.user, min_players=3, max_players=4,
            image_url='https://cf.geekdo-images.com/pic123.png',
        )
        self.game2 = BoardGame.objects.create(
            name='Chess', owner=self.user
        )
        self.game3 = BoardGame.objects.create(
            name='Risk', owner=self.other_user, min_players=2, max_players=6
        )

    def test_game_list_displays_all_games(self):
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

    def setUp(self):
        self.user = User.objects.create_user(
            username='gameowner', password='testpass123'
        )
        self.other_user = User.objects.create_user(
            username='otherplayer', password='testpass123'
        )
        self.third_user = User.objects.create_user(
            username='thirdplayer', password='testpass123'
        )
        self.game1 = BoardGame.objects.create(
            name='Catan', owner=self.user, min_players=3, max_players=4
        )
        self.game2 = BoardGame.objects.create(
            name='Risk', owner=self.other_user, min_players=2, max_players=6
        )
        self.game3 = BoardGame.objects.create(
            name='Pandemic', owner=self.third_user
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

    def setUp(self):
        self.user = User.objects.create_user(
            username='gameowner', password='testpass123'
        )
        self.game1 = BoardGame.objects.create(
            name='Catan', owner=self.user, min_players=3, max_players=4
        )
        self.game2 = BoardGame.objects.create(
            name='Risk', owner=self.user, min_players=2, max_players=6
        )
        self.game3 = BoardGame.objects.create(
            name='Chess', owner=self.user
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

    def setUp(self):
        self.user = User.objects.create_user(
            username='alice', password='testpass123'
        )
        self.other_user = User.objects.create_user(
            username='bob', password='testpass123'
        )
        self.game1 = BoardGame.objects.create(
            name='Catan', owner=self.user, min_players=3, max_players=4
        )
        self.game2 = BoardGame.objects.create(
            name='Azul', owner=self.other_user, min_players=2, max_players=4
        )
        self.game3 = BoardGame.objects.create(
            name='Risk', owner=self.user, min_players=2, max_players=6
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

    def setUp(self):
        self.user = User.objects.create_user(
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

    def setUp(self):
        self.user = User.objects.create_user(
            username='owner', password='testpass123'
        )
        self.game = BoardGame.objects.create(
            name='Catan', owner=self.user,
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

    def test_game_detail_nonexistent_game_returns_404(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': 9999}))
        self.assertEqual(response.status_code, 404)

    def test_game_detail_shows_edit_link_for_owner(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': self.game.pk}))
        self.assertContains(response, reverse('game_edit', kwargs={'pk': self.game.pk}))

    def test_game_detail_hides_edit_link_for_non_owner(self):
        other_user = User.objects.create_user(username='other', password='testpass123')
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

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', password='testpass123'
        )
        self.other_user = User.objects.create_user(
            username='other', password='testpass123'
        )
        self.game = BoardGame.objects.create(
            name='Catan', owner=self.owner
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
        self.assertEqual(response.status_code, 403)

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
        self.assertEqual(response.status_code, 403)
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

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', password='testpass123'
        )
        self.other_user = User.objects.create_user(
            username='other', password='testpass123'
        )
        self.game = BoardGame.objects.create(
            name='Catan', owner=self.owner
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
        self.assertEqual(response.status_code, 403)

    def test_owner_can_delete_game(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.post(reverse('game_delete', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BoardGame.objects.filter(pk=self.game.pk).exists())
        self.assertEqual(response.url, reverse('game_list'))

    def test_non_owner_cannot_delete_game(self):
        self.client.login(username='other', password='testpass123')
        response = self.client.post(reverse('game_delete', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 403)
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
