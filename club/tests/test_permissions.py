from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory, tag
from django.utils import timezone

from club.models import (
    Group,
    GroupCreationLog,
    GroupMembership,
    SiteSettings,
)
from club.permissions import (
    can_create_event,
    can_create_group,
    can_delete_group,
    can_edit_group_settings,
    can_manage_members,
    can_restore_group,
    can_view_group,
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
