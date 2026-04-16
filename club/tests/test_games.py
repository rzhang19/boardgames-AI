from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from club.models import BoardGame

User = get_user_model()


class GameListViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='gameowner', password='testpass123'
        )
        self.game1 = BoardGame.objects.create(
            name='Catan', owner=self.user, min_players=3, max_players=4
        )
        self.game2 = BoardGame.objects.create(
            name='Chess', owner=self.user
        )

    def test_game_list_displays_all_games(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Catan')
        self.assertContains(response, 'Chess')

    def test_game_list_requires_login(self):
        response = self.client.get(reverse('game_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)


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
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Catan')
        self.assertEqual(game.bgg_id, 13)

    def test_create_game_without_bgg_id_still_works(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Chess',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Chess')
        self.assertIsNone(game.bgg_id)


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
