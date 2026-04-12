import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BGG_API_BASE = 'https://api.geekdo.com/api/geekitems'
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
