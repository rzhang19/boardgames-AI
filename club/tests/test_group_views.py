from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.utils import timezone

from club.models import (
    BoardGame,
    Event,
    EventAttendance,
    Group,
    GroupCreationLog,
    GroupInvite,
    GroupJoinRequest,
    GroupMembership,
    SiteSettings,
    Vote,
)

User = get_user_model()


@tag("unit")
class GroupListViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='u1', password='p')
        cls.group = Group.objects.create(name='My Group')
        GroupMembership.objects.create(user=cls.user, group=cls.group)

    def setUp(self):
        self.client.login(username='u1', password='p')

    def test_authenticated_user_can_access(self):
        response = self.client.get('/groups/')
        self.assertEqual(response.status_code, 200)

    def test_redirect_if_not_logged_in(self):
        self.client.logout()
        response = self.client.get('/groups/')
        self.assertEqual(response.status_code, 302)

    def test_my_groups_tab_shows_member_groups(self):
        response = self.client.get('/groups/?tab=my')
        self.assertIn(self.group, response.context['groups'])

    def test_all_groups_tab_shows_discoverable(self):
        public_group = Group.objects.create(name='Public', discoverable=True)
        response = self.client.get('/groups/?tab=all')
        self.assertIn(public_group, response.context['groups'])

    def test_all_groups_hides_non_discoverable_non_member(self):
        private_group = Group.objects.create(name='Private', discoverable=False)
        response = self.client.get('/groups/?tab=all')
        self.assertNotIn(private_group, response.context['groups'])

    def test_search_filters_by_name(self):
        response = self.client.get('/groups/?tab=my&q=My')
        self.assertIn(self.group, response.context['groups'])

    def test_search_excludes_non_matching(self):
        response = self.client.get('/groups/?tab=my&q=Nonexistent')
        self.assertNotIn(self.group, response.context['groups'])

    def test_search_case_insensitive(self):
        response = self.client.get('/groups/?tab=my&q=my group')
        self.assertIn(self.group, response.context['groups'])

    def test_favorites_ordered_first(self):
        group2 = Group.objects.create(name='A First Group')
        GroupMembership.objects.create(user=self.user, group=group2, is_favorite=True)
        response = self.client.get('/groups/?tab=my')
        groups = response.context['groups']
        self.assertEqual(groups[0], group2)


@tag("unit")
class GroupCreateViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='u1', password='p')

    def setUp(self):
        self.client.login(username='u1', password='p')

    def test_get_create_form(self):
        response = self.client.get('/groups/create/')
        self.assertEqual(response.status_code, 200)

    def test_create_group(self):
        response = self.client.post('/groups/create/', {
            'name': 'New Group',
            'description': 'A test group',
            'discoverable': True,
            'join_policy': 'open',
        })
        self.assertEqual(response.status_code, 302)
        group = Group.objects.get(name='New Group')
        self.assertEqual(group.slug, 'new-group')
        self.assertEqual(group.created_by, self.user)

    def test_creator_becomes_admin(self):
        self.client.post('/groups/create/', {
            'name': 'Admin Group',
            'join_policy': 'open',
        })
        group = Group.objects.get(name='Admin Group')
        membership = GroupMembership.objects.get(user=self.user, group=group)
        self.assertEqual(membership.role, 'admin')

    def test_creation_log_created(self):
        self.client.post('/groups/create/', {
            'name': 'Logged Group',
            'join_policy': 'open',
        })
        self.assertEqual(GroupCreationLog.objects.filter(user=self.user).count(), 1)

    def test_rate_limit_blocks_creation(self):
        for i in range(2):
            GroupCreationLog.objects.create(user=self.user)
        response = self.client.post('/groups/create/', {
            'name': 'Blocked Group',
            'join_policy': 'open',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Group.objects.filter(name='Blocked Group').exists())

    def test_redirect_if_not_logged_in(self):
        self.client.logout()
        response = self.client.get('/groups/create/')
        self.assertEqual(response.status_code, 302)


@tag("unit")
class GroupDashboardViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='u1', password='p')
        cls.group = Group.objects.create(name='Dashboard Group', discoverable=True)
        GroupMembership.objects.create(user=cls.user, group=cls.group, role='admin')

    def setUp(self):
        self.client.login(username='u1', password='p')

    def test_member_can_view(self):
        response = self.client.get(f'/groups/{self.group.slug}/')
        self.assertEqual(response.status_code, 200)

    def test_non_discoverable_hidden_from_non_member(self):
        private_group = Group.objects.create(name='Private', discoverable=False)
        other_user = User.objects.create_user(username='other', password='p')
        self.client.login(username='other', password='p')
        response = self.client.get(f'/groups/{private_group.slug}/')
        self.assertEqual(response.status_code, 403)

    def test_non_member_can_view_discoverable(self):
        public_group = Group.objects.create(name='Public', discoverable=True)
        other_user = User.objects.create_user(username='other2', password='p')
        self.client.login(username='other2', password='p')
        response = self.client.get(f'/groups/{public_group.slug}/')
        self.assertEqual(response.status_code, 200)

    def test_disbanded_group_shows_banner(self):
        self.group.disbanded_at = timezone.now()
        self.group.save()
        response = self.client.get(f'/groups/{self.group.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['group'].is_disbanded)

    def test_context_has_members(self):
        response = self.client.get(f'/groups/{self.group.slug}/')
        self.assertIn('members', response.context)

    def test_context_has_upcoming_events(self):
        response = self.client.get(f'/groups/{self.group.slug}/')
        self.assertIn('upcoming_events', response.context)

    def test_unauthenticated_can_view_discoverable(self):
        self.client.logout()
        response = self.client.get(f'/groups/{self.group.slug}/')
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_cannot_view_non_discoverable(self):
        private = Group.objects.create(name='Priv', discoverable=False)
        self.client.logout()
        response = self.client.get(f'/groups/{private.slug}/')
        self.assertEqual(response.status_code, 403)


@tag("unit")
class GroupSettingsViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='admin', password='p')
        cls.group = Group.objects.create(name='Settings Group')
        GroupMembership.objects.create(user=cls.user, group=cls.group, role='admin')

    def setUp(self):
        self.client.login(username='admin', password='p')

    def test_admin_can_access(self):
        response = self.client.get(f'/groups/{self.group.slug}/settings/')
        self.assertEqual(response.status_code, 200)

    def test_non_admin_denied(self):
        member = User.objects.create_user(username='member', password='p')
        GroupMembership.objects.create(user=member, group=self.group, role='member')
        self.client.login(username='member', password='p')
        response = self.client.get(f'/groups/{self.group.slug}/settings/')
        self.assertEqual(response.status_code, 403)

    def test_admin_can_edit_settings(self):
        response = self.client.post(f'/groups/{self.group.slug}/settings/', {
            'name': 'Updated Name',
            'description': 'Updated',
            'join_policy': 'request',
            'discoverable': True,
            'max_members': 50,
        })
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, 'Updated Name')

    def test_disbanded_group_returns_403(self):
        self.group.disbanded_at = timezone.now()
        self.group.save()
        response = self.client.get(f'/groups/{self.group.slug}/settings/')
        self.assertEqual(response.status_code, 403)

    def test_max_members_disabled_for_non_superuser(self):
        response = self.client.get(f'/groups/{self.group.slug}/settings/')
        self.assertTrue(response.context['form'].fields['max_members'].disabled)

    def test_max_members_enabled_for_superuser(self):
        su = User.objects.create_superuser(username='su', password='p')
        GroupMembership.objects.create(user=su, group=self.group, role='admin')
        self.client.login(username='su', password='p')
        response = self.client.get(f'/groups/{self.group.slug}/settings/')
        self.assertFalse(response.context['form'].fields['max_members'].disabled)


@tag("unit")
class GroupFavoriteViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='u1', password='p')
        cls.group = Group.objects.create(name='Fav Group')
        cls.membership = GroupMembership.objects.create(
            user=cls.user, group=cls.group,
        )

    def setUp(self):
        self.client.login(username='u1', password='p')

    def test_toggle_on(self):
        self.client.post(f'/groups/{self.group.slug}/favorite/')
        self.membership.refresh_from_db()
        self.assertTrue(self.membership.is_favorite)

    def test_toggle_off(self):
        self.membership.is_favorite = True
        self.membership.save()
        self.client.post(f'/groups/{self.group.slug}/favorite/')
        self.membership.refresh_from_db()
        self.assertFalse(self.membership.is_favorite)

    def test_non_member_gets_404(self):
        other = User.objects.create_user(username='other', password='p')
        self.client.login(username='other', password='p')
        response = self.client.post(f'/groups/{self.group.slug}/favorite/')
        self.assertEqual(response.status_code, 404)

    def test_get_redirects(self):
        response = self.client.get(f'/groups/{self.group.slug}/favorite/')
        self.assertEqual(response.status_code, 302)


@tag("unit")
class GroupDeleteViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.su = User.objects.create_superuser(username='su', password='p')
        cls.group = Group.objects.create(name='Delete Me')

    def setUp(self):
        self.client.login(username='su', password='p')

    def test_superuser_can_access(self):
        response = self.client.get(f'/groups/{self.group.slug}/delete/')
        self.assertEqual(response.status_code, 200)

    def test_regular_user_denied(self):
        regular = User.objects.create_user(username='reg', password='p')
        self.client.login(username='reg', password='p')
        response = self.client.get(f'/groups/{self.group.slug}/delete/')
        self.assertEqual(response.status_code, 403)

    def test_site_admin_denied_without_toggle(self):
        sa = User.objects.create_user(username='sa', password='p', is_site_admin=True)
        self.client.login(username='sa', password='p')
        response = self.client.get(f'/groups/{self.group.slug}/delete/')
        self.assertEqual(response.status_code, 403)

    def test_site_admin_allowed_with_toggle(self):
        sa = User.objects.create_user(username='sa', password='p', is_site_admin=True)
        settings = SiteSettings.load()
        settings.allow_site_admins_to_delete_groups = True
        settings.save()
        self.client.login(username='sa', password='p')
        response = self.client.get(f'/groups/{self.group.slug}/delete/')
        self.assertEqual(response.status_code, 200)

    def test_delete_with_correct_name(self):
        response = self.client.post(f'/groups/{self.group.slug}/delete/', {
            'confirm_name': 'Delete Me',
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Group.objects.filter(pk=self.group.pk).exists())

    def test_delete_with_wrong_name_fails(self):
        response = self.client.post(f'/groups/{self.group.slug}/delete/', {
            'confirm_name': 'Wrong Name',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Group.objects.filter(pk=self.group.pk).exists())
        self.assertIn('error', response.context)

    def test_unauthenticated_redirects(self):
        self.client.logout()
        response = self.client.get(f'/groups/{self.group.slug}/delete/')
        self.assertEqual(response.status_code, 302)


@tag("unit")
class GroupRestoreViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.su = User.objects.create_superuser(username='su', password='p')
        cls.group = Group.objects.create(name='Disbanded')
        cls.group.disbanded_at = timezone.now() - timedelta(days=10)
        cls.group.save()

    def setUp(self):
        self.client.login(username='su', password='p')

    def test_superuser_can_access(self):
        response = self.client.get(f'/groups/{self.group.slug}/restore/')
        self.assertEqual(response.status_code, 200)

    def test_site_admin_can_access(self):
        sa = User.objects.create_user(username='sa', password='p', is_site_admin=True)
        self.client.login(username='sa', password='p')
        response = self.client.get(f'/groups/{self.group.slug}/restore/')
        self.assertEqual(response.status_code, 200)

    def test_regular_user_denied(self):
        regular = User.objects.create_user(username='reg', password='p')
        self.client.login(username='reg', password='p')
        response = self.client.get(f'/groups/{self.group.slug}/restore/')
        self.assertEqual(response.status_code, 403)

    def test_restore_clears_disbanded_at(self):
        self.client.post(f'/groups/{self.group.slug}/restore/')
        self.group.refresh_from_db()
        self.assertIsNone(self.group.disbanded_at)

    def test_restore_makes_restorer_admin_if_no_members(self):
        sa = User.objects.create_user(username='sa', password='p', is_site_admin=True)
        self.client.login(username='sa', password='p')
        self.client.post(f'/groups/{self.group.slug}/restore/')
        membership = GroupMembership.objects.get(user=sa, group=self.group)
        self.assertEqual(membership.role, 'admin')

    def test_restore_does_not_add_membership_if_members_exist(self):
        user = User.objects.create_user(username='existing', password='p')
        GroupMembership.objects.create(user=user, group=self.group)
        self.client.post(f'/groups/{self.group.slug}/restore/')
        self.assertFalse(GroupMembership.objects.filter(user=self.su, group=self.group).exists())

    def test_cannot_restore_active_group(self):
        active_group = Group.objects.create(name='Active')
        response = self.client.get(f'/groups/{active_group.slug}/restore/')
        self.assertEqual(response.status_code, 302)

    def test_unauthenticated_redirects(self):
        self.client.logout()
        response = self.client.get(f'/groups/{self.group.slug}/restore/')
        self.assertEqual(response.status_code, 302)


@tag("unit")
class GroupMembersViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='u1', password='p')
        cls.group = Group.objects.create(name='Members', discoverable=True)
        GroupMembership.objects.create(user=cls.user, group=cls.group, role='admin')

    def setUp(self):
        self.client.login(username='u1', password='p')

    def test_member_can_view(self):
        response = self.client.get(f'/groups/{self.group.slug}/members/')
        self.assertEqual(response.status_code, 200)

    def test_non_discoverable_hidden_from_non_member(self):
        private = Group.objects.create(name='Priv', discoverable=False)
        other = User.objects.create_user(username='other', password='p')
        self.client.login(username='other', password='p')
        response = self.client.get(f'/groups/{private.slug}/members/')
        self.assertEqual(response.status_code, 403)

    def test_discoverable_visible_to_non_member(self):
        other = User.objects.create_user(username='other', password='p')
        self.client.login(username='other', password='p')
        response = self.client.get(f'/groups/{self.group.slug}/members/')
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_can_view_discoverable(self):
        self.client.logout()
        response = self.client.get(f'/groups/{self.group.slug}/members/')
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_cannot_view_non_discoverable(self):
        private = Group.objects.create(name='Priv2', discoverable=False)
        self.client.logout()
        response = self.client.get(f'/groups/{private.slug}/members/')
        self.assertEqual(response.status_code, 403)


@tag("unit")
class GroupMembersManageViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username='admin', password='p')
        cls.group = Group.objects.create(name='Manage')
        GroupMembership.objects.create(user=cls.admin, group=cls.group, role='admin')
        cls.member = User.objects.create_user(username='member', password='p')
        GroupMembership.objects.create(user=cls.member, group=cls.group, role='member')

    def setUp(self):
        self.client.login(username='admin', password='p')

    def test_admin_can_access(self):
        response = self.client.get(f'/groups/{self.group.slug}/members/manage/')
        self.assertEqual(response.status_code, 200)

    def test_non_admin_denied(self):
        self.client.login(username='member', password='p')
        response = self.client.get(f'/groups/{self.group.slug}/members/manage/')
        self.assertEqual(response.status_code, 403)

    def test_promote_member_to_organizer(self):
        self.client.post(f'/groups/{self.group.slug}/members/manage/', {
            'user_id': self.member.pk,
            'action': 'promote_organizer',
        })
        m = GroupMembership.objects.get(user=self.member, group=self.group)
        self.assertEqual(m.role, 'organizer')

    def test_promote_organizer_to_admin(self):
        GroupMembership.objects.filter(user=self.member, group=self.group).update(role='organizer')
        self.client.post(f'/groups/{self.group.slug}/members/manage/', {
            'user_id': self.member.pk,
            'action': 'promote_admin',
        })
        m = GroupMembership.objects.get(user=self.member, group=self.group)
        self.assertEqual(m.role, 'admin')

    def test_demote_organizer_to_member(self):
        GroupMembership.objects.filter(user=self.member, group=self.group).update(role='organizer')
        self.client.post(f'/groups/{self.group.slug}/members/manage/', {
            'user_id': self.member.pk,
            'action': 'demote_member',
        })
        m = GroupMembership.objects.get(user=self.member, group=self.group)
        self.assertEqual(m.role, 'member')

    def test_demote_admin_to_organizer(self):
        GroupMembership.objects.filter(user=self.member, group=self.group).update(role='admin')
        self.client.post(f'/groups/{self.group.slug}/members/manage/', {
            'user_id': self.member.pk,
            'action': 'demote_organizer',
            'confirmed': 'true',
        })
        m = GroupMembership.objects.get(user=self.member, group=self.group)
        self.assertEqual(m.role, 'organizer')

    def test_remove_member(self):
        self.client.post(f'/groups/{self.group.slug}/members/manage/', {
            'user_id': self.member.pk,
            'action': 'remove',
        })
        self.assertFalse(GroupMembership.objects.filter(
            user=self.member, group=self.group,
        ).exists())

    def test_cannot_remove_self(self):
        self.client.post(f'/groups/{self.group.slug}/members/manage/', {
            'user_id': self.admin.pk,
            'action': 'remove',
        })
        self.assertTrue(GroupMembership.objects.filter(
            user=self.admin, group=self.group,
        ).exists())

    def test_remove_cleans_upcoming_votes_and_rsvps(self):
        event = Event.objects.create(
            title='Upcoming',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=self.admin,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.member, event=event)
        game = BoardGame.objects.create(name='G1', owner=self.admin)
        Vote.objects.create(user=self.member, event=event, board_game=game, rank=1)
        self.client.post(f'/groups/{self.group.slug}/members/manage/', {
            'user_id': self.member.pk,
            'action': 'remove',
        })
        self.assertFalse(EventAttendance.objects.filter(user=self.member).exists())
        self.assertFalse(Vote.objects.filter(user=self.member).exists())

    def test_remove_preserves_past_event_data(self):
        past_event = Event.objects.create(
            title='Past',
            date=timezone.now() - timedelta(days=7),
            voting_deadline=timezone.now() - timedelta(days=7),
            created_by=self.admin,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.member, event=past_event)
        game = BoardGame.objects.create(name='G2', owner=self.admin)
        Vote.objects.create(user=self.member, event=past_event, board_game=game, rank=1)
        self.client.post(f'/groups/{self.group.slug}/members/manage/', {
            'user_id': self.member.pk,
            'action': 'remove',
        })
        self.assertTrue(EventAttendance.objects.filter(user=self.member).exists())
        self.assertTrue(Vote.objects.filter(user=self.member).exists())

    def test_removing_last_member_disbands_group(self):
        GroupMembership.objects.filter(user=self.member, group=self.group).delete()
        self.client.post(f'/groups/{self.group.slug}/members/manage/', {
            'user_id': self.admin.pk,
            'action': 'remove',
        })


@tag("unit")
class GroupJoinViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='joiner', password='p')

    def setUp(self):
        self.client.login(username='joiner', password='p')

    def test_open_group_auto_join(self):
        group = Group.objects.create(name='Open', join_policy='open')
        response = self.client.post(f'/groups/{group.slug}/join/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(GroupMembership.objects.filter(user=self.user, group=group).exists())

    def test_request_group_creates_request(self):
        group = Group.objects.create(name='Request', join_policy='request')
        response = self.client.post(f'/groups/{group.slug}/join/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(GroupJoinRequest.objects.filter(
            user=self.user, group=group, status='pending',
        ).exists())

    def test_invite_only_group_returns_403(self):
        group = Group.objects.create(name='Invite', join_policy='invite_only')
        response = self.client.post(f'/groups/{group.slug}/join/')
        self.assertEqual(response.status_code, 403)

    def test_full_group_rejects(self):
        group = Group.objects.create(name='Full', join_policy='open', max_members=1)
        other = User.objects.create_user(username='other', password='p')
        GroupMembership.objects.create(user=other, group=group)
        response = self.client.post(f'/groups/{group.slug}/join/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('full', response.context.get('error', '').lower())

    def test_disbanded_group_rejects(self):
        group = Group.objects.create(name='Disbanded', join_policy='open')
        group.disbanded_at = timezone.now()
        group.save()
        response = self.client.post(f'/groups/{group.slug}/join/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('disbanded', response.context.get('error', '').lower())

    def test_already_member_redirects(self):
        group = Group.objects.create(name='Joined', join_policy='open')
        GroupMembership.objects.create(user=self.user, group=group)
        response = self.client.post(f'/groups/{group.slug}/join/')
        self.assertEqual(response.status_code, 302)

    def test_duplicate_request_ignored(self):
        group = Group.objects.create(name='ReqDup', join_policy='request')
        GroupJoinRequest.objects.create(
            user=self.user, group=group,
            expires_at=timezone.now() + timedelta(days=7),
        )
        response = self.client.post(f'/groups/{group.slug}/join/')
        self.assertEqual(GroupJoinRequest.objects.filter(
            user=self.user, group=group, status='pending',
        ).count(), 1)


@tag("unit")
class GroupLeaveViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='leaver', password='p')
        cls.group = Group.objects.create(name='Leave')
        GroupMembership.objects.create(user=cls.user, group=cls.group, role='member')

    def setUp(self):
        self.client.login(username='leaver', password='p')

    def test_regular_member_leaves(self):
        response = self.client.post(f'/groups/{self.group.slug}/leave/')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(GroupMembership.objects.filter(
            user=self.user, group=self.group,
        ).exists())

    def test_admin_with_other_admins_leaves(self):
        GroupMembership.objects.filter(user=self.user, group=self.group).update(role='admin')
        other_admin = User.objects.create_user(username='otheradmin', password='p')
        GroupMembership.objects.create(user=other_admin, group=self.group, role='admin')
        response = self.client.post(f'/groups/{self.group.slug}/leave/')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(GroupMembership.objects.filter(
            user=self.user, group=self.group,
        ).exists())

    def test_last_admin_gets_successor_prompt(self):
        GroupMembership.objects.filter(user=self.user, group=self.group).update(role='admin')
        member = User.objects.create_user(username='member2', password='p')
        GroupMembership.objects.create(user=member, group=self.group, role='member')
        response = self.client.get(f'/groups/{self.group.slug}/leave/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['needs_successor'])

    def test_last_admin_transfers_and_leaves(self):
        GroupMembership.objects.filter(user=self.user, group=self.group).update(role='admin')
        member = User.objects.create_user(username='member2', password='p')
        m = GroupMembership.objects.create(user=member, group=self.group, role='member')
        response = self.client.post(f'/groups/{self.group.slug}/leave/', {
            'successor': member.pk,
        })
        self.assertEqual(response.status_code, 302)
        m.refresh_from_db()
        self.assertEqual(m.role, 'admin')
        self.assertFalse(GroupMembership.objects.filter(
            user=self.user, group=self.group,
        ).exists())

    def test_last_member_triggers_grace_period(self):
        response = self.client.post(f'/groups/{self.group.slug}/leave/')
        self.group.refresh_from_db()
        self.assertIsNotNone(self.group.disbanded_at)

    def test_leave_cleans_upcoming_votes_and_rsvps(self):
        event = Event.objects.create(
            title='Upcoming',
            date=timezone.now() + timedelta(days=7),
            voting_deadline=timezone.now() + timedelta(days=7),
            created_by=self.user,
            group=self.group,
        )
        EventAttendance.objects.create(user=self.user, event=event)
        game = BoardGame.objects.create(name='G1', owner=self.user)
        Vote.objects.create(user=self.user, event=event, board_game=game, rank=1)
        self.client.post(f'/groups/{self.group.slug}/leave/')
        self.assertFalse(EventAttendance.objects.filter(user=self.user).exists())
        self.assertFalse(Vote.objects.filter(user=self.user).exists())


@tag("unit")
class GroupJoinRequestManageViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username='admin', password='p')
        cls.group = Group.objects.create(name='ReqManage', join_policy='request')
        GroupMembership.objects.create(user=cls.admin, group=cls.group, role='admin')

    def setUp(self):
        self.client.login(username='admin', password='p')

    def test_admin_can_access(self):
        response = self.client.get(f'/groups/{self.group.slug}/join-requests/')
        self.assertEqual(response.status_code, 200)

    def test_non_admin_denied(self):
        member = User.objects.create_user(username='member', password='p')
        GroupMembership.objects.create(user=member, group=self.group)
        self.client.login(username='member', password='p')
        response = self.client.get(f'/groups/{self.group.slug}/join-requests/')
        self.assertEqual(response.status_code, 403)

    def test_approve_creates_membership(self):
        requester = User.objects.create_user(username='requester', password='p')
        jr = GroupJoinRequest.objects.create(
            user=requester, group=self.group,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.post(f'/groups/{self.group.slug}/join-requests/', {
            'request_id': jr.pk,
            'action': 'approve',
        })
        self.assertTrue(GroupMembership.objects.filter(
            user=requester, group=self.group,
        ).exists())
        jr.refresh_from_db()
        self.assertEqual(jr.status, 'approved')

    def test_reject_sets_status(self):
        requester = User.objects.create_user(username='requester2', password='p')
        jr = GroupJoinRequest.objects.create(
            user=requester, group=self.group,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.post(f'/groups/{self.group.slug}/join-requests/', {
            'request_id': jr.pk,
            'action': 'reject',
        })
        jr.refresh_from_db()
        self.assertEqual(jr.status, 'rejected')
        self.assertFalse(GroupMembership.objects.filter(
            user=requester, group=self.group,
        ).exists())

    def test_full_group_on_approval(self):
        self.group.max_members = 1
        self.group.save()
        requester = User.objects.create_user(username='requester3', password='p')
        jr = GroupJoinRequest.objects.create(
            user=requester, group=self.group,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.post(f'/groups/{self.group.slug}/join-requests/', {
            'request_id': jr.pk,
            'action': 'approve',
        })
        jr.refresh_from_db()
        self.assertEqual(jr.status, 'pending')

    def test_expired_requests_hidden(self):
        requester = User.objects.create_user(username='expired', password='p')
        GroupJoinRequest.objects.create(
            user=requester, group=self.group,
            expires_at=timezone.now() - timedelta(days=1),
        )
        response = self.client.get(f'/groups/{self.group.slug}/join-requests/')
        self.assertEqual(len(response.context['requests']), 0)


@tag("unit")
class GroupInviteCreateViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username='admin', password='p')
        cls.group = Group.objects.create(name='InviteGroup')
        GroupMembership.objects.create(user=cls.admin, group=cls.group, role='admin')

    def setUp(self):
        self.client.login(username='admin', password='p')

    def test_admin_can_access(self):
        response = self.client.get(f'/groups/{self.group.slug}/invite/')
        self.assertEqual(response.status_code, 200)

    def test_non_admin_denied(self):
        member = User.objects.create_user(username='member', password='p')
        GroupMembership.objects.create(user=member, group=self.group)
        self.client.login(username='member', password='p')
        response = self.client.get(f'/groups/{self.group.slug}/invite/')
        self.assertEqual(response.status_code, 403)

    def test_generate_invite(self):
        response = self.client.post(f'/groups/{self.group.slug}/invite/')
        self.assertEqual(response.status_code, 200)
        invite = response.context['invite']
        self.assertIsNotNone(invite)
        self.assertEqual(invite.group, self.group)
        self.assertFalse(invite.used)
        self.assertEqual(invite.created_by, self.admin)

    def test_invite_expires_in_7_days(self):
        self.client.post(f'/groups/{self.group.slug}/invite/')
        invite = GroupInvite.objects.filter(group=self.group).latest('created_at')
        self.assertGreater(invite.expires_at, timezone.now() + timedelta(days=6))

    def test_disbanded_group_returns_403(self):
        self.group.disbanded_at = timezone.now()
        self.group.save()
        response = self.client.get(f'/groups/{self.group.slug}/invite/')
        self.assertEqual(response.status_code, 403)


@tag("unit")
class GroupInviteAcceptViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username='admin', password='p')
        cls.group = Group.objects.create(name='InviteAccept')
        GroupMembership.objects.create(user=cls.admin, group=cls.group, role='admin')
        cls.invite = GroupInvite.objects.create(
            group=cls.group,
            created_by=cls.admin,
            expires_at=timezone.now() + timedelta(days=7),
        )

    def test_valid_invite_creates_membership(self):
        user = User.objects.create_user(username='joinee', password='p')
        self.client.login(username='joinee', password='p')
        response = self.client.get(f'/invite/{self.invite.token}/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(GroupMembership.objects.filter(
            user=user, group=self.group,
        ).exists())

    def test_expired_invite_shows_error(self):
        self.invite.expires_at = timezone.now() - timedelta(days=1)
        self.invite.save()
        user = User.objects.create_user(username='late', password='p')
        self.client.login(username='late', password='p')
        response = self.client.get(f'/invite/{self.invite.token}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('expired', response.context['error'].lower())

    def test_used_invite_shows_error(self):
        self.invite.used = True
        self.invite.save()
        user = User.objects.create_user(username='late2', password='p')
        self.client.login(username='late2', password='p')
        response = self.client.get(f'/invite/{self.invite.token}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('already been used', response.context['error'])

    def test_full_group_shows_error(self):
        self.group.max_members = 1
        self.group.save()
        user = User.objects.create_user(username='fulluser', password='p')
        self.client.login(username='fulluser', password='p')
        response = self.client.get(f'/invite/{self.invite.token}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('maximum', response.context['error'].lower())

    def test_invalid_token_shows_generic_error(self):
        response = self.client.get('/invite/badtoken/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('invalid', response.context['error'].lower())

    def test_invalid_token_does_not_leak_group(self):
        response = self.client.get('/invite/badtoken/')
        self.assertNotIn('group', response.context)

    def test_disbanded_group_invite_rejected(self):
        self.group.disbanded_at = timezone.now()
        self.group.save()
        user = User.objects.create_user(username='disbandeduser', password='p')
        self.client.login(username='disbandeduser', password='p')
        response = self.client.get(f'/invite/{self.invite.token}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('disbanded', response.context['error'].lower())

    def test_unauthenticated_redirected_to_login(self):
        response = self.client.get(f'/invite/{self.invite.token}/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_already_member_shows_error(self):
        user = User.objects.create_user(username='already', password='p')
        GroupMembership.objects.create(user=user, group=self.group)
        self.client.login(username='already', password='p')
        response = self.client.get(f'/invite/{self.invite.token}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('already a member', response.context['error'].lower())
