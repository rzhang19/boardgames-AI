import io
import re
from urllib.parse import urlparse

from PIL import Image


MAX_PROFILE_SIZE = 300
MAX_GROUP_IMAGE_SIZE = 600
MAX_FILE_SIZE = 2 * 1024 * 1024

BGG_URL_PATTERN = re.compile(
    r'^/(?:boardgame|boardgameexpansion)/(\d+)'
)


def parse_bgg_link(value):
    value = value.strip()
    if not value:
        return None

    try:
        bgg_id = int(value)
        return {
            'bgg_id': bgg_id,
            'bgg_link': f'https://boardgamegeek.com/boardgame/{bgg_id}/',
        }
    except (ValueError, TypeError):
        pass

    url = value
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    host = parsed.hostname or ''
    if 'boardgamegeek.com' not in host:
        return None

    match = BGG_URL_PATTERN.match(parsed.path)
    if not match:
        return None

    bgg_id = int(match.group(1))
    return {
        'bgg_id': bgg_id,
        'bgg_link': url,
    }


def resize_profile_picture(image_field):
    return _resize_image(image_field, MAX_PROFILE_SIZE)


def resize_group_image(image_field):
    return _resize_image(image_field, MAX_GROUP_IMAGE_SIZE)


def _resize_image(image_field, max_size):
    img = Image.open(image_field)
    img = img.convert('RGB')
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=85)
    buffer.seek(0)
    return buffer


def validate_image_size(file):
    if file.size > MAX_FILE_SIZE:
        return False
    return True
