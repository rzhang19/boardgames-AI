from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from club.models import (
    BoardGame,
    Event,
    EventAttendance,
    User,
    Vote,
)


class Command(BaseCommand):
    help = 'Seed the staging database with test data'

    TEST_USERS = [
        {
            'username': 'testuser',
            'password': 'Testpass123!',
            'is_organizer': False,
            'is_site_admin': False,
        },
        {
            'username': 'testorganizer',
            'password': 'Testpass123!',
            'is_organizer': True,
            'is_site_admin': False,
        },
        {
            'username': 'testadmin',
            'password': 'Testpass123!',
            'is_organizer': False,
            'is_site_admin': True,
        },
    ]

    GAMES = [
        {'name': 'Catan', 'description': 'Trade, build, and settle the island of Catan.', 'min_players': 3, 'max_players': 4},
        {'name': 'Ticket to Ride', 'description': 'Cross-country train adventure.', 'min_players': 2, 'max_players': 5},
        {'name': 'Pandemic', 'description': 'Cooperative game to save humanity from diseases.', 'min_players': 2, 'max_players': 4},
        {'name': 'Wingspan', 'description': 'Competitive bird-collection engine-building game.', 'min_players': 1, 'max_players': 5},
        {'name': 'Azul', 'description': 'Draft tiles to decorate the walls of the Royal Palace.', 'min_players': 2, 'max_players': 4},
    ]

    def handle(self, *args, **options):
        existing = User.objects.filter(username__in=[u['username'] for u in self.TEST_USERS]).count()
        if existing:
            self.stdout.write(self.style.WARNING('Test data already exists. Clearing and re-seeding...'))
            Vote.objects.filter(user__username__in=[u['username'] for u in self.TEST_USERS]).delete()
            EventAttendance.objects.filter(user__username__in=[u['username'] for u in self.TEST_USERS]).delete()
            Event.objects.filter(created_by__username__in=[u['username'] for u in self.TEST_USERS]).delete()
            BoardGame.objects.filter(owner__username__in=[u['username'] for u in self.TEST_USERS]).delete()
            User.objects.filter(username__in=[u['username'] for u in self.TEST_USERS]).delete()

        users = {}
        for user_data in self.TEST_USERS:
            user = User.objects.create_user(
                username=user_data['username'],
                password=user_data['password'],
                is_organizer=user_data['is_organizer'],
                is_site_admin=user_data['is_site_admin'],
                email_verified=True,
            )
            users[user_data['username']] = user
            role = 'site admin' if user_data['is_site_admin'] else ('organizer' if user_data['is_organizer'] else 'user')
            self.stdout.write(f'  Created {user_data["username"]} ({role})')

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
        )
        self.stdout.write(f'  Created active event: {active_event.title}')

        past_event = Event.objects.create(
            title='Last Week\'s Game Night',
            date=now - timedelta(days=7, hours=19),
            location='Community Center',
            description='Last week\'s event.',
            created_by=organizer,
            is_active=False,
        )
        self.stdout.write(f'  Created past event: {past_event.title}')

        for user in users.values():
            EventAttendance.objects.create(user=user, event=active_event)
            self.stdout.write(f'  {user.username} RSVP\'d to {active_event.title}')

        for user in users.values():
            user_games = games[:5]
            for rank, game in enumerate(user_games, start=1):
                Vote.objects.create(
                    user=user,
                    event=active_event,
                    board_game=game,
                    rank=rank,
                )
            self.stdout.write(f'  {user.username} voted for {len(user_games)} games')

        self.stdout.write(self.style.SUCCESS(
            f'\nSeed complete! Created {len(users)} users, {len(games)} games, '
            f'2 events, and votes.\n'
            f'Login credentials:\n'
            f'  testuser / Testpass123! (regular)\n'
            f'  testorganizer / Testpass123! (organizer)\n'
            f'  testadmin / Testpass123! (site admin)'
        ))
