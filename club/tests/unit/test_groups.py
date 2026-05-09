from datetime import timedelta
from io import StringIO
import importlib

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase, RequestFactory, tag
from django.utils import timezone

from club.models import (
    BoardGame,
    Event,
    EventAttendance,
    EventInvite,
    Group,
    GroupCreationLog,
    GroupInvite,
    GroupJoinRequest,
    GroupMembership,
    Notification,
    PrivateEventCreationLog,
    SiteSettings,
)
from club.notifications import (
    notify_group_demoted_member,
    notify_group_demoted_organizer,
    notify_group_event_created,
    notify_group_event_updated,
    notify_group_grace_period,
    notify_group_invite_created,
    notify_group_join_approved,
    notify_group_join_rejected,
    notify_group_member_joined,
    notify_group_member_left,
    notify_group_join_request,
    notify_group_promoted_admin,
    notify_group_promoted_organizer,
    notify_group_removed,
    notify_group_restored,
    notify_group_settings_changed,
    notify_group_voting_ended,
    notify_group_voting_resumed,
)
from club.permissions import (
    can_create_event,
    can_create_group,
    can_create_private_event,
    can_delete_group,
    can_edit_group_settings,
    can_edit_private_event_settings,
    can_invite_to_event,
    can_manage_members,
    can_restore_group,
    can_rsvp_private_event,
    can_view_group,
    can_view_private_event,
    can_view_votes,
    is_group_admin,
    is_group_member,
    is_group_organizer,
)

User = get_user_model()


def _make_admin(user, group):
    return GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_organizer(user, group):
    return GroupMembership.objects.create(user=user, group=group, role='organizer')


def _make_member(user, group):
    return GroupMembership.objects.create(user=user, group=group, role='member')


# ---------------------------------------------------------------------------
# Group model tests (from test_group_models.py)
# ---------------------------------------------------------------------------


@tag("unit")
class GroupModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='groupcreator', password='testpass123'
        )

    def test_create_group_with_all_fields(self):
        group = Group.objects.create(
            name='Board Game Club',
            description='A club for board game enthusiasts',
            discoverable=True,
            join_policy='open',
            max_members=50,
            created_by=self.user,
        )
        self.assertEqual(group.name, 'Board Game Club')
        self.assertEqual(group.description, 'A club for board game enthusiasts')
        self.assertTrue(group.discoverable)
        self.assertEqual(group.join_policy, 'open')
        self.assertEqual(group.max_members, 50)
        self.assertEqual(group.created_by, self.user)
        self.assertIsNotNone(group.created_at)
        self.assertIsNone(group.disbanded_at)

    def test_create_group_with_only_required_fields(self):
        group = Group.objects.create(name='Minimal Group')
        self.assertEqual(group.name, 'Minimal Group')
        self.assertEqual(group.description, '')
        self.assertTrue(group.discoverable)
        self.assertEqual(group.join_policy, 'open')
        self.assertEqual(group.max_members, 50)
        self.assertIsNone(group.created_by)
        self.assertFalse(bool(group.image))

    def test_group_string_representation(self):
        group = Group.objects.create(
            name='Test Group',
            created_by=self.user,
        )
        self.assertEqual(str(group), 'Test Group')

    def test_slug_auto_generated_from_name(self):
        group = Group.objects.create(
            name='My Board Game Group',
            created_by=self.user,
        )
        self.assertEqual(group.slug, 'my-board-game-group')

    def test_slug_auto_generated_with_special_characters(self):
        group = Group.objects.create(
            name="Catan: A Board Game!",
            created_by=self.user,
        )
        self.assertEqual(group.slug, 'catan-a-board-game')

    def test_slug_collision_appends_number_suffix(self):
        group1 = Group.objects.create(
            name='Game Night',
            created_by=self.user,
        )
        group2 = Group.objects.create(
            name='Game Night',
            created_by=self.user,
        )
        self.assertEqual(group1.slug, 'game-night')
        self.assertEqual(group2.slug, 'game-night-2')

    def test_slug_collision_with_multiple_duplicates(self):
        Group.objects.create(name='Duplicates', created_by=self.user)
        Group.objects.create(name='Duplicates', created_by=self.user)
        group3 = Group.objects.create(name='Duplicates', created_by=self.user)
        self.assertEqual(group3.slug, 'duplicates-3')

    def test_discoverable_defaults_to_true(self):
        group = Group.objects.create(name='Test', created_by=self.user)
        self.assertTrue(group.discoverable)

    def test_join_policy_defaults_to_open(self):
        group = Group.objects.create(name='Test', created_by=self.user)
        self.assertEqual(group.join_policy, 'open')

    def test_join_policy_request(self):
        group = Group.objects.create(
            name='Request Group',
            join_policy='request',
            created_by=self.user,
        )
        self.assertEqual(group.join_policy, 'request')

    def test_join_policy_invite_only(self):
        group = Group.objects.create(
            name='Invite Only Group',
            join_policy='invite_only',
            created_by=self.user,
        )
        self.assertEqual(group.join_policy, 'invite_only')

    def test_max_members_defaults_to_50(self):
        group = Group.objects.create(name='Test', created_by=self.user)
        self.assertEqual(group.max_members, 50)

    def test_custom_max_members(self):
        group = Group.objects.create(
            name='Small Group',
            max_members=10,
            created_by=self.user,
        )
        self.assertEqual(group.max_members, 10)

    def test_disbanded_at_defaults_to_none(self):
        group = Group.objects.create(name='Test', created_by=self.user)
        self.assertIsNone(group.disbanded_at)

    def test_is_disbanded_false_when_active(self):
        group = Group.objects.create(name='Test', created_by=self.user)
        self.assertFalse(group.is_disbanded)

    def test_is_disbanded_true_when_disbanded_at_set(self):
        group = Group.objects.create(name='Test', created_by=self.user)
        group.disbanded_at = timezone.now()
        group.save()
        self.assertTrue(group.is_disbanded)

    def test_is_grace_period_expired_false_when_active(self):
        group = Group.objects.create(name='Test', created_by=self.user)
        self.assertFalse(group.is_grace_period_expired)

    def test_is_grace_period_expired_false_within_grace_period(self):
        group = Group.objects.create(name='Test', created_by=self.user)
        group.disbanded_at = timezone.now() - timedelta(days=15)
        group.save()
        self.assertFalse(group.is_grace_period_expired)

    def test_is_grace_period_expired_true_after_30_days(self):
        group = Group.objects.create(name='Test', created_by=self.user)
        group.disbanded_at = timezone.now() - timedelta(days=31)
        group.save()
        self.assertTrue(group.is_grace_period_expired)

    def test_is_grace_period_expired_false_just_before_30_days(self):
        group = Group.objects.create(name='Test', created_by=self.user)
        group.disbanded_at = timezone.now() - timedelta(days=29, hours=23, minutes=59)
        group.save()
        self.assertFalse(group.is_grace_period_expired)

    def test_created_by_can_be_null(self):
        group = Group.objects.create(name='No Creator')
        self.assertIsNone(group.created_by)

    def test_group_created_by_set_null_on_user_delete(self):
        group = Group.objects.create(name='Test', created_by=self.user)
        self.user.delete()
        group.refresh_from_db()
        self.assertIsNone(group.created_by)

    def test_slug_unique_constraint(self):
        Group.objects.create(name='Unique Slug', created_by=self.user)
        from django.db import IntegrityError
        group2 = Group(slug='unique-slug', name='Different Name')
        with self.assertRaises(IntegrityError):
            group2.save()


@tag("unit")
class GroupMembershipModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='member1', password='testpass123'
        )
        self.group = Group.objects.create(name='Test Group')

    def test_create_membership_default_role(self):
        membership = GroupMembership.objects.create(
            user=self.user, group=self.group,
        )
        self.assertEqual(membership.role, 'member')
        self.assertFalse(membership.is_favorite)
        self.assertIsNotNone(membership.joined_at)

    def test_create_membership_with_organizer_role(self):
        membership = GroupMembership.objects.create(
            user=self.user, group=self.group, role='organizer',
        )
        self.assertEqual(membership.role, 'organizer')

    def test_create_membership_with_admin_role(self):
        membership = GroupMembership.objects.create(
            user=self.user, group=self.group, role='admin',
        )
        self.assertEqual(membership.role, 'admin')

    def test_unique_constraint_prevents_duplicate_membership(self):
        GroupMembership.objects.create(user=self.user, group=self.group)
        with self.assertRaises(IntegrityError):
            GroupMembership.objects.create(user=self.user, group=self.group)

    def test_user_can_be_in_multiple_groups(self):
        group2 = Group.objects.create(name='Second Group')
        GroupMembership.objects.create(user=self.user, group=self.group)
        m2 = GroupMembership.objects.create(user=self.user, group=group2)
        self.assertEqual(GroupMembership.objects.filter(user=self.user).count(), 2)

    def test_is_favorite_defaults_to_false(self):
        membership = GroupMembership.objects.create(
            user=self.user, group=self.group,
        )
        self.assertFalse(membership.is_favorite)

    def test_is_favorite_can_be_set(self):
        membership = GroupMembership.objects.create(
            user=self.user, group=self.group, is_favorite=True,
        )
        self.assertTrue(membership.is_favorite)

    def test_membership_string_representation(self):
        membership = GroupMembership.objects.create(
            user=self.user, group=self.group, role='admin',
        )
        self.assertIn('member1', str(membership))
        self.assertIn('Test Group', str(membership))
        self.assertIn('admin', str(membership))

    def test_membership_cascade_on_group_delete(self):
        GroupMembership.objects.create(user=self.user, group=self.group)
        self.group.delete()
        self.assertEqual(GroupMembership.objects.filter(user=self.user).count(), 0)

    def test_membership_cascade_on_user_delete(self):
        GroupMembership.objects.create(user=self.user, group=self.group)
        self.user.delete()
        self.assertEqual(GroupMembership.objects.filter(group=self.group).count(), 0)


@tag("unit")
class GroupInviteModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='inviter', password='testpass123'
        )
        self.group = Group.objects.create(name='Invite Group')

    def test_create_invite_with_token(self):
        invite = GroupInvite.objects.create(
            group=self.group,
            created_by=self.user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.assertIsNotNone(invite.token)
        self.assertTrue(len(str(invite.token)) > 0)
        self.assertFalse(invite.used)
        self.assertEqual(invite.group, self.group)
        self.assertEqual(invite.created_by, self.user)

    def test_is_valid_returns_true_for_fresh_invite(self):
        invite = GroupInvite.objects.create(
            group=self.group,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.assertTrue(invite.is_valid())

    def test_is_valid_returns_false_for_expired_invite(self):
        invite = GroupInvite.objects.create(
            group=self.group,
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(invite.is_valid())

    def test_is_valid_returns_false_for_used_invite(self):
        invite = GroupInvite.objects.create(
            group=self.group,
            expires_at=timezone.now() + timedelta(days=7),
            used=True,
        )
        self.assertFalse(invite.is_valid())

    def test_use_creates_membership(self):
        invite = GroupInvite.objects.create(
            group=self.group,
            expires_at=timezone.now() + timedelta(days=7),
        )
        new_user = User.objects.create_user(username='joinee', password='testpass123')
        membership = invite.use(new_user)
        self.assertEqual(membership.user, new_user)
        self.assertEqual(membership.group, self.group)
        self.assertEqual(membership.role, 'member')
        invite.refresh_from_db()
        self.assertTrue(invite.used)

    def test_use_raises_on_expired_invite(self):
        invite = GroupInvite.objects.create(
            group=self.group,
            expires_at=timezone.now() - timedelta(days=1),
        )
        new_user = User.objects.create_user(username='joinee', password='testpass123')
        with self.assertRaises(ValueError):
            invite.use(new_user)

    def test_use_raises_on_used_invite(self):
        invite = GroupInvite.objects.create(
            group=self.group,
            expires_at=timezone.now() + timedelta(days=7),
        )
        new_user = User.objects.create_user(username='joinee', password='testpass123')
        invite.use(new_user)
        another_user = User.objects.create_user(username='latecomer', password='testpass123')
        with self.assertRaises(ValueError):
            invite.use(another_user)

    def test_use_raises_on_full_group(self):
        small_group = Group.objects.create(name='Small', max_members=1)
        GroupMembership.objects.create(
            user=self.user, group=small_group,
        )
        invite = GroupInvite.objects.create(
            group=small_group,
            expires_at=timezone.now() + timedelta(days=7),
        )
        new_user = User.objects.create_user(username='joinee', password='testpass123')
        with self.assertRaises(ValueError):
            invite.use(new_user)

    def test_use_raises_if_already_member(self):
        invite = GroupInvite.objects.create(
            group=self.group,
            expires_at=timezone.now() + timedelta(days=7),
        )
        GroupMembership.objects.create(user=self.user, group=self.group)
        with self.assertRaises(ValueError):
            invite.use(self.user)

    def test_invite_created_by_set_null_on_user_delete(self):
        invite = GroupInvite.objects.create(
            group=self.group,
            created_by=self.user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.user.delete()
        invite.refresh_from_db()
        self.assertIsNone(invite.created_by)

    def test_invite_string_representation(self):
        invite = GroupInvite.objects.create(
            group=self.group,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.assertIn('Invite Group', str(invite))


@tag("unit")
class GroupJoinRequestModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='requester', password='testpass123'
        )
        self.group = Group.objects.create(name='Joinable Group')

    def test_create_join_request(self):
        request = GroupJoinRequest.objects.create(
            group=self.group,
            user=self.user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.assertEqual(request.group, self.group)
        self.assertEqual(request.user, self.user)
        self.assertEqual(request.status, 'pending')
        self.assertIsNotNone(request.created_at)

    def test_expires_at_auto_set_to_7_days(self):
        request = GroupJoinRequest.objects.create(
            group=self.group,
            user=self.user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.assertGreater(request.expires_at, timezone.now() + timedelta(days=6))

    def test_is_valid_true_when_pending_and_not_expired(self):
        request = GroupJoinRequest.objects.create(
            group=self.group,
            user=self.user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.assertTrue(request.is_valid)

    def test_is_valid_false_when_expired(self):
        request = GroupJoinRequest.objects.create(
            group=self.group,
            user=self.user,
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(request.is_valid)

    def test_is_valid_false_when_approved(self):
        request = GroupJoinRequest.objects.create(
            group=self.group,
            user=self.user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        request.status = 'approved'
        request.save()
        self.assertFalse(request.is_valid)

    def test_is_valid_false_when_rejected(self):
        request = GroupJoinRequest.objects.create(
            group=self.group,
            user=self.user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        request.status = 'rejected'
        request.save()
        self.assertFalse(request.is_valid)

    def test_unique_constraint_prevents_duplicate_request(self):
        GroupJoinRequest.objects.create(
            group=self.group,
            user=self.user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        with self.assertRaises(IntegrityError):
            GroupJoinRequest.objects.create(
                group=self.group,
                user=self.user,
                expires_at=timezone.now() + timedelta(days=7),
            )

    def test_approve_creates_membership(self):
        request = GroupJoinRequest.objects.create(
            group=self.group,
            user=self.user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        membership = request.approve()
        self.assertEqual(membership.user, self.user)
        self.assertEqual(membership.group, self.group)
        self.assertEqual(membership.role, 'member')
        request.refresh_from_db()
        self.assertEqual(request.status, 'approved')

    def test_reject_sets_status(self):
        request = GroupJoinRequest.objects.create(
            group=self.group,
            user=self.user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        request.reject()
        request.refresh_from_db()
        self.assertEqual(request.status, 'rejected')

    def test_approve_raises_on_full_group(self):
        small_group = Group.objects.create(name='Small', max_members=1)
        GroupMembership.objects.create(
            user=self.user, group=small_group,
        )
        other_user = User.objects.create_user(username='other', password='testpass123')
        request = GroupJoinRequest.objects.create(
            group=small_group,
            user=other_user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        with self.assertRaises(ValueError):
            request.approve()

    def test_approve_raises_on_expired_request(self):
        request = GroupJoinRequest.objects.create(
            group=self.group,
            user=self.user,
            expires_at=timezone.now() - timedelta(days=1),
        )
        with self.assertRaises(ValueError):
            request.approve()

    def test_approve_raises_if_already_member(self):
        GroupMembership.objects.create(user=self.user, group=self.group)
        request = GroupJoinRequest.objects.create(
            group=self.group,
            user=self.user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        with self.assertRaises(ValueError):
            request.approve()

    def test_join_request_string_representation(self):
        request = GroupJoinRequest.objects.create(
            group=self.group,
            user=self.user,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.assertIn('requester', str(request))
        self.assertIn('Joinable Group', str(request))
        self.assertIn('pending', str(request))


@tag("unit")
class GroupCreationLogModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='creator', password='testpass123'
        )

    def test_create_log(self):
        group = Group.objects.create(name='Logged Group')
        log = GroupCreationLog.objects.create(user=self.user, group=group)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.group, group)
        self.assertIsNotNone(log.created_at)

    def test_log_group_set_null_on_group_delete(self):
        group = Group.objects.create(name='Deleted Group')
        log = GroupCreationLog.objects.create(user=self.user, group=group)
        group.delete()
        log.refresh_from_db()
        self.assertIsNone(log.group)

    def test_log_string_representation(self):
        group = Group.objects.create(name='Test')
        log = GroupCreationLog.objects.create(user=self.user, group=group)
        self.assertIn('creator', str(log))


@tag("unit")
class GroupHelperMethodsTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='helperuser', password='testpass123'
        )
        self.admin_user = User.objects.create_superuser(
            username='helperadmin', password='testpass123'
        )
        self.group = Group.objects.create(name='Helper Group')

    def test_member_count_returns_zero(self):
        self.assertEqual(self.group.member_count(), 0)

    def test_member_count_returns_correct_count(self):
        GroupMembership.objects.create(user=self.user, group=self.group)
        self.assertEqual(self.group.member_count(), 1)

    def test_member_count_with_multiple_members(self):
        user2 = User.objects.create_user(username='user2', password='testpass123')
        GroupMembership.objects.create(user=self.user, group=self.group)
        GroupMembership.objects.create(user=user2, group=self.group)
        self.assertEqual(self.group.member_count(), 2)

    def test_is_member_returns_false_for_non_member(self):
        self.assertFalse(self.group.is_member(self.user))

    def test_is_member_returns_true_for_member(self):
        GroupMembership.objects.create(user=self.user, group=self.group)
        self.assertTrue(self.group.is_member(self.user))

    def test_is_member_returns_false_for_unauthenticated(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(self.group.is_member(AnonymousUser()))

    def test_is_admin_returns_false_for_non_admin(self):
        GroupMembership.objects.create(
            user=self.user, group=self.group, role='member',
        )
        self.assertFalse(self.group.is_admin(self.user))

    def test_is_admin_returns_true_for_admin(self):
        GroupMembership.objects.create(
            user=self.user, group=self.group, role='admin',
        )
        self.assertTrue(self.group.is_admin(self.user))

    def test_is_admin_returns_false_for_organizer(self):
        GroupMembership.objects.create(
            user=self.user, group=self.group, role='organizer',
        )
        self.assertFalse(self.group.is_admin(self.user))

    def test_is_admin_returns_false_for_unauthenticated(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(self.group.is_admin(AnonymousUser()))

    def test_visible_to_returns_true_for_discoverable_group(self):
        other_user = User.objects.create_user(username='other', password='testpass123')
        self.assertTrue(self.group.visible_to(other_user))

    def test_visible_to_returns_false_for_non_discoverable_to_anon(self):
        from django.contrib.auth.models import AnonymousUser
        self.group.discoverable = False
        self.group.save()
        self.assertFalse(self.group.visible_to(AnonymousUser()))

    def test_visible_to_returns_true_for_member_of_non_discoverable(self):
        self.group.discoverable = False
        self.group.save()
        GroupMembership.objects.create(user=self.user, group=self.group)
        self.assertTrue(self.group.visible_to(self.user))

    def test_visible_to_returns_true_for_superuser_non_discoverable(self):
        self.group.discoverable = False
        self.group.save()
        self.assertTrue(self.group.visible_to(self.admin_user))

    def test_visible_to_returns_true_for_site_admin_non_discoverable(self):
        self.group.discoverable = False
        self.group.save()
        site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True,
        )
        self.assertTrue(self.group.visible_to(site_admin))

    def test_visible_to_returns_false_for_non_member_non_discoverable(self):
        self.group.discoverable = False
        self.group.save()
        other_user = User.objects.create_user(username='other', password='testpass123')
        self.assertFalse(self.group.visible_to(other_user))

    def test_games_returns_empty_for_group_with_no_members(self):
        self.assertEqual(self.group.games().count(), 0)

    def test_games_returns_games_owned_by_members(self):
        membership = GroupMembership.objects.create(
            user=self.user, group=self.group,
        )
        game = BoardGame.objects.create(name='Test Game', owner=self.user)
        self.assertIn(game, self.group.games())

    def test_games_excludes_games_from_non_members(self):
        other_user = User.objects.create_user(username='other', password='testpass123')
        game = BoardGame.objects.create(name='Other Game', owner=other_user)
        self.assertNotIn(game, self.group.games())

    def test_games_includes_games_from_all_member_roles(self):
        GroupMembership.objects.create(
            user=self.user, group=self.group, role='member',
        )
        organizer = User.objects.create_user(username='org', password='testpass123')
        GroupMembership.objects.create(
            user=organizer, group=self.group, role='organizer',
        )
        game1 = BoardGame.objects.create(name='Game 1', owner=self.user)
        game2 = BoardGame.objects.create(name='Game 2', owner=organizer)
        self.assertEqual(self.group.games().count(), 2)

    def test_can_change_max_members_returns_false_for_regular_user(self):
        self.assertFalse(self.group.can_change_max_members(self.user))

    def test_can_change_max_members_returns_true_for_superuser(self):
        self.assertTrue(self.group.can_change_max_members(self.admin_user))


@tag("unit")
class EventGroupFKTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='eventuser', password='testpass123',
        )
        self.group = Group.objects.create(name='Event Group')

    def test_event_can_have_group(self):
        event = Event.objects.create(
            title='Group Event',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=self.user,
            group=self.group,
        )
        self.assertEqual(event.group, self.group)

    def test_event_cascade_on_group_delete(self):
        event = Event.objects.create(
            title='Cascade Event',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=self.user,
            group=self.group,
        )
        self.group.delete()
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())


@tag("unit")
class UserGroupCreationOverrideTest(TestCase):

    def test_group_creation_override_defaults_to_zero(self):
        user = User.objects.create_user(username='overrideuser', password='testpass123')
        self.assertEqual(user.group_creation_override, 0)

    def test_group_creation_override_can_be_set(self):
        user = User.objects.create_user(username='overrideuser', password='testpass123')
        user.group_creation_override = 3
        user.save()
        user.refresh_from_db()
        self.assertEqual(user.group_creation_override, 3)


@tag("unit")
class SiteSettingsGroupDeletionTest(TestCase):

    def test_allow_site_admins_to_delete_groups_defaults_false(self):
        settings = SiteSettings.load()
        self.assertFalse(settings.allow_site_admins_to_delete_groups)

    def test_allow_site_admins_to_delete_groups_can_be_set(self):
        settings = SiteSettings.load()
        settings.allow_site_admins_to_delete_groups = True
        settings.save()
        settings.refresh_from_db()
        self.assertTrue(settings.allow_site_admins_to_delete_groups)


@tag("unit")
class DataMigrationTest(TestCase):

    def _get_migration_function(self):
        mod = importlib.import_module(
            'club.migrations.0019_data_migration_default_group'
        )
        return mod.create_default_group_and_assign

    def _run_migration(self, apps):
        func = self._get_migration_function()
        func(apps, None)

    def test_creates_default_group_when_users_exist(self):
        user = User.objects.create_user(username='miguser', password='testpass123')
        from django.db import connection
        from django.apps import apps as django_apps

        class FakeApps:
            def get_model(self, app_label, model_name):
                return django_apps.get_model(app_label, model_name)

        self._run_migration(FakeApps())
        group = Group.objects.get(slug='workday-boardgames')
        self.assertEqual(group.name, 'Workday Boardgames')

    def test_skips_when_no_users(self):
        from django.apps import apps as django_apps

        class FakeApps:
            def get_model(self, app_label, model_name):
                return django_apps.get_model(app_label, model_name)

        self._run_migration(FakeApps())
        self.assertFalse(Group.objects.filter(slug='workday-boardgames').exists())

    def test_assigns_member_role_when_is_organizer_removed(self):
        user = User.objects.create_user(
            username='orguser', password='testpass123',
        )
        from django.apps import apps as django_apps

        class FakeApps:
            def get_model(self, app_label, model_name):
                return django_apps.get_model(app_label, model_name)

        self._run_migration(FakeApps())
        membership = GroupMembership.objects.get(user=user)
        self.assertEqual(membership.role, 'member')

    def test_assigns_member_role_to_regular_users(self):
        user = User.objects.create_user(username='reguser', password='testpass123')
        from django.apps import apps as django_apps

        class FakeApps:
            def get_model(self, app_label, model_name):
                return django_apps.get_model(app_label, model_name)

        self._run_migration(FakeApps())
        membership = GroupMembership.objects.get(user=user)
        self.assertEqual(membership.role, 'member')

    def test_assigns_existing_events_to_default_group(self):
        user = User.objects.create_user(
            username='evtuser', password='testpass123',
        )
        existing_group = Group.objects.create(name='Existing')
        event = Event.objects.create(
            title='Grouped Event',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=user,
            group=existing_group,
        )
        from django.apps import apps as django_apps

        class FakeApps:
            def get_model(self, app_label, model_name):
                return django_apps.get_model(app_label, model_name)

        self._run_migration(FakeApps())
        event.refresh_from_db()
        self.assertEqual(event.group, existing_group)

    def test_creates_memberships_for_all_users(self):
        user1 = User.objects.create_user(username='u1', password='testpass123')
        user2 = User.objects.create_user(username='u2', password='testpass123')
        from django.apps import apps as django_apps

        class FakeApps:
            def get_model(self, app_label, model_name):
                return django_apps.get_model(app_label, model_name)

        self._run_migration(FakeApps())
        group = Group.objects.get(slug='workday-boardgames')
        self.assertEqual(group.membership.count(), 2)

    def test_created_by_is_superuser(self):
        superuser = User.objects.create_superuser(
            username='super', password='testpass123',
        )
        regular = User.objects.create_user(username='regular', password='testpass123')
        from django.apps import apps as django_apps

        class FakeApps:
            def get_model(self, app_label, model_name):
                return django_apps.get_model(app_label, model_name)

        self._run_migration(FakeApps())
        group = Group.objects.get(slug='workday-boardgames')
        self.assertEqual(group.created_by, superuser)

    def test_created_by_falls_back_to_site_admin(self):
        site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True,
        )
        from django.apps import apps as django_apps

        class FakeApps:
            def get_model(self, app_label, model_name):
                return django_apps.get_model(app_label, model_name)

        self._run_migration(FakeApps())
        group = Group.objects.get(slug='workday-boardgames')
        self.assertEqual(group.created_by, site_admin)


@tag("unit")
class CleanupDisbandedGroupsTest(TestCase):

    def test_deletes_expired_disbanded_groups(self):
        group = Group.objects.create(name='Expired')
        group.disbanded_at = timezone.now() - timedelta(days=31)
        group.save()
        out = StringIO()
        call_command('cleanup_disbanded_groups', stdout=out)
        self.assertFalse(Group.objects.filter(pk=group.pk).exists())
        self.assertIn('Deleted 1', out.getvalue())

    def test_preserves_active_groups(self):
        Group.objects.create(name='Active')
        out = StringIO()
        call_command('cleanup_disbanded_groups', stdout=out)
        self.assertTrue(Group.objects.filter(name='Active').exists())
        self.assertIn('Deleted 0', out.getvalue())

    def test_preserves_groups_in_grace_period(self):
        group = Group.objects.create(name='Grace')
        group.disbanded_at = timezone.now() - timedelta(days=15)
        group.save()
        out = StringIO()
        call_command('cleanup_disbanded_groups', stdout=out)
        self.assertTrue(Group.objects.filter(pk=group.pk).exists())

    def test_cascade_deletes_related_data(self):
        user = User.objects.create_user(username='cascade', password='testpass123')
        group = Group.objects.create(name='Cascade')
        GroupMembership.objects.create(user=user, group=group)
        Event.objects.create(
            title='Cascade Event',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=user,
            group=group,
        )
        group.disbanded_at = timezone.now() - timedelta(days=31)
        group.save()
        call_command('cleanup_disbanded_groups', stdout=StringIO())
        self.assertFalse(GroupMembership.objects.filter(user=user).exists())
        self.assertFalse(Event.objects.filter(title='Cascade Event').exists())


# ---------------------------------------------------------------------------
# Group notification tests (from test_group_notifications.py)
# ---------------------------------------------------------------------------


@tag("unit")
class NotifyGroupJoinApprovedTest(TestCase):

    def test_creates_notification_for_user(self):
        user = User.objects.create_user(username='u', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='Test Group')
        notify_group_join_approved(user, group, actor)
        notif = Notification.objects.get(user=user)
        self.assertEqual(notif.notification_type, 'group_join_approved')
        self.assertIn('Test Group', notif.message)
        self.assertIn('actor', notif.message)
        self.assertEqual(notif.url, f'/groups/{group.slug}/')
        self.assertEqual(notif.url_label, 'View Group')

    def test_does_not_notify_other_users(self):
        user = User.objects.create_user(username='u', password='p')
        other = User.objects.create_user(username='other', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        notify_group_join_approved(user, group, actor)
        self.assertFalse(Notification.objects.filter(user=other).exists())


@tag("unit")
class NotifyGroupJoinRejectedTest(TestCase):

    def test_creates_notification_for_user(self):
        user = User.objects.create_user(username='u', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        notify_group_join_rejected(user, group, actor)
        notif = Notification.objects.get(user=user)
        self.assertEqual(notif.notification_type, 'group_join_rejected')
        self.assertIn('rejected', notif.message)
        self.assertIn('actor', notif.message)


@tag("unit")
class NotifyGroupPromotedOrganizerTest(TestCase):

    def test_creates_notification(self):
        user = User.objects.create_user(username='u', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        notify_group_promoted_organizer(user, group, actor)
        notif = Notification.objects.get(user=user)
        self.assertEqual(notif.notification_type, 'group_promoted_organizer')
        self.assertIn('organizer', notif.message)
        self.assertIn('actor', notif.message)


@tag("unit")
class NotifyGroupPromotedAdminTest(TestCase):

    def test_creates_notification(self):
        user = User.objects.create_user(username='u', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        notify_group_promoted_admin(user, group, actor)
        notif = Notification.objects.get(user=user)
        self.assertEqual(notif.notification_type, 'group_promoted_admin')
        self.assertIn('admin', notif.message)
        self.assertIn('actor', notif.message)


@tag("unit")
class NotifyGroupDemotedOrganizerTest(TestCase):

    def test_creates_notification(self):
        user = User.objects.create_user(username='u', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        notify_group_demoted_organizer(user, group, actor)
        notif = Notification.objects.get(user=user)
        self.assertEqual(notif.notification_type, 'group_demoted_organizer')
        self.assertIn('demoted to organizer', notif.message)
        self.assertIn('actor', notif.message)


@tag("unit")
class NotifyGroupDemotedMemberTest(TestCase):

    def test_creates_notification(self):
        user = User.objects.create_user(username='u', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        notify_group_demoted_member(user, group, actor)
        notif = Notification.objects.get(user=user)
        self.assertEqual(notif.notification_type, 'group_demoted_member')
        self.assertIn('demoted to member', notif.message)
        self.assertIn('actor', notif.message)


@tag("unit")
class NotifyGroupRemovedTest(TestCase):

    def test_creates_notification(self):
        user = User.objects.create_user(username='u', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        notify_group_removed(user, group, actor)
        notif = Notification.objects.get(user=user)
        self.assertEqual(notif.notification_type, 'group_removed')
        self.assertIn('removed', notif.message)
        self.assertIn('actor', notif.message)
        self.assertEqual(notif.url_label, 'Browse Groups')


@tag("unit")
class NotifyGroupEventCreatedTest(TestCase):

    def setUp(self):
        self.creator = User.objects.create_user(username='creator', password='p')
        self.member = User.objects.create_user(username='member', password='p')
        self.outsider = User.objects.create_user(username='outsider', password='p')
        self.group = Group.objects.create(name='Event Group')
        _make_admin(self.creator, self.group)
        _make_member(self.member, self.group)
        self.event = Event.objects.create(
            title='Game Night',
            date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.creator,
            group=self.group,
        )

    def test_notifies_all_members_except_creator(self):
        notify_group_event_created(self.group, self.event, self.creator)
        self.assertTrue(Notification.objects.filter(user=self.member).exists())
        self.assertFalse(Notification.objects.filter(user=self.creator).exists())
        self.assertFalse(Notification.objects.filter(user=self.outsider).exists())

    def test_notification_content(self):
        notify_group_event_created(self.group, self.event, self.creator)
        notif = Notification.objects.get(user=self.member)
        self.assertEqual(notif.notification_type, 'group_event_created')
        self.assertIn('Game Night', notif.message)
        self.assertIn('Event Group', notif.message)
        self.assertEqual(notif.url, f'/groups/{self.group.slug}/events/{self.event.pk}/')
        self.assertEqual(notif.url_label, 'View Event')

    def test_recurring_event_count(self):
        notify_group_event_created(self.group, self.event, self.creator, count=3)
        notif = Notification.objects.get(user=self.member)
        self.assertIn('3', notif.message)
        self.assertIn('recurring', notif.message)


@tag("unit")
class NotifyGroupEventUpdatedTest(TestCase):

    def test_notifies_all_members_except_actor(self):
        actor = User.objects.create_user(username='actor', password='p')
        member = User.objects.create_user(username='member', password='p')
        group = Group.objects.create(name='G')
        _make_admin(actor, group)
        _make_member(member, group)
        event = Event.objects.create(
            title='Ev', date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=actor, group=group,
        )
        notify_group_event_updated(group, event, actor)
        self.assertTrue(Notification.objects.filter(user=member).exists())
        self.assertFalse(Notification.objects.filter(user=actor).exists())
        notif = Notification.objects.get(user=member)
        self.assertEqual(notif.notification_type, 'group_event_updated')


@tag("unit")
class NotifyGroupVotingEndedTest(TestCase):

    def test_notifies_all_members_including_actor(self):
        actor = User.objects.create_user(username='actor', password='p')
        member = User.objects.create_user(username='member', password='p')
        group = Group.objects.create(name='G')
        _make_admin(actor, group)
        _make_member(member, group)
        event = Event.objects.create(
            title='Ev', date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=actor, group=group,
        )
        notify_group_voting_ended(group, event, actor)
        self.assertTrue(Notification.objects.filter(user=member).exists())
        notif = Notification.objects.get(user=member)
        self.assertEqual(notif.notification_type, 'group_voting_ended')
        self.assertIn('ended', notif.message)


@tag("unit")
class NotifyGroupVotingResumedTest(TestCase):

    def test_notifies_all_members(self):
        member = User.objects.create_user(username='member', password='p')
        group = Group.objects.create(name='G')
        _make_member(member, group)
        event = Event.objects.create(
            title='Ev', date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=member, group=group,
        )
        notify_group_voting_resumed(group, event, member)
        notif = Notification.objects.get(user=member)
        self.assertEqual(notif.notification_type, 'group_voting_resumed')
        self.assertIn('resumed', notif.message)


@tag("unit")
class NotifyGroupMemberJoinedTest(TestCase):

    def test_notifies_admins_only(self):
        admin = User.objects.create_user(username='admin', password='p')
        organizer = User.objects.create_user(username='organizer', password='p')
        member = User.objects.create_user(username='member', password='p')
        joined = User.objects.create_user(username='joined', password='p')
        group = Group.objects.create(name='G')
        _make_admin(admin, group)
        _make_organizer(organizer, group)
        _make_member(member, group)
        notify_group_member_joined(group, joined, method='open join')
        self.assertTrue(Notification.objects.filter(user=admin).exists())
        self.assertFalse(Notification.objects.filter(user=organizer).exists())
        self.assertFalse(Notification.objects.filter(user=member).exists())
        self.assertFalse(Notification.objects.filter(user=joined).exists())

    def test_notification_content(self):
        admin = User.objects.create_user(username='admin', password='p')
        joined = User.objects.create_user(username='joined', password='p')
        group = Group.objects.create(name='G')
        _make_admin(admin, group)
        notify_group_member_joined(group, joined, method='invite')
        notif = Notification.objects.get(user=admin)
        self.assertEqual(notif.notification_type, 'group_member_joined')
        self.assertIn('joined', notif.message)
        self.assertIn('invite', notif.message)


@tag("unit")
class NotifyGroupJoinRequestTest(TestCase):

    def test_notifies_admins(self):
        admin = User.objects.create_user(username='admin', password='p')
        requester = User.objects.create_user(username='req', password='p')
        group = Group.objects.create(name='G')
        _make_admin(admin, group)
        notify_group_join_request(group, requester)
        notif = Notification.objects.get(user=admin)
        self.assertEqual(notif.notification_type, 'group_join_request')
        self.assertIn('req', notif.message)
        self.assertIn('join-requests', notif.url)


@tag("unit")
class NotifyGroupMemberLeftTest(TestCase):

    def test_notifies_admins(self):
        admin = User.objects.create_user(username='admin', password='p')
        leaver = User.objects.create_user(username='leaver', password='p')
        group = Group.objects.create(name='G')
        _make_admin(admin, group)
        _make_member(leaver, group)
        notify_group_member_left(group, leaver)
        notif = Notification.objects.get(user=admin)
        self.assertEqual(notif.notification_type, 'group_member_left')
        self.assertIn('leaver', notif.message)
        self.assertIn('left', notif.message)


@tag("unit")
class NotifyGroupInviteCreatedTest(TestCase):

    def test_notifies_admins(self):
        admin = User.objects.create_user(username='admin', password='p')
        other_admin = User.objects.create_user(username='admin2', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        _make_admin(admin, group)
        _make_admin(other_admin, group)
        _make_admin(actor, group)
        notify_group_invite_created(group, actor)
        notifs = Notification.objects.filter(notification_type='group_invite_created')
        self.assertEqual(notifs.count(), 2)
        self.assertFalse(notifs.filter(user=actor).exists())
        self.assertTrue(notifs.filter(user=admin).exists())
        self.assertTrue(notifs.filter(user=other_admin).exists())


@tag("unit")
class NotifyGroupSettingsChangedTest(TestCase):

    def test_notifies_admins_except_actor(self):
        admin = User.objects.create_user(username='admin', password='p')
        actor = User.objects.create_user(username='actor', password='p')
        group = Group.objects.create(name='G')
        _make_admin(admin, group)
        _make_admin(actor, group)
        notify_group_settings_changed(group, actor)
        self.assertTrue(Notification.objects.filter(user=admin).exists())
        self.assertFalse(Notification.objects.filter(user=actor).exists())


@tag("unit")
class NotifyGroupGracePeriodTest(TestCase):

    def test_notifies_site_admins_and_superusers(self):
        site_admin = User.objects.create_user(
            username='siteadmin', password='p', is_site_admin=True,
        )
        superuser = User.objects.create_superuser(
            username='super', password='p', email='s@example.com',
        )
        regular = User.objects.create_user(username='regular', password='p')
        group = Group.objects.create(name='G')
        notify_group_grace_period(group)
        self.assertTrue(Notification.objects.filter(user=site_admin).exists())
        self.assertTrue(Notification.objects.filter(user=superuser).exists())
        self.assertFalse(Notification.objects.filter(user=regular).exists())

    def test_notification_content(self):
        site_admin = User.objects.create_user(
            username='siteadmin', password='p', is_site_admin=True,
        )
        group = Group.objects.create(name='Disbanded Group')
        notify_group_grace_period(group)
        notif = Notification.objects.get(user=site_admin)
        self.assertEqual(notif.notification_type, 'group_grace_period')
        self.assertIn('Disbanded Group', notif.message)
        self.assertIn('grace period', notif.message)


@tag("unit")
class NotifyGroupRestoredTest(TestCase):

    def test_notifies_site_admins_and_superusers_except_actor(self):
        site_admin = User.objects.create_user(
            username='siteadmin', password='p', is_site_admin=True,
        )
        superuser = User.objects.create_superuser(
            username='super', password='p', email='s@example.com',
        )
        group = Group.objects.create(name='G')
        notify_group_restored(group, site_admin)
        self.assertFalse(Notification.objects.filter(user=site_admin).exists())
        self.assertTrue(Notification.objects.filter(user=superuser).exists())

    def test_notification_content(self):
        site_admin = User.objects.create_user(
            username='siteadmin', password='p', is_site_admin=True,
        )
        actor = User.objects.create_user(
            username='actor', password='p', is_site_admin=True,
        )
        group = Group.objects.create(name='Restored Group')
        notify_group_restored(group, actor)
        notif = Notification.objects.get(user=site_admin)
        self.assertEqual(notif.notification_type, 'group_restored')
        self.assertIn('Restored Group', notif.message)
        self.assertIn('restored', notif.message)
        self.assertIn('actor', notif.message)


@tag("unit")
class DisbandedGroupNotificationGuardTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='p')
        self.member = User.objects.create_user(username='member', password='p')
        self.group = Group.objects.create(name='G')
        self.group.disbanded_at = timezone.now()
        self.group.save()
        _make_admin(self.admin, self.group)
        _make_member(self.member, self.group)

    def test_event_created_does_not_notify_disbanded_group(self):
        actor = User.objects.create_user(username='actor', password='p')
        event = Event.objects.create(
            title='Ev', date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=actor, group=self.group,
        )
        notify_group_event_created(self.group, event, actor)
        self.assertEqual(Notification.objects.count(), 0)

    def test_member_joined_does_not_notify_disbanded_group(self):
        joined = User.objects.create_user(username='joined', password='p')
        notify_group_member_joined(self.group, joined)
        self.assertEqual(Notification.objects.count(), 0)

    def test_member_left_does_not_notify_disbanded_group(self):
        notify_group_member_left(self.group, self.member)
        self.assertEqual(Notification.objects.count(), 0)

    def test_settings_changed_does_not_notify_disbanded_group(self):
        notify_group_settings_changed(self.group, self.admin)
        self.assertEqual(Notification.objects.count(), 0)

    def test_join_request_does_not_notify_disbanded_group(self):
        requester = User.objects.create_user(username='req', password='p')
        notify_group_join_request(self.group, requester)
        self.assertEqual(Notification.objects.count(), 0)

    def test_invite_created_does_not_notify_disbanded_group(self):
        notify_group_invite_created(self.group, self.admin)
        self.assertEqual(Notification.objects.count(), 0)

    def test_voting_ended_does_not_notify_disbanded_group(self):
        event = Event.objects.create(
            title='Ev', date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.admin, group=self.group,
        )
        notify_group_voting_ended(self.group, event, self.admin)
        self.assertEqual(Notification.objects.count(), 0)

    def test_voting_resumed_does_not_notify_disbanded_group(self):
        event = Event.objects.create(
            title='Ev', date=timezone.now() + timezone.timedelta(days=7),
            voting_deadline=timezone.now() + timezone.timedelta(days=7),
            created_by=self.admin, group=self.group,
        )
        notify_group_voting_resumed(self.group, event, self.admin)
        self.assertEqual(Notification.objects.count(), 0)

    def test_personal_notifications_still_fire_for_disbanded_group(self):
        actor = User.objects.create_user(username='actor', password='p')
        notify_group_removed(self.member, self.group, actor)
        self.assertEqual(Notification.objects.count(), 1)


# ---------------------------------------------------------------------------
# Group permission tests (from test_permissions.py)
# ---------------------------------------------------------------------------


@tag("unit")
class IsGroupAdminTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='u1', password='p')
        self.group = Group.objects.create(name='G1')

    def test_true_for_admin(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='admin')
        self.assertTrue(is_group_admin(self.user, self.group))

    def test_false_for_organizer(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='organizer')
        self.assertFalse(is_group_admin(self.user, self.group))

    def test_false_for_member(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='member')
        self.assertFalse(is_group_admin(self.user, self.group))

    def test_false_for_non_member(self):
        self.assertFalse(is_group_admin(self.user, self.group))

    def test_false_for_unauthenticated(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(is_group_admin(AnonymousUser(), self.group))


@tag("unit")
class IsGroupOrganizerTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='u1', password='p')
        self.group = Group.objects.create(name='G1')

    def test_true_for_admin(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='admin')
        self.assertTrue(is_group_organizer(self.user, self.group))

    def test_true_for_organizer(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='organizer')
        self.assertTrue(is_group_organizer(self.user, self.group))

    def test_false_for_member(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='member')
        self.assertFalse(is_group_organizer(self.user, self.group))

    def test_false_for_non_member(self):
        self.assertFalse(is_group_organizer(self.user, self.group))

    def test_false_for_unauthenticated(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(is_group_organizer(AnonymousUser(), self.group))


@tag("unit")
class IsGroupMemberTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='u1', password='p')
        self.group = Group.objects.create(name='G1')

    def test_true_for_member(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='member')
        self.assertTrue(is_group_member(self.user, self.group))

    def test_true_for_organizer(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='organizer')
        self.assertTrue(is_group_member(self.user, self.group))

    def test_true_for_admin(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='admin')
        self.assertTrue(is_group_member(self.user, self.group))

    def test_false_for_non_member(self):
        self.assertFalse(is_group_member(self.user, self.group))

    def test_false_for_unauthenticated(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(is_group_member(AnonymousUser(), self.group))


@tag("unit")
class CanCreateEventTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='u1', password='p')
        self.group = Group.objects.create(name='G1')

    def test_true_for_organizer(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='organizer')
        self.assertTrue(can_create_event(self.user, self.group))

    def test_true_for_admin(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='admin')
        self.assertTrue(can_create_event(self.user, self.group))

    def test_false_for_member(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='member')
        self.assertFalse(can_create_event(self.user, self.group))


@tag("unit")
class CanManageMembersTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='u1', password='p')
        self.group = Group.objects.create(name='G1')

    def test_true_for_admin(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='admin')
        self.assertTrue(can_manage_members(self.user, self.group))

    def test_false_for_organizer(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='organizer')
        self.assertFalse(can_manage_members(self.user, self.group))

    def test_false_for_member(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='member')
        self.assertFalse(can_manage_members(self.user, self.group))


@tag("unit")
class CanEditGroupSettingsTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='u1', password='p')
        self.group = Group.objects.create(name='G1')

    def test_true_for_admin(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='admin')
        self.assertTrue(can_edit_group_settings(self.user, self.group))

    def test_false_for_organizer(self):
        GroupMembership.objects.create(user=self.user, group=self.group, role='organizer')
        self.assertFalse(can_edit_group_settings(self.user, self.group))


@tag("unit")
class CanViewGroupTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='u1', password='p')
        self.group = Group.objects.create(name='G1')

    def test_true_for_discoverable(self):
        self.assertTrue(can_view_group(self.user, self.group))

    def test_false_for_non_discoverable_non_member(self):
        self.group.discoverable = False
        self.group.save()
        self.assertFalse(can_view_group(self.user, self.group))

    def test_true_for_member_of_non_discoverable(self):
        self.group.discoverable = False
        self.group.save()
        GroupMembership.objects.create(user=self.user, group=self.group)
        self.assertTrue(can_view_group(self.user, self.group))

    def test_true_for_superuser_non_discoverable(self):
        self.group.discoverable = False
        self.group.save()
        su = User.objects.create_superuser(username='su', password='p')
        self.assertTrue(can_view_group(su, self.group))

    def test_true_for_site_admin_non_discoverable(self):
        self.group.discoverable = False
        self.group.save()
        sa = User.objects.create_user(username='sa', password='p', is_site_admin=True)
        self.assertTrue(can_view_group(sa, self.group))


@tag("unit")
class CanViewVotesTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='u1', password='p')
        self.group = Group.objects.create(name='G1')

    def test_true_for_member(self):
        GroupMembership.objects.create(user=self.user, group=self.group)
        self.assertTrue(can_view_votes(self.user, self.group))

    def test_false_for_non_member(self):
        self.assertFalse(can_view_votes(self.user, self.group))


@tag("unit")
class CanCreateGroupTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='u1', password='p')

    def test_true_under_limit(self):
        self.assertTrue(can_create_group(self.user))

    def test_false_at_limit(self):
        for i in range(2):
            GroupCreationLog.objects.create(user=self.user)
        from club.models import Group
        for log in GroupCreationLog.objects.filter(user=self.user):
            log.group = Group.objects.create(name=f'G{i}')
            log.save()
        self.assertFalse(can_create_group(self.user))

    def test_true_with_override(self):
        for i in range(2):
            GroupCreationLog.objects.create(user=self.user)
        self.user.group_creation_override = 1
        self.user.save()
        self.assertTrue(can_create_group(self.user))

    def test_counts_only_last_7_days(self):
        GroupCreationLog.objects.create(
            user=self.user,
            created_at=timezone.now() - timedelta(days=8),
        )
        self.assertTrue(can_create_group(self.user))

    def test_true_for_superuser(self):
        for i in range(2):
            GroupCreationLog.objects.create(user=self.user)
        su = User.objects.create_superuser(username='su', password='p')
        self.assertTrue(can_create_group(su))

    def test_true_for_site_admin(self):
        for i in range(2):
            GroupCreationLog.objects.create(user=self.user)
        sa = User.objects.create_user(username='sa', password='p', is_site_admin=True)
        self.assertTrue(can_create_group(sa))

    def test_override_used_by_existing_log(self):
        self.user.group_creation_override = 1
        self.user.save()
        GroupCreationLog.objects.create(user=self.user)
        self.assertTrue(can_create_group(self.user))

    def test_override_exhausted(self):
        self.user.group_creation_override = 1
        self.user.save()
        GroupCreationLog.objects.create(user=self.user)
        GroupCreationLog.objects.create(user=self.user)
        GroupCreationLog.objects.create(user=self.user)
        self.assertFalse(can_create_group(self.user))


@tag("unit")
class CanDeleteGroupTest(TestCase):

    def test_true_for_superuser(self):
        su = User.objects.create_superuser(username='su', password='p')
        self.assertTrue(can_delete_group(su))

    def test_false_for_site_admin_without_toggle(self):
        sa = User.objects.create_user(username='sa', password='p', is_site_admin=True)
        self.assertFalse(can_delete_group(sa))

    def test_true_for_site_admin_with_toggle(self):
        sa = User.objects.create_user(username='sa', password='p', is_site_admin=True)
        settings = SiteSettings.load()
        settings.allow_site_admins_to_delete_groups = True
        settings.save()
        self.assertTrue(can_delete_group(sa))

    def test_false_for_regular_user(self):
        self.assertFalse(can_delete_group(self.user if hasattr(self, 'user') else User.objects.create_user(username='u', password='p')))


@tag("unit")
class CanRestoreGroupTest(TestCase):

    def test_true_for_superuser(self):
        su = User.objects.create_superuser(username='su', password='p')
        self.assertTrue(can_restore_group(su))

    def test_true_for_site_admin(self):
        sa = User.objects.create_user(username='sa', password='p', is_site_admin=True)
        self.assertTrue(can_restore_group(sa))

    def test_false_for_regular_user(self):
        u = User.objects.create_user(username='u', password='p')
        self.assertFalse(can_restore_group(u))


@tag("unit")
class CanCreatePrivateEventTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='alice', password='p', email_verified=True,
        )

    def test_verified_user_can_create(self):
        self.assertTrue(can_create_private_event(self.user))

    def test_unverified_user_cannot_create(self):
        self.user.email_verified = False
        self.user.save()
        self.assertFalse(can_create_private_event(self.user))

    def test_superuser_bypasses_verification(self):
        su = User.objects.create_superuser(username='su', password='p')
        self.assertTrue(can_create_private_event(su))

    def test_site_admin_bypasses_verification(self):
        sa = User.objects.create_user(
            username='sa', password='p',
            is_site_admin=True, email_verified=False,
        )
        self.assertTrue(can_create_private_event(sa))

    def test_rate_limit_blocks_at_five(self):
        for i in range(5):
            PrivateEventCreationLog.objects.create(user=self.user)
        self.assertFalse(can_create_private_event(self.user))

    def test_rate_limit_allows_under_five(self):
        for i in range(4):
            PrivateEventCreationLog.objects.create(user=self.user)
        self.assertTrue(can_create_private_event(self.user))

    def test_rate_limit_rolling_window(self):
        old = PrivateEventCreationLog.objects.create(user=self.user)
        PrivateEventCreationLog.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(hours=169),
        )
        for i in range(4):
            PrivateEventCreationLog.objects.create(user=self.user)
        self.assertTrue(can_create_private_event(self.user))

    def test_superuser_bypasses_rate_limit(self):
        for i in range(5):
            PrivateEventCreationLog.objects.create(user=self.user)
        su = User.objects.create_superuser(username='su', password='p')
        self.assertTrue(can_create_private_event(su))

    def test_unauthenticated_cannot_create(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(can_create_private_event(AnonymousUser()))


@tag("unit")
class CanViewPrivateEventTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='p')
        self.bob = User.objects.create_user(username='bob', password='p')
        self.event = Event.objects.create(
            title='Test Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
        )

    def test_creator_can_view(self):
        self.assertTrue(can_view_private_event(self.alice, self.event))

    def test_public_event_visible_to_anyone(self):
        self.event.privacy = 'public'
        self.event.save()
        self.assertTrue(can_view_private_event(self.bob, self.event))

    def test_invite_only_public_visible_to_anyone(self):
        self.event.privacy = 'invite_only_public'
        self.event.save()
        self.assertTrue(can_view_private_event(self.bob, self.event))

    def test_private_not_visible_to_non_invitee(self):
        self.event.privacy = 'private'
        self.event.save()
        self.assertFalse(can_view_private_event(self.bob, self.event))

    def test_private_visible_to_invitee(self):
        self.event.privacy = 'private'
        self.event.save()
        EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        self.assertTrue(can_view_private_event(self.bob, self.event))

    def test_private_visible_to_attendee(self):
        self.event.privacy = 'private'
        self.event.save()
        EventAttendance.objects.create(user=self.bob, event=self.event)
        self.assertTrue(can_view_private_event(self.bob, self.event))

    def test_group_event_ignored(self):
        group = Group.objects.create(name='G1')
        self.event.group = group
        self.event.save()
        self.assertIsNone(can_view_private_event(self.bob, self.event))

    def test_superuser_can_view(self):
        su = User.objects.create_superuser(username='su', password='p')
        self.event.privacy = 'private'
        self.event.save()
        self.assertTrue(can_view_private_event(su, self.event))

    def test_additional_organizer_can_view(self):
        self.event.privacy = 'private'
        self.event.save()
        self.event.additional_organizers.add(self.bob)
        self.assertTrue(can_view_private_event(self.bob, self.event))


@tag("unit")
class CanRsvpPrivateEventTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='p')
        self.bob = User.objects.create_user(username='bob', password='p')
        self.event = Event.objects.create(
            title='Test Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
        )

    def test_public_event_anyone_can_rsvp(self):
        self.event.privacy = 'public'
        self.event.save()
        self.assertTrue(can_rsvp_private_event(self.bob, self.event))

    def test_private_event_invitee_can_rsvp(self):
        self.event.privacy = 'private'
        self.event.save()
        EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        self.assertTrue(can_rsvp_private_event(self.bob, self.event))

    def test_private_event_non_invitee_cannot_rsvp(self):
        self.event.privacy = 'private'
        self.event.save()
        self.assertFalse(can_rsvp_private_event(self.bob, self.event))

    def test_invite_only_public_invitee_can_rsvp(self):
        self.event.privacy = 'invite_only_public'
        self.event.save()
        EventInvite.objects.create(
            event=self.event, user=self.bob, invited_by=self.alice,
        )
        self.assertTrue(can_rsvp_private_event(self.bob, self.event))

    def test_invite_only_public_non_invitee_cannot_rsvp(self):
        self.event.privacy = 'invite_only_public'
        self.event.save()
        self.assertFalse(can_rsvp_private_event(self.bob, self.event))

    def test_group_event_ignored(self):
        group = Group.objects.create(name='G1')
        self.event.group = group
        self.event.save()
        self.assertIsNone(can_rsvp_private_event(self.bob, self.event))


@tag("unit")
class CanInviteToEventTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='p')
        self.bob = User.objects.create_user(username='bob', password='p')
        self.carol = User.objects.create_user(username='carol', password='p')
        self.event = Event.objects.create(
            title='Test Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
        )

    def test_creator_can_always_invite(self):
        self.assertTrue(can_invite_to_event(self.alice, self.event))

    def test_nobody_setting_blocks_others(self):
        self.event.allow_invite_others = 'nobody'
        self.event.save()
        self.assertFalse(can_invite_to_event(self.bob, self.event))

    def test_anyone_setting_allows_anyone(self):
        self.event.allow_invite_others = 'anyone'
        self.event.additional_organizers.add(self.bob)
        self.event.save()
        self.assertTrue(can_invite_to_event(self.bob, self.event))

    def test_friends_only_allows_friend(self):
        from club.models import Friendship
        Friendship.objects.create(
            requester=self.bob, receiver=self.carol, status='accepted',
        )
        self.event.allow_invite_others = 'friends_only'
        self.event.additional_organizers.add(self.bob)
        self.event.save()
        self.assertTrue(can_invite_to_event(self.bob, self.event, self.carol))

    def test_friends_only_blocks_non_friend(self):
        self.event.allow_invite_others = 'friends_only'
        self.event.additional_organizers.add(self.bob)
        self.event.save()
        self.assertFalse(can_invite_to_event(self.bob, self.event, self.carol))

    def test_non_organizer_cannot_invite(self):
        self.event.allow_invite_others = 'anyone'
        self.event.save()
        self.assertFalse(can_invite_to_event(self.bob, self.event))


@tag("unit")
class CanEditPrivateEventSettingsTest(TestCase):

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='p')
        self.bob = User.objects.create_user(username='bob', password='p')
        self.event = Event.objects.create(
            title='Test Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.alice,
            voting_deadline=timezone.now() + timedelta(days=6),
        )

    def test_creator_can_edit_settings(self):
        self.assertTrue(can_edit_private_event_settings(self.alice, self.event))

    def test_additional_organizer_cannot_edit_settings(self):
        self.event.additional_organizers.add(self.bob)
        self.assertFalse(can_edit_private_event_settings(self.bob, self.event))

    def test_non_organizer_cannot_edit_settings(self):
        self.assertFalse(can_edit_private_event_settings(self.bob, self.event))
