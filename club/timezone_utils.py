import zoneinfo

COMMON_TIMEZONES = [
    ('US', [
        'US/Eastern',
        'US/Central',
        'US/Mountain',
        'US/Pacific',
        'US/Alaska',
        'US/Hawaii',
        'America/Puerto_Rico',
    ]),
    ('Americas', [
        'America/New_York',
        'America/Toronto',
        'America/Vancouver',
        'America/Chicago',
        'America/Denver',
        'America/Los_Angeles',
        'America/Mexico_City',
        'America/Sao_Paulo',
        'America/Buenos_Aires',
        'America/Bogota',
        'America/Lima',
        'America/Santiago',
    ]),
    ('Europe', [
        'Europe/London',
        'Europe/Paris',
        'Europe/Berlin',
        'Europe/Madrid',
        'Europe/Rome',
        'Europe/Amsterdam',
        'Europe/Brussels',
        'Europe/Zurich',
        'Europe/Vienna',
        'Europe/Stockholm',
        'Europe/Oslo',
        'Europe/Helsinki',
        'Europe/Warsaw',
        'Europe/Athens',
        'Europe/Bucharest',
        'Europe/Moscow',
        'Europe/Istanbul',
        'Europe/Lisbon',
    ]),
    ('Asia', [
        'Asia/Dubai',
        'Asia/Kolkata',
        'Asia/Bangkok',
        'Asia/Singapore',
        'Asia/Hong_Kong',
        'Asia/Shanghai',
        'Asia/Taipei',
        'Asia/Tokyo',
        'Asia/Seoul',
        'Asia/Manila',
        'Asia/Karachi',
        'Asia/Dhaka',
    ]),
    ('Australia / Pacific', [
        'Australia/Perth',
        'Australia/Adelaide',
        'Australia/Sydney',
        'Australia/Melbourne',
        'Australia/Brisbane',
        'Pacific/Auckland',
        'Pacific/Honolulu',
        'Pacific/Fiji',
    ]),
    ('Africa', [
        'Africa/Cairo',
        'Africa/Johannesburg',
        'Africa/Lagos',
        'Africa/Nairobi',
        'Africa/Casablanca',
    ]),
    ('Other', [
        'UTC',
    ]),
]


def get_timezone_choices():
    choices = []
    for group, zones in COMMON_TIMEZONES:
        for tz in zones:
            choices.append((tz, tz.replace('_', ' ')))
    return choices


def is_valid_timezone(tz_string):
    try:
        zoneinfo.ZoneInfo(tz_string)
        return True
    except (KeyError, ValueError):
        return False
