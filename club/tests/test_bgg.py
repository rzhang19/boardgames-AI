import json
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase

from club.bgg import search_bgg, fetch_bgg_game, fetch_bgg_weight, weight_to_complexity, _clean_name, _score_item, _rank_results


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


class CleanNameTest(TestCase):

    def test_strips_colon(self):
        """Given a name with colon, when cleaning, then colon is removed"""
        self.assertEqual(_clean_name("Eclipse: Second Dawn"), "eclipse second dawn")

    def test_strips_apostrophe(self):
        """Given a name with apostrophe, when cleaning, then apostrophe is removed"""
        self.assertEqual(_clean_name("Chris's Game"), "chriss game")

    def test_strips_dash(self):
        """Given a name with dashes, when cleaning, then dashes are removed"""
        self.assertEqual(_clean_name("Game - Subtitle"), "game subtitle")

    def test_normalizes_whitespace(self):
        """Given a name with extra spaces, when cleaning, then whitespace is normalized"""
        self.assertEqual(_clean_name("Game  of   Thrones"), "game of thrones")

    def test_lowercase(self):
        """Given a name with uppercase, when cleaning, then name is lowercased"""
        self.assertEqual(_clean_name("MY GAME"), "my game")


class ScoreItemTest(TestCase):

    def test_full_match(self):
        """Given all query words in name, when scoring, then score is 1.0"""
        score = _score_item("Eclipse: Second Dawn for the Galaxy", ["eclipse", "second", "dawn"])
        self.assertEqual(score, 1.0)

    def test_partial_match(self):
        """Given some query words in name, when scoring, then score is fractional"""
        score = _score_item("Eclipse: New Dawn for the Galaxy", ["eclipse", "second", "dawn"])
        self.assertAlmostEqual(score, 2 / 3)

    def test_single_word_match(self):
        """Given one query word in name, when scoring, then score reflects one match"""
        score = _score_item("Eclipse Phase", ["eclipse", "second", "dawn"])
        self.assertAlmostEqual(score, 1 / 3)

    def test_no_match(self):
        """Given no query words in name, when scoring, then score is 0"""
        score = _score_item("Totally Unrelated", ["eclipse", "second", "dawn"])
        self.assertEqual(score, 0)

    def test_matches_with_apostrophe_in_name(self):
        """Given a name with apostrophe, when scoring against query without, then match occurs"""
        score = _score_item("Chris's Board Game", ["chriss", "board"])
        self.assertEqual(score, 1.0)

    def test_empty_query_words(self):
        """Given empty query words, when scoring, then score is 0"""
        score = _score_item("Some Game", [])
        self.assertEqual(score, 0)


class RankResultsTest(TestCase):

    def test_ranks_by_score_descending(self):
        """Given items with different match scores, when ranking, then higher scores come first"""
        items = [
            {'objectid': '1', 'name': 'Eclipse Phase'},
            {'objectid': '2', 'name': 'Eclipse: Second Dawn for the Galaxy'},
            {'objectid': '3', 'name': 'Eclipse: New Dawn for the Galaxy'},
        ]
        ranked = _rank_results(items, 'Eclipse Second Dawn')
        self.assertEqual(ranked[0]['name'], 'Eclipse: Second Dawn for the Galaxy')
        self.assertEqual(ranked[1]['name'], 'Eclipse: New Dawn for the Galaxy')
        self.assertEqual(ranked[2]['name'], 'Eclipse Phase')

    def test_preserves_order_for_ties(self):
        """Given items with same score, when ranking, then original order is preserved"""
        items = [
            {'objectid': '1', 'name': 'Eclipse Phase'},
            {'objectid': '2', 'name': 'Eclipse Nations'},
        ]
        ranked = _rank_results(items, 'Eclipse Random')
        self.assertEqual(ranked[0]['name'], 'Eclipse Phase')
        self.assertEqual(ranked[1]['name'], 'Eclipse Nations')

    def test_single_word_query_returns_unsorted(self):
        """Given a single word query, when ranking, then items are returned as-is"""
        items = [
            {'objectid': '1', 'name': 'Game B'},
            {'objectid': '2', 'name': 'Game A'},
        ]
        ranked = _rank_results(items, 'Game')
        self.assertEqual(ranked[0]['name'], 'Game B')

    def test_filters_zero_score_with_fallback(self):
        """Given items where none match any query word, when ranking, then all items are returned as fallback"""
        items = [
            {'objectid': '1', 'name': 'Catan'},
            {'objectid': '2', 'name': 'Monopoly'},
        ]
        ranked = _rank_results(items, 'Eclipse Second Dawn')
        self.assertEqual(len(ranked), 2)

    def test_filters_out_zero_score_items(self):
        """Given items where some match and some don't, when ranking, then zero-score items are removed"""
        items = [
            {'objectid': '1', 'name': 'Eclipse: Second Dawn for the Galaxy'},
            {'objectid': '2', 'name': 'Totally Unrelated Game'},
            {'objectid': '3', 'name': 'Eclipse Phase'},
        ]
        ranked = _rank_results(items, 'Eclipse Second Dawn')
        self.assertEqual(len(ranked), 2)
        self.assertEqual(ranked[0]['name'], 'Eclipse: Second Dawn for the Galaxy')
        self.assertEqual(ranked[1]['name'], 'Eclipse Phase')


class SearchBggRelaxedTest(TestCase):

    def _mock_response(self, data):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(data).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    @patch('club.bgg.urlopen')
    def test_single_word_returns_results_directly(self, mock_urlopen):
        """Given a single word query that returns results, when calling search_bgg, then results are returned with one API call"""
        mock_urlopen.return_value = self._mock_response({
            'items': [{'objectid': '13', 'name': 'Catan'}]
        })

        results = search_bgg('Catan')

        self.assertEqual(len(results), 1)
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch('club.bgg.urlopen')
    def test_multi_word_uses_first_token_fallback(self, mock_urlopen):
        """Given a multi-word query with no exact results, when calling search_bgg, then first-token broad results are ranked and returned"""
        empty_response = self._mock_response({'items': []})
        broad_response = self._mock_response({
            'items': [
                {'objectid': '246900', 'name': 'Eclipse: Second Dawn for the Galaxy'},
                {'objectid': '72125', 'name': 'Eclipse: New Dawn for the Galaxy'},
                {'objectid': '23272', 'name': 'Eclipse'},
            ]
        })
        mock_urlopen.side_effect = [empty_response, broad_response]

        results = search_bgg('Eclipse Second Dawn')

        self.assertTrue(len(results) >= 2)
        self.assertEqual(results[0]['name'], 'Eclipse: Second Dawn for the Galaxy')

    @patch('club.bgg.urlopen')
    def test_returns_empty_when_no_results(self, mock_urlopen):
        """Given a query where all searches return empty, when calling search_bgg, then empty list is returned"""
        mock_urlopen.return_value = self._mock_response({'items': []})

        results = search_bgg('xyznonexistent')

        self.assertEqual(results, [])


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
                {'objectid': '38133', 'name': 'Gizmo'},
                {'objectid': '242302', 'name': 'Gizmo'},
            ]
        })
        game1_response = self._mock_response({
            'item': {
                'name': 'Gizmo', 'yearpublished': '1999',
                'minplayers': None, 'maxplayers': None,
                'minplaytime': None, 'maxplaytime': None,
                'description': '', 'short_description': '',
                'canonical_link': '', 'imageurl': None, 'objectid': '38133',
            }
        })
        game2_response = self._mock_response({
            'item': {
                'name': 'Gizmo', 'yearpublished': '2018',
                'minplayers': None, 'maxplayers': None,
                'minplaytime': None, 'maxplaytime': None,
                'description': '', 'short_description': '',
                'canonical_link': '', 'imageurl': None, 'objectid': '242302',
            }
        })
        mock_urlopen.side_effect = [search_response, game1_response, game2_response]

        results = search_bgg('Gizmo')

        self.assertEqual(len(results), 2)
        names = [r['name'] for r in results]
        self.assertTrue(any('(1999)' in n for n in names), f"Expected (1999) in {names}")
        self.assertTrue(any('(2018)' in n for n in names), f"Expected (2018) in {names}")

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
                {'objectid': '38133', 'name': 'Gizmo'},
                {'objectid': '242302', 'name': 'Gizmo'},
                {'objectid': '322546', 'name': 'Gizmo: Biodome'},
            ]
        })
        game1_response = self._mock_response({
            'item': {
                'name': 'Gizmo', 'yearpublished': '1999',
                'minplayers': None, 'maxplayers': None,
                'minplaytime': None, 'maxplaytime': None,
                'description': '', 'short_description': '',
                'canonical_link': '', 'imageurl': None, 'objectid': '38133',
            }
        })
        game2_response = self._mock_response({
            'item': {
                'name': 'Gizmo', 'yearpublished': '2018',
                'minplayers': None, 'maxplayers': None,
                'minplaytime': None, 'maxplaytime': None,
                'description': '', 'short_description': '',
                'canonical_link': '', 'imageurl': None, 'objectid': '242302',
            }
        })
        mock_urlopen.side_effect = [search_response, game1_response, game2_response]

        results = search_bgg('Gizmo')

        dup_names = [r['name'] for r in results if r['name'].startswith('Gizmo (')]
        unique_names = [r['name'] for r in results if not r['name'].startswith('Gizmo (')]
        self.assertEqual(len(dup_names), 2)
        self.assertTrue(any('(1999)' in n for n in dup_names))
        self.assertTrue(any('(2018)' in n for n in dup_names))
        self.assertIn('Gizmo: Biodome', unique_names)

    @patch('club.bgg.urlopen')
    def test_duplicate_with_missing_year_uses_bgg_id(self, mock_urlopen):
        """Given duplicate names where year fetch fails, when processing, then BGG ID is used as fallback"""
        search_response = self._mock_response({
            'items': [
                {'objectid': '38133', 'name': 'Gizmo'},
                {'objectid': '242302', 'name': 'Gizmo'},
            ]
        })
        game1_response = self._mock_response({
            'item': {
                'name': 'Gizmo', 'yearpublished': None,
                'minplayers': None, 'maxplayers': None,
                'minplaytime': None, 'maxplaytime': None,
                'description': '', 'short_description': '',
                'canonical_link': '', 'imageurl': None, 'objectid': '38133',
            }
        })
        game2_response = self._mock_response({
            'item': {
                'name': 'Gizmo', 'yearpublished': '2018',
                'minplayers': None, 'maxplayers': None,
                'minplaytime': None, 'maxplaytime': None,
                'description': '', 'short_description': '',
                'canonical_link': '', 'imageurl': None, 'objectid': '242302',
            }
        })
        mock_urlopen.side_effect = [search_response, game1_response, game2_response]

        results = search_bgg('Gizmo')

        names = [r['name'] for r in results]
        self.assertTrue(any('BGG: 38133' in n for n in names), f"Expected BGG: 38133 in {names}")
        self.assertTrue(any('(2018)' in n for n in names), f"Expected (2018) in {names}")
