from collections import defaultdict

from .models import BoardGame, EventGameOverride, EventPresence, Group


COMPLEXITY_ORDER = {
    'unknown': 0,
    'light': 1,
    'medium': 2,
    'medium_heavy': 3,
    'heavy': 4,
}


def _simpler_complexity(c1, c2):
    if c1 is None:
        return c2
    if c2 is None:
        return c1
    if COMPLEXITY_ORDER.get(c1, 99) <= COMPLEXITY_ORDER.get(c2, 99):
        return c1
    return c2


def compute_game_pool(event):
    games = event.get_game_pool().select_related('owner', 'group')

    present_user_ids = set(
        EventPresence.objects.filter(event=event).values_list('user_id', flat=True)
    )

    overrides = {
        o.board_game_id: o.is_available
        for o in EventGameOverride.objects.filter(event=event)
    }

    bgg_groups = defaultdict(list)
    non_bgg_games = []

    for game in games:
        if game.bgg_id is not None:
            bgg_groups[game.bgg_id].append(game)
        else:
            non_bgg_games.append(game)

    pool = {}

    for bgg_id, copies in bgg_groups.items():
        key = f'bgg_{bgg_id}'
        owners = []
        for copy in copies:
            if copy.owner:
                owners.append(copy.owner.username)
            elif copy.group:
                owners.append('Group Library')
            else:
                owners.append('Unknown')

        has_present_owner = any(
            copy.owner_id in present_user_ids
            for copy in copies
            if copy.owner_id is not None
        )
        has_present_group = any(
            copy.group_id is not None
            for copy in copies
        )

        default_available = has_present_owner or has_present_group

        overridden = False
        is_available = default_available
        for copy in copies:
            if copy.pk in overrides:
                is_available = overrides[copy.pk]
                overridden = True
                break

        complexity = None
        for copy in copies:
            complexity = _simpler_complexity(complexity, copy.complexity)

        min_p = None
        max_p = None
        for copy in copies:
            if copy.min_players is not None:
                if min_p is None or copy.min_players < min_p:
                    min_p = copy.min_players
            if copy.max_players is not None:
                if max_p is None or copy.max_players > max_p:
                    max_p = copy.max_players

        pool[key] = {
            'name': copies[0].name,
            'bgg_id': bgg_id,
            'copies': copies,
            'owners': sorted(set(owners)),
            'complexity': complexity,
            'is_available': is_available,
            'overridden': overridden,
            'min_players': min_p,
            'max_players': max_p,
        }

    for game in non_bgg_games:
        key = f'pk_{game.pk}'
        owners = []
        if game.owner:
            owners.append(game.owner.username)
        elif game.group:
            owners.append('Group Library')
        else:
            owners.append('Unknown')

        if game.owner_id is not None:
            default_available = game.owner_id in present_user_ids
        elif game.group_id is not None:
            default_available = True
        else:
            default_available = False

        overridden = False
        is_available = default_available
        if game.pk in overrides:
            is_available = overrides[game.pk]
            overridden = True

        pool[key] = {
            'name': game.name,
            'bgg_id': None,
            'copies': [game],
            'owners': sorted(set(owners)),
            'complexity': game.complexity,
            'is_available': is_available,
            'overridden': overridden,
            'min_players': game.min_players,
            'max_players': game.max_players,
        }

    return pool
