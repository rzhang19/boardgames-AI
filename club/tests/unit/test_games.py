import json
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone

from club.models import (
    BoardGame,
    Event,
    EventTag,
    GameTag,
    GameSession,
    GameSessionPlayer,
    Group,
    GroupMembership,
)
from club.bgg import (
    search_bgg,
    fetch_bgg_game,
    fetch_bgg_weight,
    weight_to_complexity,
    _clean_name,
    _score_item,
    _rank_results,
)

User = get_user_model()


def _make_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='admin')


@tag("unit")
class BoardGameModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='gameowner', password='testpass123'
        )

    def test_create_board_game_with_all_fields(self):
        game = BoardGame.objects.create(
            name='Catan',
            description='A classic resource management game',
            owner=self.user,
            min_players=3,
            max_players=4,
        )
        self.assertEqual(game.name, 'Catan')
        self.assertEqual(game.description, 'A classic resource management game')
        self.assertEqual(game.owner, self.user)
        self.assertEqual(game.min_players, 3)
        self.assertEqual(game.max_players, 4)
        self.assertIsNotNone(game.created_at)

    def test_create_board_game_with_only_required_fields(self):
        game = BoardGame.objects.create(
            name='Chess',
            owner=self.user,
        )
        self.assertEqual(game.name, 'Chess')
        self.assertEqual(game.description, '')
        self.assertIsNone(game.min_players)
        self.assertIsNone(game.max_players)

    def test_board_game_string_representation(self):
        game = BoardGame.objects.create(
            name='Ticket to Ride',
            owner=self.user,
        )
        self.assertEqual(str(game), 'Ticket to Ride')

    def test_board_game_owner_relationship(self):
        game = BoardGame.objects.create(
            name='Pandemic',
            owner=self.user,
        )
        self.assertIn(game, self.user.boardgame_set.all())

    def test_board_game_bgg_fields_default_to_none(self):
        game = BoardGame.objects.create(
            name='Chess',
            owner=self.user,
        )
        self.assertIsNone(game.bgg_id)
        self.assertEqual(game.bgg_link, '')
        self.assertEqual(game.image_url, '')
        self.assertIsNone(game.bgg_last_synced)

    def test_board_game_with_bgg_data(self):
        from django.utils import timezone as tz
        synced = tz.now()
        game = BoardGame.objects.create(
            name='Catan',
            owner=self.user,
            bgg_id=13,
            bgg_link='https://boardgamegeek.com/boardgame/13/catan',
            image_url='https://cf.geekdo-images.com/pic123.png',
            bgg_last_synced=synced,
        )
        self.assertEqual(game.bgg_id, 13)
        self.assertEqual(game.bgg_link, 'https://boardgamegeek.com/boardgame/13/catan')
        self.assertEqual(game.image_url, 'https://cf.geekdo-images.com/pic123.png')
        self.assertEqual(game.bgg_last_synced, synced)

    def test_board_game_bgg_fields_are_optional(self):
        game = BoardGame.objects.create(
            name='Azul',
            owner=self.user,
            min_players=2,
            max_players=4,
        )
        self.assertIsNone(game.bgg_id)
        self.assertIsNone(game.bgg_last_synced)

    def test_board_game_complexity_defaults_to_null(self):
        game = BoardGame.objects.create(
            name='Chess',
            owner=self.user,
        )
        self.assertIsNone(game.complexity)

    def test_board_game_with_complexity_light(self):
        game = BoardGame.objects.create(
            name='Uno',
            owner=self.user,
            complexity='light',
        )
        self.assertEqual(game.complexity, 'light')

    def test_board_game_with_complexity_medium(self):
        game = BoardGame.objects.create(
            name='Catan',
            owner=self.user,
            complexity='medium',
        )
        self.assertEqual(game.complexity, 'medium')

    def test_board_game_with_complexity_medium_heavy(self):
        game = BoardGame.objects.create(
            name='Terraforming Mars',
            owner=self.user,
            complexity='medium_heavy',
        )
        self.assertEqual(game.complexity, 'medium_heavy')

    def test_board_game_with_complexity_heavy(self):
        game = BoardGame.objects.create(
            name='Gloomhaven',
            owner=self.user,
            complexity='heavy',
        )
        self.assertEqual(game.complexity, 'heavy')

    def test_board_game_with_complexity_unknown(self):
        game = BoardGame.objects.create(
            name='Mystery Game',
            owner=self.user,
            complexity='unknown',
        )
        self.assertEqual(game.complexity, 'unknown')

    def test_board_game_bgg_weight_defaults_to_null(self):
        game = BoardGame.objects.create(
            name='Chess',
            owner=self.user,
        )
        self.assertIsNone(game.bgg_weight)

    def test_board_game_with_bgg_weight(self):
        from decimal import Decimal
        game = BoardGame.objects.create(
            name='Catan',
            owner=self.user,
            bgg_weight=Decimal('2.28'),
        )
        self.assertEqual(game.bgg_weight, Decimal('2.28'))


@tag("unit")
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


@tag("unit")
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


@tag("unit")
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


@tag("unit")
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


@tag("unit")
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


@tag("unit")
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


@tag("unit")
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


@tag("unit")
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


@tag("unit")
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


@tag("unit")
class GameTagModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='tagowner', password='testpass123'
        )

    def test_create_game_tag_stores_name_lowercase(self):
        tag = GameTag.objects.create(name='Racing')
        self.assertEqual(tag.name, 'racing')

    def test_game_tag_string_representation(self):
        tag = GameTag.objects.create(name='Racing')
        self.assertEqual(str(tag), 'racing')

    def test_game_tag_unique_name_constraint(self):
        GameTag.objects.create(name='racing')
        with self.assertRaises(IntegrityError):
            GameTag.objects.create(name='racing')

    def test_game_tag_case_insensitive_unique(self):
        GameTag.objects.create(name='racing')
        with self.assertRaises(IntegrityError):
            GameTag.objects.create(name='RACING')

    def test_game_tag_mixed_case_unique(self):
        GameTag.objects.create(name='Racing')
        with self.assertRaises(IntegrityError):
            GameTag.objects.create(name='RACING')

    def test_game_tag_optional_created_by(self):
        tag = GameTag.objects.create(name='racing')
        self.assertIsNone(tag.created_by)

    def test_game_tag_with_created_by(self):
        tag = GameTag.objects.create(name='racing', created_by=self.user)
        self.assertEqual(tag.created_by, self.user)

    def test_game_tag_created_at_auto_set(self):
        tag = GameTag.objects.create(name='racing')
        self.assertIsNotNone(tag.created_at)

    def test_game_tag_max_length(self):
        name = 'a' * 25
        tag = GameTag.objects.create(name=name)
        self.assertEqual(len(tag.name), 25)

    def test_game_tag_ordering_by_name(self):
        GameTag.objects.create(name='ztag_zebra')
        GameTag.objects.create(name='atag_alpha')
        GameTag.objects.create(name='mtag_middle')
        tags = list(GameTag.objects.filter(name__endswith='tag_zebra') | GameTag.objects.filter(name__endswith='tag_alpha') | GameTag.objects.filter(name__endswith='tag_middle'))
        tag_names = [t.name for t in tags]
        self.assertLess(tag_names.index('atag_alpha'), tag_names.index('mtag_middle'))
        self.assertLess(tag_names.index('mtag_middle'), tag_names.index('ztag_zebra'))

    def test_seed_data_exists(self):
        self.assertTrue(GameTag.objects.filter(name='strategy').exists())
        self.assertTrue(GameTag.objects.filter(name='party').exists())
        self.assertTrue(GameTag.objects.filter(name='cooperative').exists())
        self.assertTrue(GameTag.objects.filter(name='worker placement').exists())
        self.assertTrue(GameTag.objects.filter(name='engine building').exists())
        self.assertTrue(GameTag.objects.filter(name='deck builder').exists())


@tag("unit")
class GameSessionModelTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.user = User.objects.create_user(username='user', password='pass')
        self.group = Group.objects.create(name='Session Group')
        _make_organizer(self.admin, self.group)
        self.event = Event.objects.create(
            title='Session Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.admin,
            group=self.group,
        )
        self.game = BoardGame.objects.create(name='Catan', owner=self.admin)

    def test_create_session(self):
        session = GameSession.objects.create(
            event=self.event,
            board_game=self.game,
            selection_method='manual',
            created_by=self.admin,
        )
        self.assertEqual(session.event, self.event)
        self.assertEqual(session.board_game, self.game)
        self.assertEqual(session.selection_method, 'manual')
        self.assertIsNotNone(session.played_at)

    def test_multiple_sessions_per_event(self):
        GameSession.objects.create(
            event=self.event, board_game=self.game,
            selection_method='random', created_by=self.admin,
        )
        GameSession.objects.create(
            event=self.event, board_game=self.game,
            selection_method='manual', created_by=self.admin,
        )
        self.assertEqual(GameSession.objects.filter(event=self.event).count(), 2)


@tag("unit")
class BoardGameTagTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='gameowner', password='testpass123'
        )

    def test_board_game_can_have_tags(self):
        game = BoardGame.objects.create(name='Catan', owner=self.user)
        tag1 = GameTag.objects.create(name='racing')
        tag2 = GameTag.objects.create(name='trading')
        game.tags.add(tag1, tag2)
        self.assertEqual(game.tags.count(), 2)
        self.assertIn(tag1, game.tags.all())

    def test_board_game_can_have_no_tags(self):
        game = BoardGame.objects.create(name='Chess', owner=self.user)
        self.assertEqual(game.tags.count(), 0)

    def test_board_game_tags_are_game_tags_not_event_tags(self):
        game = BoardGame.objects.create(name='Catan', owner=self.user)
        game_tag = GameTag.objects.create(name='racing')
        event_tag = EventTag.objects.create(name='tournament')
        game.tags.add(game_tag)
        self.assertIn(game_tag, game.tags.all())
        self.assertNotIn(event_tag, game.tags.all())

    def test_game_tag_reverse_relation(self):
        game = BoardGame.objects.create(name='Catan', owner=self.user)
        tag = GameTag.objects.create(name='racing')
        game.tags.add(tag)
        self.assertIn(game, tag.tagged_games.all())

    def test_filter_games_by_tag(self):
        game1 = BoardGame.objects.create(name='Catan', owner=self.user)
        game2 = BoardGame.objects.create(name='Uno', owner=self.user)
        tag = GameTag.objects.create(name='racing')
        game1.tags.add(tag)
        strategy_games = BoardGame.objects.filter(tags=tag)
        self.assertIn(game1, strategy_games)
        self.assertNotIn(game2, strategy_games)


@tag("unit")
class ParseBggLinkTest(TestCase):

    def test_parse_full_url_extracts_id(self):
        from club.utils import parse_bgg_link
        result = parse_bgg_link('https://boardgamegeek.com/boardgame/13/catan')
        self.assertEqual(result, {'bgg_id': 13, 'bgg_link': 'https://boardgamegeek.com/boardgame/13/catan'})

    def test_parse_url_without_slug(self):
        from club.utils import parse_bgg_link
        result = parse_bgg_link('https://boardgamegeek.com/boardgame/13')
        self.assertEqual(result, {'bgg_id': 13, 'bgg_link': 'https://boardgamegeek.com/boardgame/13'})

    def test_parse_url_with_http(self):
        from club.utils import parse_bgg_link
        result = parse_bgg_link('http://boardgamegeek.com/boardgame/13/catan')
        self.assertEqual(result, {'bgg_id': 13, 'bgg_link': 'http://boardgamegeek.com/boardgame/13/catan'})

    def test_parse_url_without_scheme(self):
        from club.utils import parse_bgg_link
        result = parse_bgg_link('boardgamegeek.com/boardgame/13/catan')
        self.assertEqual(result, {'bgg_id': 13, 'bgg_link': 'https://boardgamegeek.com/boardgame/13/catan'})

    def test_parse_expansion_url(self):
        from club.utils import parse_bgg_link
        result = parse_bgg_link('https://boardgamegeek.com/boardgameexpansion/1234/some-expansion')
        self.assertEqual(result, {'bgg_id': 1234, 'bgg_link': 'https://boardgamegeek.com/boardgameexpansion/1234/some-expansion'})

    def test_parse_raw_id(self):
        from club.utils import parse_bgg_link
        result = parse_bgg_link('13')
        self.assertEqual(result, {'bgg_id': 13, 'bgg_link': 'https://boardgamegeek.com/boardgame/13/'})

    def test_parse_empty_string_returns_none(self):
        from club.utils import parse_bgg_link
        result = parse_bgg_link('')
        self.assertIsNone(result)

    def test_parse_whitespace_returns_none(self):
        from club.utils import parse_bgg_link
        result = parse_bgg_link('   ')
        self.assertIsNone(result)

    def test_parse_non_bgg_url_returns_none(self):
        from club.utils import parse_bgg_link
        result = parse_bgg_link('https://example.com/something')
        self.assertIsNone(result)

    def test_parse_invalid_string_returns_none(self):
        from club.utils import parse_bgg_link
        result = parse_bgg_link('not a url or id')
        self.assertIsNone(result)

    def test_parse_url_with_trailing_slash(self):
        from club.utils import parse_bgg_link
        result = parse_bgg_link('https://boardgamegeek.com/boardgame/13/')
        self.assertEqual(result, {'bgg_id': 13, 'bgg_link': 'https://boardgamegeek.com/boardgame/13/'})

    def test_parse_url_with_www(self):
        from club.utils import parse_bgg_link
        result = parse_bgg_link('https://www.boardgamegeek.com/boardgame/13/catan')
        self.assertEqual(result, {'bgg_id': 13, 'bgg_link': 'https://www.boardgamegeek.com/boardgame/13/catan'})


@tag("unit")
class GameSessionPlayerModelTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='pass')
        self.user = User.objects.create_user(username='user', password='pass')
        self.group = Group.objects.create(name='Player Group')
        from club.models import GroupMembership
        GroupMembership.objects.create(user=self.admin, group=self.group, role='admin')
        self.event = Event.objects.create(
            title='Player Event',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.admin,
            group=self.group,
        )
        self.game = BoardGame.objects.create(name='Catan', owner=self.admin)
        self.session = GameSession.objects.create(
            event=self.event, board_game=self.game,
            selection_method='manual', created_by=self.admin,
        )

    def test_add_registered_player(self):
        player = GameSessionPlayer.objects.create(
            game_session=self.session, user=self.user,
        )
        self.assertEqual(player.user, self.user)
        self.assertEqual(player.guest_name, '')

    def test_add_guest_player(self):
        player = GameSessionPlayer.objects.create(
            game_session=self.session, guest_name='Guest1',
        )
        self.assertIsNone(player.user_id)
        self.assertEqual(player.guest_name, 'Guest1')

    def test_clean_validates_exactly_one_of_user_or_guest(self):
        from django.core.exceptions import ValidationError
        player = GameSessionPlayer(
            game_session=self.session,
            user=self.user,
            guest_name='Guest1',
        )
        with self.assertRaises(ValidationError):
            player.clean()

    def test_clean_validates_neither_user_nor_guest(self):
        from django.core.exceptions import ValidationError
        player = GameSessionPlayer(
            game_session=self.session,
        )
        with self.assertRaises(ValidationError):
            player.clean()

    def test_unique_constraint_registered_player(self):
        GameSessionPlayer.objects.create(
            game_session=self.session, user=self.user,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            GameSessionPlayer.objects.create(
                game_session=self.session, user=self.user,
            )

    def test_guest_names_not_unique(self):
        GameSessionPlayer.objects.create(
            game_session=self.session, guest_name='Guest',
        )
        player2 = GameSessionPlayer.objects.create(
            game_session=self.session, guest_name='Guest',
        )
        self.assertIsNotNone(player2.pk)


@tag("unit")
class BoardGameGroupOwnerTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='gameowner', password='testpass123'
        )
        cls.group = Group.objects.create(name='Test Group')

    def test_create_board_game_with_group_owner(self):
        game = BoardGame.objects.create(
            name='Group Catan', group=self.group,
            min_players=3, max_players=4, complexity='medium',
        )
        self.assertEqual(game.name, 'Group Catan')
        self.assertEqual(game.group, self.group)
        self.assertIsNone(game.owner)

    def test_create_board_game_with_user_owner(self):
        game = BoardGame.objects.create(
            name='User Chess', owner=self.user,
            min_players=3, max_players=4,
        )
        self.assertEqual(game.owner, self.user)
        self.assertIsNone(game.group)

    def test_create_board_game_with_both_owner_and_group_is_not_preferred(self):
        game = BoardGame.objects.create(
            name='Dual Owner Game', owner=self.user, group=self.group,
        )
        self.assertEqual(game.owner, self.user)
        self.assertEqual(game.group, self.group)

    def test_create_board_game_with_neither_owner_nor_group_possible(self):
        game = BoardGame.objects.create(name='Orphan Game')
        self.assertIsNone(game.owner)
        self.assertIsNone(game.group)

    def test_group_owned_game_cascade_on_group_delete(self):
        game = BoardGame.objects.create(name='Doomed Game', group=self.group)
        self.group.delete()
        self.assertFalse(BoardGame.objects.filter(pk=game.pk).exists())

    def test_user_owned_game_unaffected_by_unrelated_group_delete(self):
        other_group = Group.objects.create(name='Other Group')
        game = BoardGame.objects.create(name='Safe Game', owner=self.user)
        other_group.delete()
        self.assertTrue(BoardGame.objects.filter(pk=game.pk).exists())

    def test_group_owned_game_bgg_fields(self):
        game = BoardGame.objects.create(
            name='BGG Group Game', group=self.group,
            bgg_id=42, bgg_link='https://boardgamegeek.com/boardgame/42/test',
        )
        self.assertEqual(game.bgg_id, 42)
        self.assertEqual(game.bgg_link, 'https://boardgamegeek.com/boardgame/42/test')

    def test_group_owned_game_complexity(self):
        game = BoardGame.objects.create(
            name='Complex Group Game', group=self.group, complexity='heavy',
        )
        self.assertEqual(game.complexity, 'heavy')

    def test_group_owned_game_string_representation(self):
        game = BoardGame.objects.create(name='Group Chess', group=self.group)
        self.assertEqual(str(game), 'Group Chess')
