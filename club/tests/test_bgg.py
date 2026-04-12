import json
from unittest.mock import patch, MagicMock
from django.test import TestCase

from club.bgg import search_bgg, fetch_bgg_game


class SearchBggTest(TestCase):

    @patch('club.bgg.urlopen')
    def test_search_returns_list_of_results(self, mock_urlopen):
        """Given a search query, when calling search_bgg, then a list of dicts with id and name is returned"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'items': [
                {'objectid': '13', 'name': 'Catan'},
                {'objectid': '278', 'name': 'Catan Card Game'},
            ]
        }).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        results = search_bgg('Catan')

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], {'id': 13, 'name': 'Catan'})
        self.assertEqual(results[1], {'id': 278, 'name': 'Catan Card Game'})

    @patch('club.bgg.urlopen')
    def test_search_returns_empty_list_when_no_results(self, mock_urlopen):
        """Given a search query with no matches, when calling search_bgg, then an empty list is returned"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({'items': []}).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        results = search_bgg('xyznonexistent')

        self.assertEqual(results, [])

    @patch('club.bgg.urlopen')
    def test_search_limits_results_to_20(self, mock_urlopen):
        """Given a search returning many results, when calling search_bgg, then only first 20 are returned"""
        items = [{'objectid': str(i), 'name': f'Game {i}'} for i in range(50)]
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({'items': items}).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        results = search_bgg('Game')

        self.assertEqual(len(results), 20)

    @patch('club.bgg.urlopen')
    def test_search_handles_api_error_gracefully(self, mock_urlopen):
        """Given an API error, when calling search_bgg, then an empty list is returned"""
        mock_urlopen.side_effect = Exception('Network error')

        results = search_bgg('Catan')

        self.assertEqual(results, [])

    @patch('club.bgg.urlopen')
    def test_search_calls_correct_url(self, mock_urlopen):
        """Given a search query, when calling search_bgg, then the correct BGG API URL is called"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({'items': []}).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        search_bgg('Pandemic')

        call_args = mock_urlopen.call_args[0][0]
        self.assertIn('search=Pandemic', call_args.full_url)
        self.assertIn('subtype=boardgame', call_args.full_url)


class FetchBggGameTest(TestCase):

    @patch('club.bgg.urlopen')
    def test_fetch_returns_game_data(self, mock_urlopen):
        """Given a valid BGG ID, when calling fetch_bgg_game, then game data dict is returned"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'item': {
                'name': 'Catan',
                'yearpublished': '1995',
                'minplayers': '3',
                'maxplayers': '4',
                'minplaytime': '60',
                'maxplaytime': '120',
                'description': '<p>A settlement game</p>',
                'short_description': 'A settlement game',
                'canonical_link': 'https://boardgamegeek.com/boardgame/13/catan',
                'imageurl': 'https://cf.geekdo-images.com/pic123.png',
                'objectid': '13',
            }
        }).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = fetch_bgg_game(13)

        self.assertEqual(result['name'], 'Catan')
        self.assertEqual(result['bgg_id'], 13)
        self.assertEqual(result['min_players'], 3)
        self.assertEqual(result['max_players'], 4)
        self.assertEqual(result['description'], 'A settlement game')
        self.assertEqual(result['bgg_link'], 'https://boardgamegeek.com/boardgame/13/catan')
        self.assertEqual(result['image_url'], 'https://cf.geekdo-images.com/pic123.png')

    @patch('club.bgg.urlopen')
    def test_fetch_handles_missing_optional_fields(self, mock_urlopen):
        """Given a BGG game with minimal data, when calling fetch_bgg_game, then None is used for missing fields"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'item': {
                'name': 'Simple Game',
                'yearpublished': '2020',
                'minplayers': None,
                'maxplayers': None,
                'minplaytime': None,
                'maxplaytime': None,
                'description': '',
                'short_description': '',
                'canonical_link': 'https://boardgamegeek.com/boardgame/999/simple-game',
                'imageurl': None,
                'objectid': '999',
            }
        }).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = fetch_bgg_game(999)

        self.assertEqual(result['name'], 'Simple Game')
        self.assertIsNone(result['min_players'])
        self.assertIsNone(result['max_players'])
        self.assertIsNone(result['image_url'])

    @patch('club.bgg.urlopen')
    def test_fetch_returns_none_on_api_error(self, mock_urlopen):
        """Given an API error, when calling fetch_bgg_game, then None is returned"""
        mock_urlopen.side_effect = Exception('Network error')

        result = fetch_bgg_game(13)

        self.assertIsNone(result)

    @patch('club.bgg.urlopen')
    def test_fetch_uses_short_description_when_available(self, mock_urlopen):
        """Given a game with short_description, when calling fetch_bgg_game, then short_description is used"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'item': {
                'name': 'Catan',
                'yearpublished': '1995',
                'minplayers': '3',
                'maxplayers': '4',
                'minplaytime': '60',
                'maxplaytime': '120',
                'description': '<p>Very long HTML description</p>',
                'short_description': 'Short clean description',
                'canonical_link': 'https://boardgamegeek.com/boardgame/13/catan',
                'imageurl': 'https://cf.geekdo-images.com/pic123.png',
                'objectid': '13',
            }
        }).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = fetch_bgg_game(13)

        self.assertEqual(result['description'], 'Short clean description')

    @patch('club.bgg.urlopen')
    def test_fetch_calls_correct_url(self, mock_urlopen):
        """Given a BGG game ID, when calling fetch_bgg_game, then the correct BGG API URL is called"""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'item': {
                'name': 'Test', 'yearpublished': '2020',
                'minplayers': None, 'maxplayers': None,
                'minplaytime': None, 'maxplaytime': None,
                'description': '', 'short_description': '',
                'canonical_link': '', 'imageurl': None, 'objectid': '42',
            }
        }).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        fetch_bgg_game(42)

        call_args = mock_urlopen.call_args[0][0]
        self.assertIn('objectid=42', call_args.full_url)
        self.assertIn('objecttype=thing', call_args.full_url)
