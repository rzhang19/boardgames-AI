from django.db import migrations


GAME_TAGS = [
    'strategy',
    'party',
    'cooperative',
    'worker placement',
    'engine building',
    'deck builder',
]

EVENT_TAGS = [
    'party',
    'long form',
    'private',
]


def seed_default_tags(apps, schema_editor):
    GameTag = apps.get_model('club', 'GameTag')
    EventTag = apps.get_model('club', 'EventTag')

    for name in GAME_TAGS:
        GameTag.objects.get_or_create(name=name)

    for name in EVENT_TAGS:
        EventTag.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ('club', '0035_eventtag_event_tags_gametag_boardgame_tags_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_default_tags, migrations.RunPython.noop),
    ]
