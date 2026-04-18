from django.contrib.auth.models import AbstractUser, UserManager
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


class ClubUserManager(UserManager):

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_organizer', True)
        extra_fields.setdefault('is_site_admin', True)
        return super().create_superuser(username, email, password, **extra_fields)


class VerifiedIcon(models.Model):
    name = models.CharField(max_length=100)
    image = models.FileField(upload_to='verified_icons/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class User(AbstractUser):
    objects = ClubUserManager()

    username = models.CharField(
        max_length=150,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^[a-zA-Z][a-zA-Z0-9_.\-]{2,}[a-zA-Z0-9]\Z',
                message='Username must be at least 4 characters and contain only letters, numbers, underscores, periods, and dashes. It must start with a letter and end with a letter or number.',
            ),
        ],
        error_messages={
            'unique': 'A user with that username already exists.',
        },
    )

    is_organizer = models.BooleanField(default=False)
    is_site_admin = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    timezone = models.CharField(max_length=63, default='UTC')
    timezone_detected = models.BooleanField(default=False)
    verified_icon = models.ForeignKey(
        VerifiedIcon, on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    profile_picture = models.ImageField(
        upload_to='profile_pictures/', blank=True,
    )
    bio = models.TextField(blank=True, max_length=500)
    show_games = models.BooleanField(default=True)
    show_events = models.BooleanField(default=True)
    show_date_joined = models.BooleanField(default=True)
    must_change_password = models.BooleanField(default=False)

    def __str__(self):
        return self.username


class BoardGame(models.Model):
    COMPLEXITY_CHOICES = [
        ('light', 'Light'),
        ('medium', 'Medium'),
        ('medium_heavy', 'Medium Heavy'),
        ('heavy', 'Heavy'),
        ('unknown', 'Unknown'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    min_players = models.PositiveIntegerField(null=True, blank=True)
    max_players = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    bgg_id = models.PositiveIntegerField(null=True, blank=True)
    bgg_link = models.URLField(blank=True)
    image_url = models.URLField(blank=True)
    bgg_last_synced = models.DateTimeField(null=True, blank=True)
    complexity = models.CharField(
        max_length=15,
        choices=COMPLEXITY_CHOICES,
        null=True, blank=True,
    )
    bgg_weight = models.DecimalField(
        max_digits=3, decimal_places=2,
        null=True, blank=True,
    )

    def __str__(self):
        return self.name


class Event(models.Model):
    title = models.CharField(max_length=200)
    date = models.DateTimeField()
    location = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    show_individual_votes = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    voting_open = models.BooleanField(default=True)
    voting_deadline = models.DateTimeField()

    def __str__(self):
        return self.title

    @property
    def phase(self):
        return 'upcoming' if self.date > timezone.now() else 'completed'

    @property
    def is_currently_active(self):
        return self.is_active and self.date > timezone.now()

    @property
    def is_voting_open(self):
        if not self.is_active:
            return False
        if not self.voting_open:
            return False
        if timezone.now() >= self.voting_deadline:
            return False
        return True

    def sync_voting_status(self):
        if self.voting_open and not self.is_voting_open:
            self.voting_open = False
            self.save(update_fields=['voting_open'])


class EventAttendance(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'event'], name='unique_attendance'),
        ]

    def __str__(self):
        return f'{self.user} attending {self.event}'


class Vote(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    board_game = models.ForeignKey(BoardGame, on_delete=models.CASCADE)
    rank = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'event', 'rank'],
                name='unique_rank_per_user_event',
            ),
            models.UniqueConstraint(
                fields=['user', 'event', 'board_game'],
                name='unique_game_per_user_event',
            ),
        ]

    def __str__(self):
        return f'{self.user} ranked {self.board_game} #{self.rank} at {self.event}'


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    url = models.URLField(blank=True)
    url_label = models.CharField(max_length=100, blank=True)
    is_read = models.BooleanField(default=False)
    notification_type = models.CharField(max_length=50, default='general')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at'], name='notif_user_read_created'),
        ]

    def __str__(self):
        return f'Notification for {self.user}: {self.message[:50]}'
