from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from club.models import Friendship, Notification

User = get_user_model()


def _create_users(*usernames, password='testpass123'):
    return [User.objects.create_user(username=u, password=password) for u in usernames]


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

@tag("unit")
class FriendshipModelTest(TestCase):

    def test_create_pending_friendship(self):
        a, b = _create_users('alice', 'bob')
        f = Friendship.objects.create(requester=a, receiver=b)
        self.assertEqual(f.status, 'pending')
        self.assertEqual(str(f), 'alice -> bob (pending)')

    def test_unique_constraint_prevents_duplicate(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b)
        with self.assertRaises(IntegrityError):
            Friendship.objects.create(requester=a, receiver=b)

    def test_reverse_pair_is_allowed(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b)
        f2 = Friendship.objects.create(requester=b, receiver=a)
        self.assertEqual(f2.status, 'pending')

    def test_accept_sets_status(self):
        a, b = _create_users('alice', 'bob')
        f = Friendship.objects.create(requester=a, receiver=b)
        f.status = 'accepted'
        f.save()
        f.refresh_from_db()
        self.assertEqual(f.status, 'accepted')

    def test_decline_increments_counter(self):
        a, b = _create_users('alice', 'bob')
        f = Friendship.objects.create(requester=a, receiver=b)
        f.status = 'declined'
        f.decline_count = 1
        f.last_declined_at = timezone.now()
        f.save()
        f.refresh_from_db()
        self.assertEqual(f.status, 'declined')
        self.assertEqual(f.decline_count, 1)
        self.assertIsNotNone(f.last_declined_at)

    def test_cascade_on_user_delete(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b)
        a.delete()
        self.assertEqual(Friendship.objects.count(), 0)

    def test_are_friends_utility(self):
        a, b = _create_users('alice', 'bob')
        self.assertFalse(Friendship.are_friends(a, b))
        Friendship.objects.create(requester=a, receiver=b, status='accepted')
        self.assertTrue(Friendship.are_friends(a, b))
        self.assertTrue(Friendship.are_friends(b, a))

    def test_are_friends_returns_false_for_pending(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b, status='pending')
        self.assertFalse(Friendship.are_friends(a, b))

    def test_get_friendship_returns_correct_record(self):
        a, b = _create_users('alice', 'bob')
        f = Friendship.objects.create(requester=a, receiver=b)
        result = Friendship.get_friendship(a, b)
        self.assertEqual(result, f)
        result2 = Friendship.get_friendship(b, a)
        self.assertEqual(result2, f)

    def test_get_friendship_returns_none_when_none_exists(self):
        a, b = _create_users('alice', 'bob')
        self.assertIsNone(Friendship.get_friendship(a, b))

    def test_can_send_request_no_previous(self):
        a, b = _create_users('alice', 'bob')
        self.assertTrue(Friendship.can_send_request(a, b))

    def test_can_send_request_under_limit(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(
            requester=a, receiver=b, status='declined',
            decline_count=1, last_declined_at=timezone.now(),
        )
        self.assertTrue(Friendship.can_send_request(a, b))

    def test_can_send_request_at_limit(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(
            requester=a, receiver=b, status='declined',
            decline_count=2, last_declined_at=timezone.now(),
        )
        self.assertFalse(Friendship.can_send_request(a, b))

    def test_can_send_request_old_declines_expire(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(
            requester=a, receiver=b, status='declined',
            decline_count=2, last_declined_at=timezone.now() - timedelta(hours=169),
        )
        self.assertTrue(Friendship.can_send_request(a, b))

    def test_can_send_request_directional(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(
            requester=a, receiver=b, status='declined',
            decline_count=2, last_declined_at=timezone.now(),
        )
        self.assertTrue(Friendship.can_send_request(b, a))

    def test_can_send_request_accepted_blocks(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b, status='accepted')
        self.assertFalse(Friendship.can_send_request(a, b))

    def test_can_send_request_pending_blocks(self):
        a, b = _create_users('alice', 'bob')
        Friendship.objects.create(requester=a, receiver=b, status='pending')
        self.assertFalse(Friendship.can_send_request(a, b))

    def test_can_send_request_self_blocked(self):
        a = _create_users('alice')[0]
        self.assertFalse(Friendship.can_send_request(a, a))

    def test_get_friends_of_user(self):
        a, b, c, d = _create_users('alice', 'bob', 'carol', 'dave')
        Friendship.objects.create(requester=a, receiver=b, status='accepted')
        Friendship.objects.create(requester=c, receiver=a, status='accepted')
        Friendship.objects.create(requester=c, receiver=d, status='accepted')
        friends = Friendship.get_friends_of(a)
        self.assertEqual(set(friends), {b, c})

    def test_get_friends_of_user_no_friends(self):
        a = _create_users('alice')[0]
        friends = Friendship.get_friends_of(a)
        self.assertEqual(list(friends), [])


# ---------------------------------------------------------------------------
# View tests — Send friend request
# ---------------------------------------------------------------------------

@tag("integration")
class SendFriendRequestViewTest(TestCase):

    def setUp(self):
        self.a, self.b = _create_users('alice', 'bob')

    def test_send_request_success(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(reverse('send_friend_request', kwargs={'username': 'bob'}))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Friendship.objects.filter(requester=self.a, receiver=self.b, status='pending').exists())

    def test_send_request_shows_toast(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(reverse('send_friend_request', kwargs={'username': 'bob'}), follow=True)
        self.assertContains(resp, 'Friend request sent to bob')

    def test_send_request_creates_notification(self):
        self.client.login(username='alice', password='testpass123')
        self.client.post(reverse('send_friend_request', kwargs={'username': 'bob'}))
        notif = Notification.objects.get(user=self.b, notification_type='friend_request')
        self.assertIn('alice', notif.message)

    def test_send_request_to_self_fails(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(reverse('send_friend_request', kwargs={'username': 'alice'}))
        self.assertEqual(resp.status_code, 403)

    def test_send_request_duplicate_fails(self):
        Friendship.objects.create(requester=self.a, receiver=self.b)
        self.client.login(username='alice', password='testpass123')
        self.client.post(reverse('send_friend_request', kwargs={'username': 'bob'}))
        self.assertEqual(Friendship.objects.count(), 1)

    def test_send_request_rate_limited(self):
        Friendship.objects.create(
            requester=self.a, receiver=self.b, status='declined',
            decline_count=2, last_declined_at=timezone.now(),
        )
        self.client.login(username='alice', password='testpass123')
        self.client.post(reverse('send_friend_request', kwargs={'username': 'bob'}))
        self.assertFalse(Friendship.objects.filter(status='pending').exists())

    def test_send_request_resends_after_one_decline(self):
        Friendship.objects.create(
            requester=self.a, receiver=self.b, status='declined',
            decline_count=1, last_declined_at=timezone.now(),
        )
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(reverse('send_friend_request', kwargs={'username': 'bob'}))
        self.assertEqual(resp.status_code, 302)
        f = Friendship.objects.get(requester=self.a, receiver=self.b)
        self.assertEqual(f.status, 'pending')

    def test_send_request_requires_login(self):
        resp = self.client.post(reverse('send_friend_request', kwargs={'username': 'bob'}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_send_request_nonexistent_user_404(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(reverse('send_friend_request', kwargs={'username': 'nobody'}))
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# View tests — Accept friend request
# ---------------------------------------------------------------------------

@tag("integration")
class AcceptFriendRequestViewTest(TestCase):

    def setUp(self):
        self.a, self.b = _create_users('alice', 'bob')
        self.friendship = Friendship.objects.create(requester=self.a, receiver=self.b)

    def test_accept_success(self):
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(reverse('accept_friend_request', kwargs={'pk': self.friendship.pk}))
        self.assertEqual(resp.status_code, 302)
        self.friendship.refresh_from_db()
        self.assertEqual(self.friendship.status, 'accepted')

    def test_accept_creates_notification_for_requester(self):
        self.client.login(username='bob', password='testpass123')
        self.client.post(reverse('accept_friend_request', kwargs={'pk': self.friendship.pk}))
        notif = Notification.objects.get(user=self.a, notification_type='friend_request_accepted')
        self.assertIn('bob', notif.message)

    def test_accept_by_wrong_user_forbidden(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(reverse('accept_friend_request', kwargs={'pk': self.friendship.pk}))
        self.assertEqual(resp.status_code, 403)

    def test_accept_non_pending_forbidden(self):
        self.friendship.status = 'accepted'
        self.friendship.save()
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(reverse('accept_friend_request', kwargs={'pk': self.friendship.pk}))
        self.assertEqual(resp.status_code, 403)

    def test_accept_requires_login(self):
        resp = self.client.post(reverse('accept_friend_request', kwargs={'pk': self.friendship.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_accept_get_redirects(self):
        self.client.login(username='bob', password='testpass123')
        resp = self.client.get(reverse('accept_friend_request', kwargs={'pk': self.friendship.pk}))
        self.assertEqual(resp.status_code, 302)


# ---------------------------------------------------------------------------
# View tests — Decline friend request
# ---------------------------------------------------------------------------

@tag("integration")
class DeclineFriendRequestViewTest(TestCase):

    def setUp(self):
        self.a, self.b = _create_users('alice', 'bob')
        self.friendship = Friendship.objects.create(requester=self.a, receiver=self.b)

    def test_decline_success(self):
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(reverse('decline_friend_request', kwargs={'pk': self.friendship.pk}))
        self.assertEqual(resp.status_code, 302)
        self.friendship.refresh_from_db()
        self.assertEqual(self.friendship.status, 'declined')
        self.assertEqual(self.friendship.decline_count, 1)
        self.assertIsNotNone(self.friendship.last_declined_at)

    def test_decline_creates_notification_for_requester(self):
        self.client.login(username='bob', password='testpass123')
        self.client.post(reverse('decline_friend_request', kwargs={'pk': self.friendship.pk}))
        notif = Notification.objects.get(user=self.a, notification_type='friend_request_declined')
        self.assertIn('bob', notif.message)

    def test_decline_by_wrong_user_forbidden(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(reverse('decline_friend_request', kwargs={'pk': self.friendship.pk}))
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# View tests — Cancel friend request
# ---------------------------------------------------------------------------

@tag("integration")
class CancelFriendRequestViewTest(TestCase):

    def setUp(self):
        self.a, self.b = _create_users('alice', 'bob')

    def test_cancel_success(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(reverse('cancel_friend_request', kwargs={'pk': friendship.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Friendship.objects.filter(pk=friendship.pk).exists())

    def test_cancel_by_wrong_user_forbidden(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(reverse('cancel_friend_request', kwargs={'pk': friendship.pk}))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Friendship.objects.filter(pk=friendship.pk).exists())

    def test_cancel_accepted_request_forbidden(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b, status='accepted')
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(reverse('cancel_friend_request', kwargs={'pk': friendship.pk}))
        self.assertEqual(resp.status_code, 403)

    def test_cancel_deletes_notification(self):
        self.client.login(username='alice', password='testpass123')
        self.client.post(reverse('send_friend_request', kwargs={'username': 'bob'}))
        friendship = Friendship.objects.get(requester=self.a, receiver=self.b)
        self.assertTrue(Notification.objects.filter(
            user=self.b,
            notification_type='friend_request',
            url=f'/profile/{self.a.username}/',
        ).exists())
        self.client.post(reverse('cancel_friend_request', kwargs={'pk': friendship.pk}))
        self.assertFalse(Notification.objects.filter(
            user=self.b,
            notification_type='friend_request',
            url=f'/profile/{self.a.username}/',
        ).exists())


# ---------------------------------------------------------------------------
# View tests — Unfriend
# ---------------------------------------------------------------------------

@tag("integration")
class UnfriendViewTest(TestCase):

    def setUp(self):
        self.a, self.b = _create_users('alice', 'bob')
        self.friendship = Friendship.objects.create(requester=self.a, receiver=self.b, status='accepted')

    def test_unfriend_success(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(reverse('remove_friend', kwargs={'username': 'bob'}))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Friendship.objects.filter(pk=self.friendship.pk).exists())

    def test_unfriend_by_non_friend_fails(self):
        c = User.objects.create_user(username='carol', password='testpass123')
        self.client.login(username='carol', password='testpass123')
        resp = self.client.post(reverse('remove_friend', kwargs={'username': 'bob'}))
        self.assertEqual(resp.status_code, 403)

    def test_unfriend_nonexistent_user_404(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(reverse('remove_friend', kwargs={'username': 'nobody'}))
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# View tests — Profile friend button context
# ---------------------------------------------------------------------------

@tag("integration")
class ProfileFriendButtonTest(TestCase):

    def setUp(self):
        self.a, self.b = _create_users('alice', 'bob')

    def test_profile_shows_add_friend_when_no_relationship(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(reverse('public_profile', kwargs={'username': 'bob'}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['friend_status'], 'none')

    def test_profile_shows_pending_sent(self):
        Friendship.objects.create(requester=self.a, receiver=self.b)
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(reverse('public_profile', kwargs={'username': 'bob'}))
        self.assertEqual(resp.context['friend_status'], 'pending_sent')

    def test_profile_shows_pending_received(self):
        Friendship.objects.create(requester=self.b, receiver=self.a)
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(reverse('public_profile', kwargs={'username': 'bob'}))
        self.assertEqual(resp.context['friend_status'], 'pending_received')

    def test_profile_shows_friends(self):
        Friendship.objects.create(requester=self.a, receiver=self.b, status='accepted')
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(reverse('public_profile', kwargs={'username': 'bob'}))
        self.assertEqual(resp.context['friend_status'], 'friends')

    def test_own_profile_no_friend_status(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(reverse('public_profile', kwargs={'username': 'alice'}))
        self.assertIsNone(resp.context.get('friend_status'))


# ---------------------------------------------------------------------------
# View tests — User search
# ---------------------------------------------------------------------------

@tag("integration")
class UserSearchViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='testpass123')
        User.objects.create_user(username='bob123', password='testpass123')
        User.objects.create_user(username='bobsmith', password='testpass123')
        User.objects.create_user(username='carol', password='testpass123')

    def test_search_partial_match(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(reverse('user_search') + '?q=bob')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['results']), 2)

    def test_search_case_insensitive(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(reverse('user_search') + '?q=BOB')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['results']), 2)

    def test_search_excludes_self(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(reverse('user_search') + '?q=ali')
        self.assertEqual(resp.status_code, 200)
        usernames = [u.username for u in resp.context['results']]
        self.assertNotIn('alice', usernames)

    def test_search_limits_to_20(self):
        for i in range(25):
            User.objects.create_user(username=f'user{i:02d}', password='testpass123')
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(reverse('user_search') + '?q=user')
        self.assertEqual(len(resp.context['results']), 20)

    def test_search_no_query_shows_empty(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(reverse('user_search'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['results']), 0)

    def test_search_requires_login(self):
        resp = self.client.get(reverse('user_search'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_search_shows_verified_icon_for_verified_user(self):
        bob = User.objects.get(username='bob123')
        bob.email_verified = True
        bob.save()
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(reverse('user_search') + '?q=bob')
        self.assertContains(resp, 'verified-badge')


# ---------------------------------------------------------------------------
# View tests — Friends list on profile
# ---------------------------------------------------------------------------

@tag("integration")
class FriendsListOnProfileTest(TestCase):

    def setUp(self):
        self.a, self.b, self.c = _create_users('alice', 'bob', 'carol')
        Friendship.objects.create(requester=self.a, receiver=self.b, status='accepted')
        Friendship.objects.create(requester=self.c, receiver=self.a, status='accepted')

    def test_friends_list_shows_friends(self):
        self.client.login(username='alice', password='testpass123')
        resp = self.client.get(reverse('friends_list', kwargs={'username': 'alice'}))
        self.assertEqual(resp.status_code, 200)
        friends_usernames = [u.username for u in resp.context['friends']]
        self.assertIn('bob', friends_usernames)
        self.assertIn('carol', friends_usernames)

    def test_friends_list_visible_to_other_users(self):
        self.client.login(username='bob', password='testpass123')
        resp = self.client.get(reverse('friends_list', kwargs={'username': 'alice'}))
        self.assertEqual(resp.status_code, 200)
        friends_usernames = [u.username for u in resp.context['friends']]
        self.assertIn('carol', friends_usernames)

    def test_friends_list_requires_login(self):
        resp = self.client.get(reverse('friends_list', kwargs={'username': 'alice'}))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)


# ---------------------------------------------------------------------------
# View tests — Inline friend request actions on notification list
# ---------------------------------------------------------------------------

@tag("integration")
class FriendRequestInlineNotificationTest(TestCase):

    def setUp(self):
        self.a, self.b = _create_users('alice', 'bob')

    def test_friend_request_notification_shows_accept_decline(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        Notification.objects.create(
            user=self.b,
            message=f'{self.a.username} sent you a friend request.',
            url=f'/profile/{self.a.username}/',
            url_label='View Profile',
            notification_type='friend_request',
        )
        self.client.login(username='bob', password='testpass123')
        resp = self.client.get(reverse('notification_list'))
        accept_url = reverse('accept_friend_request', kwargs={'pk': friendship.pk})
        decline_url = reverse('decline_friend_request', kwargs={'pk': friendship.pk})
        self.assertContains(resp, accept_url)
        self.assertContains(resp, decline_url)

    def test_non_friend_notification_has_no_inline_buttons(self):
        Notification.objects.create(
            user=self.b, message='Some other notif',
            notification_type='general',
        )
        self.client.login(username='bob', password='testpass123')
        resp = self.client.get(reverse('notification_list'))
        self.assertNotContains(resp, 'accept')
        self.assertNotContains(resp, 'decline')

    def test_read_friend_request_no_inline_buttons(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        Notification.objects.create(
            user=self.b,
            message=f'{self.a.username} sent you a friend request.',
            url=f'/profile/{self.a.username}/',
            notification_type='friend_request',
            is_read=True,
        )
        self.client.login(username='bob', password='testpass123')
        resp = self.client.get(reverse('notification_list'))
        accept_url = reverse('accept_friend_request', kwargs={'pk': friendship.pk})
        self.assertNotContains(resp, accept_url)

    def test_accepted_friendship_no_inline_buttons(self):
        Friendship.objects.create(requester=self.a, receiver=self.b, status='accepted')
        Notification.objects.create(
            user=self.b,
            message=f'{self.a.username} sent you a friend request.',
            url=f'/profile/{self.a.username}/',
            notification_type='friend_request',
        )
        self.client.login(username='bob', password='testpass123')
        resp = self.client.get(reverse('notification_list'))
        friendship = Friendship.objects.get(requester=self.a, receiver=self.b)
        accept_url = reverse('accept_friend_request', kwargs={'pk': friendship.pk})
        self.assertNotContains(resp, accept_url)

    def test_accepting_via_notification_accepts_friendship(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        self.client.login(username='bob', password='testpass123')
        self.client.post(reverse('accept_friend_request', kwargs={'pk': friendship.pk}))
        friendship.refresh_from_db()
        self.assertEqual(friendship.status, 'accepted')

    def test_declining_via_notification_declines_friendship(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        self.client.login(username='bob', password='testpass123')
        self.client.post(reverse('decline_friend_request', kwargs={'pk': friendship.pk}))
        friendship.refresh_from_db()
        self.assertEqual(friendship.status, 'declined')