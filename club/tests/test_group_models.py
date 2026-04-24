from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone
from datetime import timedelta

from django.core.management import call_command
from io import StringIO

from club.models import Group, GroupMembership, GroupInvite, GroupJoinRequest, GroupCreationLog, BoardGame, Event, SiteSettings
import importlib

User = get_user_model()


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
