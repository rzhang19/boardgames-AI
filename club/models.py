from django.contrib.auth.models import AbstractUser, UserManager
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify
from uuid import uuid4


class ClubUserManager(UserManager):

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_site_admin', True)
        return super().create_superuser(username, email, password, **extra_fields)


class VerifiedIcon(models.Model):
    name = models.CharField(max_length=100)
    image = models.FileField(upload_to='verified_icons/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class SiteSettings(models.Model):
    default_voting_offset_minutes = models.IntegerField(default=0)
    allow_site_admins_to_delete_groups = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        return cls.objects.get_or_create(pk=1, defaults={'default_voting_offset_minutes': 0})[0]


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
    group_creation_override = models.PositiveIntegerField(default=0)
    is_view_only = models.BooleanField(default=False)

    def __str__(self):
        return self.username


class Group(models.Model):
    JOIN_POLICY_CHOICES = [
        ('open', 'Open'),
        ('request', 'Request Approval'),
        ('invite_only', 'Invite Only'),
    ]

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='group_images/', blank=True)
    discoverable = models.BooleanField(default=True)
    join_policy = models.CharField(
        max_length=20,
        choices=JOIN_POLICY_CHOICES,
        default='open',
    )
    max_members = models.PositiveIntegerField(default=50)
    disbanded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_groups',
    )

    def __str__(self):
        return self.name

    @property
    def is_disbanded(self):
        return self.disbanded_at is not None

    @property
    def is_grace_period_expired(self):
        if self.disbanded_at is None:
            return False
        return self.disbanded_at + timezone.timedelta(days=30) <= timezone.now()

    def member_count(self):
        return self.membership.count()

    def is_member(self, user):
        if not user.is_authenticated:
            return False
        return GroupMembership.objects.filter(user=user, group=self).exists()

    def is_admin(self, user):
        if not user.is_authenticated:
            return False
        return GroupMembership.objects.filter(
            user=user, group=self, role='admin',
        ).exists()

    def visible_to(self, user):
        if not user.is_authenticated:
            return self.discoverable
        return (
            self.discoverable
            or self.is_member(user)
            or user.is_superuser
            or user.is_site_admin
        )

    def games(self):
        return BoardGame.objects.filter(
            Q(owner__membership__group=self,
              owner__membership__role__in=['admin', 'organizer', 'member'])
            | Q(group=self)
        )

    def can_change_max_members(self, user):
        return user.is_superuser


@receiver(pre_save, sender=Group)
def group_generate_slug(sender, instance, **kwargs):
    if instance.slug:
        return
    base_slug = slugify(instance.name)
    if not base_slug:
        base_slug = 'group'
    slug = base_slug
    counter = 2
    while Group.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
        slug = f'{base_slug}-{counter}'
        counter += 1
    instance.slug = slug


class GroupMembership(models.Model):
    ROLE_CHOICES = [
        ('member', 'Member'),
        ('organizer', 'Organizer'),
        ('admin', 'Admin'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='membership',
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='membership',
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='member',
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    is_favorite = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'group'],
                name='unique_group_membership',
            ),
        ]

    def __str__(self):
        return f'{self.user} - {self.group} ({self.role})'


class GroupInvite(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    token = models.CharField(max_length=64, unique=True, default=uuid4)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    def is_valid(self):
        if self.used:
            return False
        if timezone.now() >= self.expires_at:
            return False
        return True

    def use(self, user):
        if self.used:
            raise ValueError('Invite has already been used.')
        if timezone.now() >= self.expires_at:
            raise ValueError('Invite has expired.')
        if self.group.membership.count() >= self.group.max_members:
            raise ValueError('Group has reached its maximum number of members.')
        if GroupMembership.objects.filter(user=user, group=self.group).exists():
            raise ValueError('User is already a member of this group.')
        self.used = True
        self.save(update_fields=['used'])
        return GroupMembership.objects.create(
            user=user,
            group=self.group,
            role='member',
        )

    def __str__(self):
        return f'Invite to {self.group} (expires {self.expires_at})'


class GroupJoinRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'group'],
                name='unique_join_request',
            ),
        ]

    @property
    def is_valid(self):
        return self.status == 'pending' and timezone.now() < self.expires_at

    def approve(self):
        if self.status != 'pending':
            raise ValueError('Request is not pending.')
        if timezone.now() >= self.expires_at:
            raise ValueError('Request has expired.')
        if self.group.membership.count() >= self.group.max_members:
            raise ValueError('Group has reached its maximum number of members.')
        if GroupMembership.objects.filter(user=self.user, group=self.group).exists():
            raise ValueError('User is already a member of this group.')
        self.status = 'approved'
        self.save(update_fields=['status'])
        return GroupMembership.objects.create(
            user=self.user,
            group=self.group,
            role='member',
        )

    def reject(self):
        self.status = 'rejected'
        self.save(update_fields=['status'])

    def __str__(self):
        return f'{self.user} requests to join {self.group} ({self.status})'


class GroupCreationLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    group = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
    )

    def __str__(self):
        return f'{self.user} created a group at {self.created_at}'


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
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True,
    )
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, null=True, blank=True,
        related_name='owned_games',
    )
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
    PRIVACY_CHOICES = [
        ('private', 'Private'),
        ('invite_only_public', 'Invite Only - Public'),
        ('public', 'Public'),
    ]

    INVITE_OTHERS_CHOICES = [
        ('nobody', 'Nobody'),
        ('friends_only', 'Friends Only'),
        ('anyone', 'Anyone'),
    ]

    title = models.CharField(max_length=200)
    date = models.DateTimeField()
    location = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        null=True, blank=True,
    )
    show_individual_votes = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    voting_open = models.BooleanField(default=True)
    voting_deadline = models.DateTimeField()
    voting_deadline_offset_minutes = models.IntegerField(default=0)
    privacy = models.CharField(
        max_length=20,
        choices=PRIVACY_CHOICES,
        default='public',
    )
    show_description_publicly = models.BooleanField(default=True)
    show_location_publicly = models.BooleanField(default=True)
    show_datetime_publicly = models.BooleanField(default=True)
    show_attendees_publicly = models.BooleanField(default=True)
    allow_invite_others = models.CharField(
        max_length=15,
        choices=INVITE_OTHERS_CHOICES,
        default='nobody',
    )
    auto_add_games = models.BooleanField(default=False)
    additional_organizers = models.ManyToManyField(
        User,
        blank=True,
        related_name='co_organized_events',
    )
    organizers_can_edit_title = models.BooleanField(default=True)
    organizers_can_edit_description = models.BooleanField(default=True)
    organizers_can_edit_datetime = models.BooleanField(default=True)

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

    def is_organizer(self, user):
        if not user.is_authenticated:
            return False
        if self.created_by == user:
            return True
        return self.additional_organizers.filter(pk=user.pk).exists()

    def sync_voting_status(self):
        if self.voting_open and not self.is_voting_open:
            self.voting_open = False
            self.save(update_fields=['voting_open'])

    def get_game_pool(self):
        if self.group_id is not None:
            return self.group.games()

        organizer_ids = [self.created_by_id]
        if self.additional_organizers.exists():
            organizer_ids.extend(
                self.additional_organizers.values_list('pk', flat=True)
            )

        attendee_ids = list(
            EventAttendance.objects.filter(event=self)
            .values_list('user_id', flat=True)
        )

        relevant_user_ids = list(set(organizer_ids + attendee_ids))

        attendee_group_ids = list(
            GroupMembership.objects.filter(
                user_id__in=relevant_user_ids,
                role__in=['admin', 'organizer', 'member'],
            ).values_list('group_id', flat=True)
        )

        return BoardGame.objects.filter(
            Q(owner_id__in=relevant_user_ids)
            | Q(group_id__in=attendee_group_ids)
        ).distinct()


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


class EventInvite(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='invites')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='event_invites')
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'user'],
                name='unique_event_invite',
            ),
        ]

    def __str__(self):
        return f'{self.user} invited to {self.event} ({self.status})'

    @property
    def is_expired(self):
        return timezone.now() >= self.event.date

    def accept(self):
        if self.status == 'accepted':
            return
        if self.status != 'pending':
            raise ValueError('Invite is not pending.')
        self.status = 'accepted'
        self.save(update_fields=['status'])
        EventAttendance.objects.get_or_create(
            user=self.user, event=self.event,
        )

    def decline(self):
        if self.status != 'pending':
            raise ValueError('Invite is not pending.')
        self.status = 'declined'
        self.save(update_fields=['status'])


class PrivateEventCreationLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    event = models.ForeignKey(
        Event,
        on_delete=models.SET_NULL,
        null=True, blank=True,
    )

    def __str__(self):
        return f'{self.user} created a private event at {self.created_at}'


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


class PasswordHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_history')
    password = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Password history for {self.user}'


class Friendship(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]

    requester = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='sent_friendships',
    )
    receiver = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='received_friendships',
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending',
    )
    decline_count = models.PositiveIntegerField(default=0)
    last_declined_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['requester', 'receiver'],
                name='unique_friendship',
            ),
        ]

    def __str__(self):
        return f'{self.requester} -> {self.receiver} ({self.status})'

    @staticmethod
    def are_friends(user_a, user_b):
        return Friendship.objects.filter(
            status='accepted',
        ).filter(
            Q(requester=user_a, receiver=user_b)
            | Q(requester=user_b, receiver=user_a),
        ).exists()

    @staticmethod
    def get_friendship(user_a, user_b):
        return Friendship.objects.filter(
            Q(requester=user_a, receiver=user_b)
            | Q(requester=user_b, receiver=user_a),
        ).first()

    @staticmethod
    def can_send_request(requester, receiver):
        if requester == receiver:
            return False
        existing = Friendship.objects.filter(
            requester=requester, receiver=receiver,
        ).first()
        if existing is None:
            return True
        if existing.status in ('pending', 'accepted'):
            return False
        if existing.status == 'declined':
            if existing.decline_count >= 2 and existing.last_declined_at:
                elapsed = timezone.now() - existing.last_declined_at
                if elapsed < timezone.timedelta(hours=168):
                    return False
            return True
        return False

    @staticmethod
    def get_friends_of(user):
        accepted = Friendship.objects.filter(
            status='accepted',
        ).filter(
            Q(requester=user) | Q(receiver=user),
        )
        friend_ids = set()
        for f in accepted:
            if f.requester_id == user.pk:
                friend_ids.add(f.receiver_id)
            else:
                friend_ids.add(f.requester_id)
        return User.objects.filter(pk__in=friend_ids)
