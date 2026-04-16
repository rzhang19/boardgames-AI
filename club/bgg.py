import json
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BGG_API_BASE = 'https://api.geekdo.com/api/geekitems'
BGG_XML_API_BASE = 'https://boardgamegeek.com/xmlapi2/thing'
MAX_SEARCH_RESULTS = 20


def _build_request(url):
    return Request(url, headers={'User-Agent': 'BoardGameClub/1.0'})


def _make_request(url):
    req = _build_request(url)
    with urlopen(req) as response:
        return json.loads(response.read())


def _safe_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def search_bgg(query):
    try:
        params = urlencode({
            'objecttype': 'thing',
            'subtype': 'boardgame',
            'search': query,
        })
        url = f'{BGG_API_BASE}?{params}'
        data = _make_request(url)

        items = data.get('items', [])
        results = []
        for item in items[:MAX_SEARCH_RESULTS]:
            results.append({
                'id': int(item['objectid']),
                'name': item['name'],
            })
        return results
    except Exception:
        return []


def fetch_bgg_game(bgg_id):
    try:
        params = urlencode({
            'objecttype': 'thing',
            'objectid': bgg_id,
        })
        url = f'{BGG_API_BASE}?{params}'
        data = _make_request(url)

        item = data.get('item', {})
        if not item:
            return None

        description = item.get('short_description') or item.get('description', '')

        return {
            'bgg_id': int(item['objectid']),
            'name': item.get('name', ''),
            'description': description,
            'min_players': _safe_int(item.get('minplayers')),
            'max_players': _safe_int(item.get('maxplayers')),
            'bgg_link': item.get('canonical_link', ''),
            'image_url': item.get('imageurl'),
        }
    except Exception:
        return None


def fetch_bgg_weight(bgg_id):
    try:
        url = f'{BGG_XML_API_BASE}?id={bgg_id}&stats=1'
        req = _build_request(url)
        with urlopen(req) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        item = root.find('item')
        if item is None:
            return None

        weight_elem = item.find('.//averageweight')
        if weight_elem is None:
            return None

        value = weight_elem.get('value', '0')
        weight = Decimal(value)
        if weight == 0:
            return None
        return weight
    except Exception:
        return None


def weight_to_complexity(weight):
    if weight is None:
        return None
    if weight < Decimal('2.0'):
        return 'light'
    elif weight < Decimal('3.0'):
        return 'medium'
    elif weight < Decimal('4.0'):
        return 'medium_heavy'
    else:
        return 'heavy'
