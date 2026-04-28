from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory, tag
from django.utils import timezone

from club.models import (
    Event,
    EventAttendance,
    EventInvite,
    Group,
    GroupCreationLog,
    GroupMembership,
    PrivateEventCreationLog,
    SiteSettings,
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


# ---------------------------------------------------------------------------
# Private event permissions
# ---------------------------------------------------------------------------

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
