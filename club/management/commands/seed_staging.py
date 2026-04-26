import os
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from club.models import (
    BoardGame,
    Event,
    EventAttendance,
    Group,
    GroupMembership,
    User,
    Vote,
)


class Command(BaseCommand):
    help = 'Seed the staging database with test data'

    TEST_USERS = [
        {'username': 'testuser', 'is_site_admin': False},
        {'username': 'testorganizer', 'is_site_admin': False},
        {'username': 'testadmin', 'is_site_admin': True},
        {'username': 'newtestadmin', 'is_site_admin': False},
        {'username': 'testsiteadmin', 'is_site_admin': True},
    ]

    GAMES = [
        {'name': 'Catan', 'description': 'Trade, build, and settle the island of Catan.', 'min_players': 3, 'max_players': 4},
        {'name': 'Ticket to Ride', 'description': 'Cross-country train adventure.', 'min_players': 2, 'max_players': 5},
        {'name': 'Pandemic', 'description': 'Cooperative game to save humanity from diseases.', 'min_players': 2, 'max_players': 4},
        {'name': 'Wingspan', 'description': 'Competitive bird-collection engine-building game.', 'min_players': 1, 'max_players': 5},
        {'name': 'Azul', 'description': 'Draft tiles to decorate the walls of the Royal Palace.', 'min_players': 2, 'max_players': 4},
    ]

    def handle(self, *args, **options):
        view_only_username = settings.VIEW_ONLY_USERNAME
        all_usernames = [u['username'] for u in self.TEST_USERS]
        if settings.VIEW_ONLY_PASSWORD:
            all_usernames.append(view_only_username)

        existing = User.objects.filter(username__in=all_usernames).count()
        if existing:
            self.stdout.write(self.style.WARNING('Test data already exists. Clearing and re-seeding...'))
            Vote.objects.filter(user__username__in=all_usernames).delete()
            EventAttendance.objects.filter(user__username__in=all_usernames).delete()
            Event.objects.filter(created_by__username__in=all_usernames).delete()
            BoardGame.objects.filter(owner__username__in=all_usernames).delete()
            GroupMembership.objects.filter(user__username__in=all_usernames).delete()
            Group.objects.filter(name='Workday Boardgames').delete()
            Group.objects.filter(name='Public Board Games Group').delete()
            User.objects.filter(username__in=all_usernames).delete()

        users = {}
        password = os.environ.get('SEED_USER_PASSWORD')
        if not password:
            self.stderr.write(self.style.ERROR(
                'SEED_USER_PASSWORD environment variable is required. '
                'Set it in your .env or .env.staging file.'
            ))
            return
        for user_data in self.TEST_USERS:
            user = User.objects.create_user(
                username=user_data['username'],
                password=password,
                is_site_admin=user_data['is_site_admin'],
                email_verified=True,
            )
            users[user_data['username']] = user
            role = 'site admin' if user_data['is_site_admin'] else 'user'
            self.stdout.write(f'  Created {user_data["username"]} ({role})')
        if settings.VIEW_ONLY_PASSWORD:
            viewer = User.objects.create_user(
                username=view_only_username,
                password=settings.VIEW_ONLY_PASSWORD,
                is_view_only=True,
                email_verified=True,
            )
            users[view_only_username] = viewer
            self.stdout.write(f'  Created {view_only_username} (view-only visitor)')
        else:
            self.stdout.write(self.style.WARNING(
                '  VIEW_ONLY_PASSWORD not set \u2014 skipping view-only user. '
                'Set it in .env to enable.'
            ))

        private_group = Group.objects.create(
            name='Workday Boardgames',
            discoverable=False,
            join_policy='invite_only',
            created_by=users['testorganizer'],
        )
        GroupMembership.objects.create(user=users['testuser'], group=private_group, role='member')
        GroupMembership.objects.create(user=users['testorganizer'], group=private_group, role='organizer')
        GroupMembership.objects.create(user=users['testadmin'], group=private_group, role='admin')
        self.stdout.write(f'  Created group: {private_group.name} (private)')

        public_group = Group.objects.create(
            name='Public Board Games Group',
            discoverable=True,
            join_policy='open',
            created_by=users['newtestadmin'],
        )
        GroupMembership.objects.create(user=users['newtestadmin'], group=public_group, role='admin')
        if view_only_username in users:
            GroupMembership.objects.create(
                user=users[view_only_username], group=public_group, role='member',
            )
            self.stdout.write(f'  {view_only_username} joined {public_group.name}')
        self.stdout.write(f'  Created group: {public_group.name} (public)')

        games = []
        for i, game_data in enumerate(self.GAMES):
            owner = users['testuser'] if i % 2 == 0 else users['testorganizer']
            game = BoardGame.objects.create(owner=owner, **game_data)
            games.append(game)
            self.stdout.write(f'  Created game: {game.name} (owned by {owner.username})')

        now = timezone.now()
        organizer = users['testorganizer']

        active_event = Event.objects.create(
            title='Friday Night Board Games',
            date=now + timedelta(days=7, hours=19),
            location='The Game Cafe, Downtown',
            description='Weekly board game night! Bring snacks.',
            created_by=organizer,
            is_active=True,
            voting_deadline=now + timedelta(days=7, hours=19),
            group=private_group,
        )
        self.stdout.write(f'  Created active event: {active_event.title}')

        past_event = Event.objects.create(
            title='Last Week\'s Game Night',
            date=now - timedelta(days=7, hours=19),
            location='Community Center',
            description='Last week\'s event.',
            created_by=organizer,
            is_active=False,
            voting_deadline=now - timedelta(days=7, hours=19),
            group=private_group,
        )
        self.stdout.write(f'  Created past event: {past_event.title}')

        for user in users.values():
            if getattr(user, 'is_view_only', False):
                continue
            EventAttendance.objects.create(user=user, event=active_event)
            self.stdout.write(f'  {user.username} RSVP\'d to {active_event.title}')

        for user in users.values():
            if getattr(user, 'is_view_only', False):
                continue
            user_games = games[:5]
            for rank, game in enumerate(user_games, start=1):
                Vote.objects.create(
                    user=user,
                    event=active_event,
                    board_game=game,
                    rank=rank,
                )
            self.stdout.write(f'  {user.username} voted for {len(user_games)} games')

        viewer_line = ''
        if view_only_username in users:
            viewer_line = (
                f'  {view_only_username} / [env var] (view-only visitor)\n'
            )
        self.stdout.write(self.style.SUCCESS(
            f'\nSeed complete! Created {len(users)} users, {len(games)} games, '
            f'2 groups, 2 events, and votes.\n'
            f'Login credentials (password from SEED_USER_PASSWORD env var):\n'
            f'  testuser (member of Workday Boardgames)\n'
            f'  testorganizer (organizer of Workday Boardgames)\n'
            f'  testadmin (site admin, admin of Workday Boardgames)\n'
            f'  newtestadmin (admin of Public Board Games Group)\n'
            f'  testsiteadmin (site admin, no group)'
        ))
