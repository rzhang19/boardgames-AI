import json
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase

from club.bgg import search_bgg, fetch_bgg_game, fetch_bgg_weight, weight_to_complexity


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


class FetchBggWeightTest(TestCase):

    BGG_XML_RESPONSE = '''<?xml version="1.0" encoding="utf-8"?>
<items termsofuse="https://boardgamegeek.com/xmlapi/termsofuse">
  <item type="boardgame" id="13">
    <statistics>
      <ratings>
        <averageweight value="2.28"/>
      </ratings>
    </statistics>
  </item>
</items>'''

    BGG_XML_NO_STATS = '''<?xml version="1.0" encoding="utf-8"?>
<items termsofuse="https://boardgamegeek.com/xmlapi/termsofuse">
  <item type="boardgame" id="13">
  </item>
</items>'''

    BGG_XML_EMPTY_WEIGHT = '''<?xml version="1.0" encoding="utf-8"?>
<items termsofuse="https://boardgamegeek.com/xmlapi/termsofuse">
  <item type="boardgame" id="13">
    <statistics>
      <ratings>
        <averageweight value="0"/>
      </ratings>
    </statistics>
  </item>
</items>'''

    @patch('club.bgg.urlopen')
    def test_fetch_weight_returns_decimal(self, mock_urlopen):
        """Given a valid BGG ID with stats, when calling fetch_bgg_weight, then a Decimal weight is returned"""
        mock_response = MagicMock()
        mock_response.read.return_value = self.BGG_XML_RESPONSE.encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = fetch_bgg_weight(13)

        self.assertEqual(result, Decimal('2.28'))

    @patch('club.bgg.urlopen')
    def test_fetch_weight_calls_xml_api(self, mock_urlopen):
        """Given a BGG ID, when calling fetch_bgg_weight, then the XML API v2 with stats=1 is called"""
        mock_response = MagicMock()
        mock_response.read.return_value = self.BGG_XML_RESPONSE.encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        fetch_bgg_weight(13)

        call_args = mock_urlopen.call_args[0][0]
        self.assertIn('xmlapi2/thing', call_args.full_url)
        self.assertIn('id=13', call_args.full_url)
        self.assertIn('stats=1', call_args.full_url)

    @patch('club.bgg.urlopen')
    def test_fetch_weight_returns_none_on_api_error(self, mock_urlopen):
        """Given an API error, when calling fetch_bgg_weight, then None is returned"""
        mock_urlopen.side_effect = Exception('Network error')

        result = fetch_bgg_weight(13)

        self.assertIsNone(result)

    @patch('club.bgg.urlopen')
    def test_fetch_weight_returns_none_when_no_stats(self, mock_urlopen):
        """Given a BGG response without statistics, when calling fetch_bgg_weight, then None is returned"""
        mock_response = MagicMock()
        mock_response.read.return_value = self.BGG_XML_NO_STATS.encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = fetch_bgg_weight(13)

        self.assertIsNone(result)

    @patch('club.bgg.urlopen')
    def test_fetch_weight_returns_none_when_zero_weight(self, mock_urlopen):
        """Given a BGG response with 0 weight (unrated), when calling fetch_bgg_weight, then None is returned"""
        mock_response = MagicMock()
        mock_response.read.return_value = self.BGG_XML_EMPTY_WEIGHT.encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = fetch_bgg_weight(13)

        self.assertIsNone(result)

    @patch('club.bgg.urlopen')
    def test_fetch_weight_returns_none_on_malformed_xml(self, mock_urlopen):
        """Given malformed XML, when calling fetch_bgg_weight, then None is returned"""
        mock_response = MagicMock()
        mock_response.read.return_value = b'<not valid xml'
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = fetch_bgg_weight(13)

        self.assertIsNone(result)


class WeightToComplexityTest(TestCase):

    def test_weight_below_2_is_light(self):
        """Given weight 1.5, when mapping to complexity, then 'light' is returned"""
        self.assertEqual(weight_to_complexity(Decimal('1.5')), 'light')

    def test_weight_exactly_1_is_light(self):
        """Given weight 1.0, when mapping to complexity, then 'light' is returned"""
        self.assertEqual(weight_to_complexity(Decimal('1.0')), 'light')

    def test_weight_exactly_2_is_medium(self):
        """Given weight 2.0, when mapping to complexity, then 'medium' is returned"""
        self.assertEqual(weight_to_complexity(Decimal('2.0')), 'medium')

    def test_weight_2_point_28_is_medium(self):
        """Given weight 2.28, when mapping to complexity, then 'medium' is returned"""
        self.assertEqual(weight_to_complexity(Decimal('2.28')), 'medium')

    def test_weight_exactly_3_is_medium_heavy(self):
        """Given weight 3.0, when mapping to complexity, then 'medium_heavy' is returned"""
        self.assertEqual(weight_to_complexity(Decimal('3.0')), 'medium_heavy')

    def test_weight_3_point_5_is_medium_heavy(self):
        """Given weight 3.5, when mapping to complexity, then 'medium_heavy' is returned"""
        self.assertEqual(weight_to_complexity(Decimal('3.5')), 'medium_heavy')

    def test_weight_exactly_4_is_heavy(self):
        """Given weight 4.0, when mapping to complexity, then 'heavy' is returned"""
        self.assertEqual(weight_to_complexity(Decimal('4.0')), 'heavy')

    def test_weight_4_point_5_is_heavy(self):
        """Given weight 4.5, when mapping to complexity, then 'heavy' is returned"""
        self.assertEqual(weight_to_complexity(Decimal('4.5')), 'heavy')

    def test_weight_exactly_5_is_heavy(self):
        """Given weight 5.0, when mapping to complexity, then 'heavy' is returned"""
        self.assertEqual(weight_to_complexity(Decimal('5.0')), 'heavy')

    def test_weight_none_returns_none(self):
        """Given None weight, when mapping to complexity, then None is returned"""
        self.assertIsNone(weight_to_complexity(None))

    def test_weight_1_point_99_is_light(self):
        """Given weight 1.99, when mapping to complexity, then 'light' is returned"""
        self.assertEqual(weight_to_complexity(Decimal('1.99')), 'light')

    def test_weight_2_point_99_is_medium(self):
        """Given weight 2.99, when mapping to complexity, then 'medium' is returned"""
        self.assertEqual(weight_to_complexity(Decimal('2.99')), 'medium')

    def test_weight_3_point_99_is_medium_heavy(self):
        """Given weight 3.99, when mapping to complexity, then 'medium_heavy' is returned"""
        self.assertEqual(weight_to_complexity(Decimal('3.99')), 'medium_heavy')


class SearchBggRelaxedTest(TestCase):

    def _mock_response(self, data):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(data).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    @patch('club.bgg.urlopen')
    def test_search_returns_results_without_retry_when_found(self, mock_urlopen):
        """Given a query that returns results, when calling search_bgg, then no retry occurs"""
        mock_urlopen.return_value = self._mock_response({
            'items': [{'objectid': '13', 'name': 'Catan'}]
        })

        results = search_bgg('Catan')

        self.assertEqual(len(results), 1)
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch('club.bgg.urlopen')
    def test_search_retries_without_punctuation_when_no_results(self, mock_urlopen):
        """Given a query with punctuation that returns 0 results, when calling search_bgg, then retry without punctuation returns results"""
        empty_response = self._mock_response({'items': []})
        results_response = self._mock_response({
            'items': [{'objectid': '246900', 'name': 'Eclipse: Second Dawn for the Galaxy'}]
        })
        mock_urlopen.side_effect = [empty_response, results_response]

        results = search_bgg('Eclipse: Second Dawn')

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Eclipse: Second Dawn for the Galaxy')
        self.assertEqual(mock_urlopen.call_count, 2)

    @patch('club.bgg.urlopen')
    def test_search_strips_colons_and_dashes(self, mock_urlopen):
        """Given a query with colons and dashes, when retry occurs, then punctuation is removed"""
        empty_response = self._mock_response({'items': []})
        results_response = self._mock_response({
            'items': [{'objectid': '100', 'name': 'Game Name'}]
        })
        mock_urlopen.side_effect = [empty_response, results_response]

        results = search_bgg('Game: The - Name')

        self.assertEqual(len(results), 1)
        second_call_url = mock_urlopen.call_args_list[1][0][0].full_url
        self.assertIn('Game+The+Name', second_call_url)

    @patch('club.bgg.urlopen')
    def test_search_returns_empty_when_all_retries_fail(self, mock_urlopen):
        """Given a query where all retries return 0 results, when calling search_bgg, then empty list is returned"""
        empty_response = self._mock_response({'items': []})
        mock_urlopen.side_effect = [empty_response, empty_response, empty_response]

        results = search_bgg('xyznonexistent')

        self.assertEqual(results, [])

    @patch('club.bgg.urlopen')
    def test_search_does_not_retry_when_initial_query_works(self, mock_urlopen):
        """Given a query with punctuation that already returns results, when calling search_bgg, then both parallel queries share the same mock response and results are returned"""
        results_response = self._mock_response({
            'items': [{'objectid': '246900', 'name': 'Eclipse: Second Dawn for the Galaxy'}]
        })
        mock_urlopen.return_value = results_response

        results = search_bgg('Eclipse: Second Dawn')

        self.assertEqual(len(results), 1)


class SearchBggDuplicatesTest(TestCase):

    def _mock_response(self, data):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(data).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    @patch('club.bgg.urlopen')
    def test_duplicate_names_get_year_appended(self, mock_urlopen):
        """Given search results with duplicate names, when processing, then year is appended to distinguish them"""
        search_response = self._mock_response({
            'items': [
                {'objectid': '38133', 'name': 'Space Base'},
                {'objectid': '242302', 'name': 'Space Base'},
            ]
        })
        game1_response = self._mock_response({
            'item': {
                'name': 'Space Base', 'yearpublished': '1999',
                'minplayers': None, 'maxplayers': None,
                'minplaytime': None, 'maxplaytime': None,
                'description': '', 'short_description': '',
                'canonical_link': '', 'imageurl': None, 'objectid': '38133',
            }
        })
        game2_response = self._mock_response({
            'item': {
                'name': 'Space Base', 'yearpublished': '2018',
                'minplayers': None, 'maxplayers': None,
                'minplaytime': None, 'maxplaytime': None,
                'description': '', 'short_description': '',
                'canonical_link': '', 'imageurl': None, 'objectid': '242302',
            }
        })
        mock_urlopen.side_effect = [search_response, game1_response, game2_response]

        results = search_bgg('Space Base')

        self.assertEqual(len(results), 2)
        self.assertIn('(1999)', results[0]['name'])
        self.assertIn('(2018)', results[1]['name'])

    @patch('club.bgg.urlopen')
    def test_unique_names_unchanged(self, mock_urlopen):
        """Given search results with all unique names, when processing, then names are unchanged"""
        mock_urlopen.return_value = self._mock_response({
            'items': [
                {'objectid': '13', 'name': 'Catan'},
                {'objectid': '278', 'name': 'Catan Card Game'},
            ]
        })

        results = search_bgg('Catan')

        self.assertEqual(results[0]['name'], 'Catan')
        self.assertEqual(results[1]['name'], 'Catan Card Game')
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch('club.bgg.urlopen')
    def test_mixed_duplicates_and_uniques(self, mock_urlopen):
        """Given search results with some duplicate names and some unique, when processing, then only duplicates get year"""
        search_response = self._mock_response({
            'items': [
                {'objectid': '38133', 'name': 'Space Base'},
                {'objectid': '242302', 'name': 'Space Base'},
                {'objectid': '322546', 'name': 'Space Base: Biodome'},
            ]
        })
        game1_response = self._mock_response({
            'item': {
                'name': 'Space Base', 'yearpublished': '1999',
                'minplayers': None, 'maxplayers': None,
                'minplaytime': None, 'maxplaytime': None,
                'description': '', 'short_description': '',
                'canonical_link': '', 'imageurl': None, 'objectid': '38133',
            }
        })
        game2_response = self._mock_response({
            'item': {
                'name': 'Space Base', 'yearpublished': '2018',
                'minplayers': None, 'maxplayers': None,
                'minplaytime': None, 'maxplaytime': None,
                'description': '', 'short_description': '',
                'canonical_link': '', 'imageurl': None, 'objectid': '242302',
            }
        })
        mock_urlopen.side_effect = [search_response, game1_response, game2_response]

        results = search_bgg('Space Base')

        self.assertIn('(1999)', results[0]['name'])
        self.assertIn('(2018)', results[1]['name'])
        self.assertEqual(results[2]['name'], 'Space Base: Biodome')

    @patch('club.bgg.urlopen')
    def test_duplicate_with_missing_year_uses_bgg_id(self, mock_urlopen):
        """Given duplicate names where year fetch fails, when processing, then BGG ID is used as fallback"""
        search_response = self._mock_response({
            'items': [
                {'objectid': '38133', 'name': 'Space Base'},
                {'objectid': '242302', 'name': 'Space Base'},
            ]
        })
        game1_response = self._mock_response({
            'item': {
                'name': 'Space Base', 'yearpublished': None,
                'minplayers': None, 'maxplayers': None,
                'minplaytime': None, 'maxplaytime': None,
                'description': '', 'short_description': '',
                'canonical_link': '', 'imageurl': None, 'objectid': '38133',
            }
        })
        game2_response = self._mock_response({
            'item': {
                'name': 'Space Base', 'yearpublished': '2018',
                'minplayers': None, 'maxplayers': None,
                'minplaytime': None, 'maxplaytime': None,
                'description': '', 'short_description': '',
                'canonical_link': '', 'imageurl': None, 'objectid': '242302',
            }
        })
        mock_urlopen.side_effect = [search_response, game1_response, game2_response]

        results = search_bgg('Space Base')

        self.assertIn('BGG: 38133', results[0]['name'])
        self.assertIn('(2018)', results[1]['name'])
