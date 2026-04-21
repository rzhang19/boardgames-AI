import json
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from club.models import BoardGame

User = get_user_model()


class BggSearchViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='searcher', password='testpass123'
        )

    def test_bgg_search_requires_login(self):
        """Given an unauthenticated user, when accessing bgg_search, then redirect to login"""
        response = self.client.get(reverse('bgg_search'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    @patch('club.views.search_bgg')
    def test_bgg_search_returns_json(self, mock_search):
        """Given a logged-in user and query, when searching BGG, then JSON results are returned"""
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
        """Given a query parameter, when searching BGG, then the query is passed to search_bgg"""
        mock_search.return_value = []
        self.client.login(username='searcher', password='testpass123')
        self.client.get(reverse('bgg_search'), {'q': 'Pandemic'})
        mock_search.assert_called_once_with('Pandemic')

    @patch('club.views.search_bgg')
    def test_bgg_search_returns_empty_on_api_error(self, mock_search):
        """Given a BGG API failure, when searching, then empty JSON list is returned"""
        mock_search.return_value = []
        self.client.login(username='searcher', password='testpass123')
        response = self.client.get(reverse('bgg_search'), {'q': 'xyz'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data, [])

    def test_bgg_search_without_query_returns_empty(self):
        """Given no query parameter, when searching BGG, then empty JSON list is returned"""
        self.client.login(username='searcher', password='testpass123')
        response = self.client.get(reverse('bgg_search'))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data, [])


class BggImportViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='importer', password='testpass123'
        )

    def test_bgg_import_requires_login(self):
        """Given an unauthenticated user, when accessing bgg_import, then redirect to login"""
        response = self.client.get(reverse('bgg_import', kwargs={'bgg_id': 13}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    @patch('club.views.fetch_bgg_game')
    def test_bgg_import_returns_json(self, mock_fetch):
        """Given a logged-in user and valid BGG ID, when importing, then JSON game data is returned"""
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
        """Given a valid BGG ID, when importing, then JSON includes bgg_weight and suggested complexity"""
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
        """Given an invalid BGG ID, when importing, then JSON error is returned"""
        mock_fetch.return_value = None
        self.client.login(username='importer', password='testpass123')
        response = self.client.get(reverse('bgg_import', kwargs={'bgg_id': 999999}))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('error', data)


class GameAddWithBggTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='creator', password='testpass123'
        )

    @patch('club.views.fetch_bgg_game')
    def test_create_game_with_bgg_id_fetches_and_saves_data(self, mock_fetch):
        """Given a bgg_id on game creation, when posting, then BGG data is fetched and saved"""
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
        """Given no bgg_id on game creation, when posting, then no BGG fetch occurs"""
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
        """Given a bgg_id that fails to fetch, when posting, then game is still created without BGG data"""
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
        """Given a bgg_id with weight data, when posting, then complexity is auto-filled from BGG"""
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
        """Given a bgg_id where weight fetch fails, when posting, then game is still created"""
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
        """Given a bgg_id on game edit, when posting, then BGG data is fetched and updated"""
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


class GameDetailWithBggTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='viewer', password='testpass123'
        )

    def test_game_detail_shows_bgg_link(self):
        """Given a game with bgg_link, when viewing detail, then BGG link is shown"""
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
        """Given a game with image_url, when viewing detail, then BGG image is shown"""
        game = BoardGame.objects.create(
            name='Catan', owner=self.user,
            bgg_id=13,
            image_url='https://cf.geekdo-images.com/pic123.png',
        )
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(response, 'pic123.png')

    def test_game_detail_without_bgg_data_hides_bgg_elements(self):
        """Given a game without BGG data, when viewing detail, then no BGG elements are shown"""
        game = BoardGame.objects.create(
            name='Chess', owner=self.user,
        )
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertNotContains(response, 'Link to BoardGameGeek site')
        self.assertNotContains(response, 'boardgamegeek.com')

    def test_game_detail_shows_bgg_weight(self):
        """Given a game with bgg_weight, when viewing detail, then weight value is shown"""
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
        """Given a game with bgg_link, when viewing detail, then 'Link to BoardGameGeek site' is shown"""
        game = BoardGame.objects.create(
            name='Catan', owner=self.user,
            bgg_id=13,
            bgg_link='https://boardgamegeek.com/boardgame/13/catan',
        )
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(response, 'Link to BoardGameGeek site')

    def test_game_detail_bgg_link_opens_in_new_tab(self):
        """Given a game with bgg_link, when viewing detail, then the link opens in a new tab"""
        game = BoardGame.objects.create(
            name='Catan', owner=self.user,
            bgg_id=13,
            bgg_link='https://boardgamegeek.com/boardgame/13/catan',
        )
        self.client.login(username='viewer', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(response, 'target="_blank"')


class ParseBggLinkTest(TestCase):

    def test_parse_full_url_extracts_id(self):
        """Given a full BGG URL, when parsing, then the numeric ID is extracted"""
        from club.utils import parse_bgg_link
        result = parse_bgg_link('https://boardgamegeek.com/boardgame/13/catan')
        self.assertEqual(result, {'bgg_id': 13, 'bgg_link': 'https://boardgamegeek.com/boardgame/13/catan'})

    def test_parse_url_without_slug(self):
        """Given a BGG URL without slug, when parsing, then the ID is extracted"""
        from club.utils import parse_bgg_link
        result = parse_bgg_link('https://boardgamegeek.com/boardgame/13')
        self.assertEqual(result, {'bgg_id': 13, 'bgg_link': 'https://boardgamegeek.com/boardgame/13'})

    def test_parse_url_with_http(self):
        """Given an http BGG URL, when parsing, then the ID is extracted"""
        from club.utils import parse_bgg_link
        result = parse_bgg_link('http://boardgamegeek.com/boardgame/13/catan')
        self.assertEqual(result, {'bgg_id': 13, 'bgg_link': 'http://boardgamegeek.com/boardgame/13/catan'})

    def test_parse_url_without_scheme(self):
        """Given a BGG URL without scheme, when parsing, then the ID is extracted"""
        from club.utils import parse_bgg_link
        result = parse_bgg_link('boardgamegeek.com/boardgame/13/catan')
        self.assertEqual(result, {'bgg_id': 13, 'bgg_link': 'https://boardgamegeek.com/boardgame/13/catan'})

    def test_parse_expansion_url(self):
        """Given a BGG expansion URL, when parsing, then the ID is extracted"""
        from club.utils import parse_bgg_link
        result = parse_bgg_link('https://boardgamegeek.com/boardgameexpansion/1234/some-expansion')
        self.assertEqual(result, {'bgg_id': 1234, 'bgg_link': 'https://boardgamegeek.com/boardgameexpansion/1234/some-expansion'})

    def test_parse_raw_id(self):
        """Given a raw numeric ID, when parsing, then a BGG link is constructed"""
        from club.utils import parse_bgg_link
        result = parse_bgg_link('13')
        self.assertEqual(result, {'bgg_id': 13, 'bgg_link': 'https://boardgamegeek.com/boardgame/13/'})

    def test_parse_empty_string_returns_none(self):
        """Given an empty string, when parsing, then None is returned"""
        from club.utils import parse_bgg_link
        result = parse_bgg_link('')
        self.assertIsNone(result)

    def test_parse_whitespace_returns_none(self):
        """Given only whitespace, when parsing, then None is returned"""
        from club.utils import parse_bgg_link
        result = parse_bgg_link('   ')
        self.assertIsNone(result)

    def test_parse_non_bgg_url_returns_none(self):
        """Given a non-BGG URL, when parsing, then None is returned"""
        from club.utils import parse_bgg_link
        result = parse_bgg_link('https://example.com/something')
        self.assertIsNone(result)

    def test_parse_invalid_string_returns_none(self):
        """Given a random non-URL non-numeric string, when parsing, then None is returned"""
        from club.utils import parse_bgg_link
        result = parse_bgg_link('not a url or id')
        self.assertIsNone(result)

    def test_parse_url_with_trailing_slash(self):
        """Given a BGG URL with trailing slash, when parsing, then the ID is extracted"""
        from club.utils import parse_bgg_link
        result = parse_bgg_link('https://boardgamegeek.com/boardgame/13/')
        self.assertEqual(result, {'bgg_id': 13, 'bgg_link': 'https://boardgamegeek.com/boardgame/13/'})

    def test_parse_url_with_www(self):
        """Given a BGG URL with www subdomain, when parsing, then the ID is extracted"""
        from club.utils import parse_bgg_link
        result = parse_bgg_link('https://www.boardgamegeek.com/boardgame/13/catan')
        self.assertEqual(result, {'bgg_id': 13, 'bgg_link': 'https://www.boardgamegeek.com/boardgame/13/catan'})


class GameAddWithBggLinkInputTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='creator', password='testpass123'
        )

    @patch('club.views.fetch_bgg_game')
    def test_create_with_bgg_link_url(self, mock_fetch):
        """Given a BGG URL in bgg_link_input, when creating a game, then bgg_id and bgg_link are saved"""
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
        """Given a raw BGG ID in bgg_link_input, when creating a game, then bgg_id and constructed link are saved"""
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
        """Given no bgg_link_input, when creating a game, then no BGG data is saved"""
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
        """Given an invalid bgg_link_input, when creating a game, then form shows an error"""
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
        """Given a BGG URL in bgg_link_input, when creating a game, then BGG data is fetched and saved"""
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
        """Given both bgg_id (from search) and bgg_link_input, when creating, then bgg_id takes precedence"""
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
        """Given the add game page, when rendering, then the bgg_link_input field is shown"""
        self.client.login(username='creator', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertContains(response, 'bgg_link_input')

    def test_add_form_shows_soft_warning_without_bgg(self):
        """Given the add game page, when rendering, then a soft warning about no BGG link is shown"""
        self.client.login(username='creator', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertContains(response, 'bgg-link-warning')


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
        """Given a game with bgg_link, when loading edit form, then the bgg_link is shown in the input"""
        self.game.bgg_id = 13
        self.game.bgg_link = 'https://boardgamegeek.com/boardgame/13/catan'
        self.game.save()
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(reverse('game_edit', kwargs={'pk': self.game.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'https://boardgamegeek.com/boardgame/13/catan')

    def test_edit_adds_bgg_link_via_url(self):
        """Given a BGG URL in bgg_link_input, when editing a game, then bgg_id and bgg_link are saved"""
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
        """Given a game with bgg_link, when editing and clearing bgg_link_input, then BGG data is removed"""
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
