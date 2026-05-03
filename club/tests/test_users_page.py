from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from club.models import (
    Block,
    Event,
    EventAttendance,
    Friendship,
    Group,
    GroupMembership,
    Notification,
)

User = get_user_model()


def _create_users(*usernames, password='testpass123', **kwargs):
    return [User.objects.create_user(username=u, password=password, **kwargs) for u in usernames]


def _create_verified_user(username, password='testpass123', **kwargs):
    return User.objects.create_user(
        username=username, password=password,
        email_verified=True, email=f'{username}@test.com', **kwargs,
    )


# ---------------------------------------------------------------------------
# Users page access tests
# ---------------------------------------------------------------------------

@tag("integration")
class UsersPageAccessTest(TestCase):

    def test_authenticated_user_can_access(self):
        user = _create_verified_user('alice')
        self.client.force_login(user)
        resp = self.client.get(reverse('users_page'))
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_redirected_to_login(self):
        resp = self.client.get(reverse('users_page'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_default_tab_is_friends(self):
        user = _create_verified_user('alice')
        self.client.force_login(user)
        resp = self.client.get(reverse('users_page'))
        self.assertEqual(resp.context['tab'], 'friends')


# ---------------------------------------------------------------------------
# All Users tab tests
# ---------------------------------------------------------------------------

@tag("integration")
class AllUsersTabTest(TestCase):

    def setUp(self):
        self.user = _create_verified_user('alice')
        for i in range(30):
            _create_verified_user(f'user{i:02d}')

    def test_verified_user_sees_user_list(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['page_obj'].paginator.count > 0)

    def test_unverified_user_sees_gate_message(self):
        unverified = User.objects.create_user(username='unverified', password='testpass123')
        self.client.force_login(unverified)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        self.assertContains(resp, 'Become verified')

    def test_search_filters_by_username(self):
        _create_verified_user('bob_jones')
        _create_verified_user('bob_smith')
        _create_verified_user('carol')
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all&q=bob')
        for u in resp.context['page_obj'].object_list:
            self.assertIn('bob', u.username.lower())

    def test_pagination_25_per_page(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        self.assertEqual(len(resp.context['page_obj'].object_list), 25)

    def test_second_page_exists(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all&page=2')
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(len(resp.context['page_obj'].object_list), 0)

    def test_blocked_users_excluded(self):
        other = _create_verified_user('blocked_user')
        Block.objects.create(blocker=self.user, blocked=other)
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertNotIn('blocked_user', usernames)

    def test_soft_deleted_users_excluded(self):
        deleted = _create_verified_user('deleted_user')
        deleted.deleted_at = timezone.now()
        deleted.save()
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertNotIn('deleted_user', usernames)

    def test_self_excluded(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertNotIn('alice', usernames)

    def test_superuser_excluded_from_list(self):
        User.objects.create_superuser(username='sysop', password='SysPass123!')
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertNotIn('sysop', usernames)

    def test_superuser_excluded_from_search(self):
        User.objects.create_superuser(username='sysop', password='SysPass123!')
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all&q=sysop')
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertNotIn('sysop', usernames)

    def test_verified_badge_shown_for_verified_users(self):
        _create_verified_user('verified_bob')
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all&q=verified_bob')
        self.assertContains(resp, 'verified-badge')


# ---------------------------------------------------------------------------
# Superuser profile hidden
# ---------------------------------------------------------------------------

@tag("integration")
class SuperuserProfileHiddenTest(TestCase):

    def test_superuser_profile_returns_404(self):
        User.objects.create_superuser(username='sysop', password='SysPass123!')
        user = _create_verified_user('alice')
        self.client.force_login(user)
        resp = self.client.get(reverse('public_profile', kwargs={'username': 'sysop'}))
        self.assertEqual(resp.status_code, 404)

    def test_superuser_profile_redirects_for_anonymous(self):
        User.objects.create_superuser(username='sysop', password='SysPass123!')
        resp = self.client.get(reverse('public_profile', kwargs={'username': 'sysop'}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_superuser_can_view_own_profile(self):
        su = User.objects.create_superuser(username='sysop', password='SysPass123!')
        self.client.force_login(su)
        resp = self.client.get(reverse('public_profile', kwargs={'username': 'sysop'}))
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# All Users tab - old user search redirect
# ---------------------------------------------------------------------------

@tag("integration")
class UserSearchRedirectTest(TestCase):

    def test_old_search_url_redirects(self):
        user = _create_verified_user('alice')
        self.client.force_login(user)
        resp = self.client.get('/users/search/?q=bob')
        self.assertEqual(resp.status_code, 301)


# ---------------------------------------------------------------------------
# Friends tab - current friends
# ---------------------------------------------------------------------------

@tag("integration")
class FriendsTabCurrentFriendsTest(TestCase):

    def setUp(self):
        self.user = _create_verified_user('alice')
        self.friend1 = _create_verified_user('bob')
        self.friend2 = _create_verified_user('carol')
        Friendship.objects.create(requester=self.user, receiver=self.friend1, status='accepted')
        Friendship.objects.create(requester=self.friend2, receiver=self.user, status='accepted')

    def test_shows_current_friends(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        friend_usernames = [f.username for f in resp.context['friends']]
        self.assertIn('bob', friend_usernames)
        self.assertIn('carol', friend_usernames)

    def test_shows_mutual_groups(self):
        group = Group.objects.create(name='Test Group', slug='test-group', created_by=self.user)
        GroupMembership.objects.create(user=self.user, group=group, role='member')
        GroupMembership.objects.create(user=self.friend1, group=group, role='member')
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'Test Group')

    def test_shows_shared_upcoming_private_events(self):
        event = Event.objects.create(
            title='Game Night',
            date=timezone.now() + timedelta(days=7),
            created_by=self.user,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        EventAttendance.objects.create(user=self.user, event=event)
        EventAttendance.objects.create(user=self.friend1, event=event)
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'Game Night')

    def test_does_not_show_group_events_in_shared_events(self):
        group = Group.objects.create(name='G', slug='g', created_by=self.user)
        event = Event.objects.create(
            title='Group Event',
            date=timezone.now() + timedelta(days=7),
            created_by=self.user,
            group=group,
            voting_deadline=timezone.now() + timedelta(days=6),
        )
        EventAttendance.objects.create(user=self.user, event=event)
        EventAttendance.objects.create(user=self.friend1, event=event)
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        friend_shared_events = resp.context['friends_shared_events']
        self.assertNotIn('bob', {k: v for k, v in friend_shared_events.items()})

    def test_no_friends_shows_empty_state(self):
        solo = _create_verified_user('solo')
        self.client.force_login(solo)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'No friends yet')

    def test_unfriend_button_present(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'Unfriend')


# ---------------------------------------------------------------------------
# Friends tab - pending received requests
# ---------------------------------------------------------------------------

@tag("integration")
class FriendsTabPendingReceivedTest(TestCase):

    def setUp(self):
        self.user = _create_verified_user('alice')
        self.sender = _create_verified_user('bob')
        Friendship.objects.create(requester=self.sender, receiver=self.user, status='pending')

    def test_shows_pending_received_requests(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        pending = resp.context['pending_received']
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].requester.username, 'bob')

    def test_shows_mutual_groups_on_pending(self):
        group = Group.objects.create(name='Test Group', slug='test-group', created_by=self.user)
        GroupMembership.objects.create(user=self.user, group=group, role='member')
        GroupMembership.objects.create(user=self.sender, group=group, role='member')
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'Test Group')

    def test_accept_decline_buttons_present(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'friend-accept-btn')
        self.assertContains(resp, 'friend-decline-btn')

    def test_no_pending_shows_empty_state(self):
        solo = _create_verified_user('solo')
        self.client.force_login(solo)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'No pending friend requests')


# ---------------------------------------------------------------------------
# Friends tab - sent requests
# ---------------------------------------------------------------------------

@tag("integration")
class FriendsTabSentRequestsTest(TestCase):

    def setUp(self):
        self.user = _create_verified_user('alice')
        self.target = _create_verified_user('bob')
        Friendship.objects.create(requester=self.user, receiver=self.target, status='pending')

    def test_shows_sent_requests(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        sent = resp.context['sent_requests']
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0].receiver.username, 'bob')

    def test_cancel_button_present(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'Cancel')

    def test_no_sent_shows_empty_state(self):
        solo = _create_verified_user('solo')
        self.client.force_login(solo)
        resp = self.client.get(reverse('users_page') + '?tab=friends')
        self.assertContains(resp, 'No sent friend requests')


# ---------------------------------------------------------------------------
# Unfriend from users page
# ---------------------------------------------------------------------------

@tag("integration")
class UnfriendFromUsersPageTest(TestCase):

    def setUp(self):
        self.user = _create_verified_user('alice')
        self.friend = _create_verified_user('bob')
        Friendship.objects.create(requester=self.user, receiver=self.friend, status='accepted')

    def test_unfriend_success(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse('remove_friend', kwargs={'username': 'bob'}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Friendship.objects.filter(pk__isnull=False).exists())

    def test_unfriend_non_friend_forbidden(self):
        other = _create_verified_user('carol')
        self.client.force_login(other)
        resp = self.client.post(reverse('remove_friend', kwargs={'username': 'bob'}))
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# Unverified friend request rate limit tests
# ---------------------------------------------------------------------------

@tag("unit")
class UnverifiedFriendRequestRateLimitTest(TestCase):

    def setUp(self):
        self.unverified = User.objects.create_user(
            username='unverified', password='testpass123',
        )

    def test_unverified_can_send_up_to_3_pending(self):
        targets = _create_users('target1', 'target2', 'target3')
        for t in targets:
            self.assertTrue(Friendship.can_send_request(self.unverified, t))
            Friendship.objects.create(requester=self.unverified, receiver=t, status='pending')

    def test_unverified_blocked_on_4th_pending(self):
        targets = _create_users('target1', 'target2', 'target3', 'target4')
        for t in targets[:3]:
            Friendship.objects.create(requester=self.unverified, receiver=t, status='pending')
        self.assertFalse(Friendship.can_send_request(self.unverified, targets[3]))

    def test_verified_user_not_limited(self):
        verified = _create_verified_user('verified_user')
        targets = _create_users('target1', 'target2', 'target3', 'target4')
        for t in targets[:3]:
            Friendship.objects.create(requester=verified, receiver=t, status='pending')
        self.assertTrue(Friendship.can_send_request(verified, targets[3]))

    def test_accepting_frees_up_slot(self):
        targets = _create_users('target1', 'target2', 'target3', 'target4')
        for t in targets[:3]:
            Friendship.objects.create(requester=self.unverified, receiver=t, status='pending')
        Friendship.objects.filter(requester=self.unverified, receiver=targets[0]).update(status='accepted')
        self.assertTrue(Friendship.can_send_request(self.unverified, targets[3]))

    def test_declining_frees_up_slot(self):
        targets = _create_users('target1', 'target2', 'target3', 'target4')
        for t in targets[:3]:
            Friendship.objects.create(requester=self.unverified, receiver=t, status='pending')
        Friendship.objects.filter(requester=self.unverified, receiver=targets[0]).update(status='declined')
        self.assertTrue(Friendship.can_send_request(self.unverified, targets[3]))

    def test_unverified_still_subject_to_decline_cooldown(self):
        target = _create_users('target1')[0]
        Friendship.objects.create(
            requester=self.unverified, receiver=target,
            status='declined', decline_count=2, last_declined_at=timezone.now(),
        )
        self.assertFalse(Friendship.can_send_request(self.unverified, target))


# ---------------------------------------------------------------------------
# Unverified friend request rate limit - view tests
# ---------------------------------------------------------------------------

@tag("integration")
class UnverifiedFriendRequestViewTest(TestCase):

    def setUp(self):
        self.unverified = User.objects.create_user(
            username='unverified', password='testpass123',
        )

    def test_send_request_blocked_at_limit(self):
        targets = _create_users('t1', 't2', 't3', 't4')
        for t in targets[:3]:
            Friendship.objects.create(requester=self.unverified, receiver=t, status='pending')
        self.client.force_login(self.unverified)
        resp = self.client.post(reverse('send_friend_request', kwargs={'username': 't4'}))
        self.assertFalse(Friendship.objects.filter(requester=self.unverified, receiver=targets[3], status='pending').exists())

    def test_send_request_works_under_limit(self):
        targets = _create_users('t1', 't2')
        Friendship.objects.create(requester=self.unverified, receiver=targets[0], status='pending')
        self.client.force_login(self.unverified)
        resp = self.client.post(reverse('send_friend_request', kwargs={'username': 't2'}))
        self.assertTrue(Friendship.objects.filter(requester=self.unverified, receiver=targets[1], status='pending').exists())


# ---------------------------------------------------------------------------
# Users page nav link
# ---------------------------------------------------------------------------

@tag("integration")
class UsersNavLinkTest(TestCase):

    def test_nav_shows_users_link_when_authenticated(self):
        user = _create_verified_user('alice')
        self.client.force_login(user)
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, reverse('users_page'))

    def test_nav_hides_users_link_when_unauthenticated(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertNotContains(resp, reverse('users_page'))
