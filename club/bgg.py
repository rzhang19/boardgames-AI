import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BGG_API_BASE = 'https://api.geekdo.com/api/geekitems'
BGG_XML_API_BASE = 'https://boardgamegeek.com/xmlapi2/thing'
MAX_SEARCH_RESULTS = 20
API_TIMEOUT = 15


def _build_request(url):
    return Request(url, headers={'User-Agent': 'BoardGameClub/1.0'})


def _make_request(url):
    req = _build_request(url)
    with urlopen(req, timeout=API_TIMEOUT) as response:
        return json.loads(response.read())


def _safe_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _raw_search(query):
    params = urlencode({
        'objecttype': 'thing',
        'subtype': 'boardgame',
        'search': query,
    })
    url = f'{BGG_API_BASE}?{params}'
    data = _make_request(url)
    return data.get('items', [])


def _fetch_year(bgg_id):
    try:
        params = urlencode({
            'objecttype': 'thing',
            'objectid': bgg_id,
        })
        url = f'{BGG_API_BASE}?{params}'
        data = _make_request(url)
        item = data.get('item', {})
        return (bgg_id, item.get('yearpublished'))
    except Exception:
        return (bgg_id, None)


def _disambiguate_duplicates(results):
    name_counts = Counter(r['name'] for r in results)
    duplicate_names = {name for name, count in name_counts.items() if count > 1}

    if not duplicate_names:
        return results

    dup_ids = [r['id'] for r in results if r['name'] in duplicate_names]
    year_map = {}
    with ThreadPoolExecutor(max_workers=min(len(dup_ids), 5)) as executor:
        futures = {executor.submit(_fetch_year, bid): bid for bid in dup_ids}
        for future in as_completed(futures):
            bid, year = future.result()
            year_map[bid] = year

    for result in results:
        if result['name'] in duplicate_names:
            year = year_map.get(result['id'])
            if year:
                result['name'] = f"{result['name']} ({year})"
            else:
                result['name'] = f"{result['name']} (BGG: {result['id']})"

    return results


def _clean_name(name):
    cleaned = re.sub(r"[''\u2019]", '', name)
    cleaned = re.sub(r"[:\-–—,;.!?]", ' ', cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip().lower()


def _score_item(name, query_words):
    cleaned = _clean_name(name)
    name_words = set(cleaned.split())
    matched = sum(1 for w in query_words if w.lower() in name_words)
    return matched / len(query_words) if query_words else 0


def _rank_results(items, query):
    query_words = query.lower().split()
    if len(query_words) <= 1:
        return items

    scored = []
    for idx, item in enumerate(items):
        score = _score_item(item['name'], query_words)
        scored.append((score, idx, item))

    scored.sort(key=lambda x: (-x[0], x[1]))

    ranked = [item for score, _, item in scored if score > 0]
    if not ranked:
        return items
    return ranked


def _parallel_search_exact_and_first(query):
    first_token = query.split()[0] if query.split() else query
    queries = [query]
    if first_token != query and len(first_token) >= 3:
        queries.append(first_token)

    exact_items = []
    broad_items = []

    with ThreadPoolExecutor(max_workers=len(queries)) as executor:
        futures = {executor.submit(_raw_search, q): q for q in queries}
        for future in as_completed(futures):
            query_used = futures[future]
            try:
                result = future.result()
            except Exception:
                result = []
            if query_used == query:
                exact_items = result
            else:
                broad_items = result

    if exact_items:
        return exact_items
    return broad_items


def search_bgg(query):
    try:
        items = _parallel_search_exact_and_first(query)

        if not items:
            return []

        items = _rank_results(items, query)

        results = []
        for item in items[:MAX_SEARCH_RESULTS]:
            results.append({
                'id': int(item['objectid']),
                'name': item['name'],
            })

        results = _disambiguate_duplicates(results)
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
