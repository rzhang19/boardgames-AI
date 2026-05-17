from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from club.models import BoardGame, Friendship, Notification

User = get_user_model()


def _create_users(*usernames, password='testpass123'):
    return [User.objects.create_user(username=u, password=password) for u in usernames]


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
        self.user = User.objects.create_user(
            username='alice', password='testpass123',
            email_verified=True, email='alice@test.com',
        )
        User.objects.create_user(username='bob123', password='testpass123')
        User.objects.create_user(username='bobsmith', password='testpass123')
        User.objects.create_user(username='carol', password='testpass123')

    def test_search_partial_match(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all&q=bob')
        self.assertEqual(resp.status_code, 200)
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertTrue(any('bob' in u for u in usernames))

    def test_search_case_insensitive(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all&q=BOB')
        self.assertEqual(resp.status_code, 200)
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertTrue(any('bob' in u.lower() for u in usernames))

    def test_search_excludes_self(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all&q=ali')
        usernames = [u.username for u in resp.context['page_obj'].object_list]
        self.assertNotIn('alice', usernames)

    def test_search_no_query_shows_all(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all')
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(len(resp.context['page_obj'].object_list), 0)

    def test_search_requires_login(self):
        resp = self.client.get(reverse('users_page') + '?tab=all')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_search_shows_verified_icon_for_verified_user(self):
        bob = User.objects.get(username='bob123')
        bob.email_verified = True
        bob.save()
        self.client.force_login(self.user)
        resp = self.client.get(reverse('users_page') + '?tab=all&q=bob')
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
        self.assertContains(resp, 'data-friendship-pk="' + str(friendship.pk) + '"')
        self.assertContains(resp, 'friend-accept-btn')
        self.assertContains(resp, 'friend-decline-btn')

    def test_non_friend_notification_has_no_inline_buttons(self):
        Notification.objects.create(
            user=self.b, message='Some other notif',
            notification_type='general',
        )
        self.client.login(username='bob', password='testpass123')
        resp = self.client.get(reverse('notification_list'))
        self.assertNotContains(resp, 'data-action="accept"')
        self.assertNotContains(resp, 'data-action="decline"')

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
        self.assertNotContains(resp, 'data-action="accept"')

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
        self.assertNotContains(resp, 'data-action="accept"')

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


# ---------------------------------------------------------------------------
# View tests — AJAX friend request actions
# ---------------------------------------------------------------------------

@tag("integration")
class AjaxAcceptFriendRequestTest(TestCase):

    def setUp(self):
        self.a, self.b = _create_users('alice', 'bob')

    def test_ajax_accept_returns_json(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(
            reverse('accept_friend_request', kwargs={'pk': friendship.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'accepted')
        self.assertEqual(data['username'], 'alice')

    def test_ajax_accept_marks_notification_as_read(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        notif = Notification.objects.create(
            user=self.b,
            message=f'{self.a.username} sent you a friend request.',
            url=f'/profile/{self.a.username}/',
            notification_type='friend_request',
        )
        self.client.login(username='bob', password='testpass123')
        self.client.post(
            reverse('accept_friend_request', kwargs={'pk': friendship.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_ajax_accept_actually_accepts_friendship(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        self.client.login(username='bob', password='testpass123')
        self.client.post(
            reverse('accept_friend_request', kwargs={'pk': friendship.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        friendship.refresh_from_db()
        self.assertEqual(friendship.status, 'accepted')

    def test_ajax_accept_by_wrong_user_forbidden(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(
            reverse('accept_friend_request', kwargs={'pk': friendship.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 403)

    def test_ajax_accept_non_pending_forbidden(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b, status='accepted')
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(
            reverse('accept_friend_request', kwargs={'pk': friendship.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 403)

    def test_ajax_accept_requires_login(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        resp = self.client.post(
            reverse('accept_friend_request', kwargs={'pk': friendship.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_non_ajax_accept_still_redirects(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(reverse('accept_friend_request', kwargs={'pk': friendship.pk}))
        self.assertEqual(resp.status_code, 302)


@tag("integration")
class AjaxDeclineFriendRequestTest(TestCase):

    def setUp(self):
        self.a, self.b = _create_users('alice', 'bob')

    def test_ajax_decline_returns_json(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(
            reverse('decline_friend_request', kwargs={'pk': friendship.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'declined')
        self.assertEqual(data['username'], 'alice')

    def test_ajax_decline_marks_notification_as_read(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        notif = Notification.objects.create(
            user=self.b,
            message=f'{self.a.username} sent you a friend request.',
            url=f'/profile/{self.a.username}/',
            notification_type='friend_request',
        )
        self.client.login(username='bob', password='testpass123')
        self.client.post(
            reverse('decline_friend_request', kwargs={'pk': friendship.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_ajax_decline_actually_declines_friendship(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        self.client.login(username='bob', password='testpass123')
        self.client.post(
            reverse('decline_friend_request', kwargs={'pk': friendship.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        friendship.refresh_from_db()
        self.assertEqual(friendship.status, 'declined')
        self.assertEqual(friendship.decline_count, 1)

    def test_ajax_decline_by_wrong_user_forbidden(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        self.client.login(username='alice', password='testpass123')
        resp = self.client.post(
            reverse('decline_friend_request', kwargs={'pk': friendship.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 403)

    def test_non_ajax_decline_still_redirects(self):
        friendship = Friendship.objects.create(requester=self.a, receiver=self.b)
        self.client.login(username='bob', password='testpass123')
        resp = self.client.post(reverse('decline_friend_request', kwargs={'pk': friendship.pk}))
        self.assertEqual(resp.status_code, 302)


# ---------------------------------------------------------------------------
# Notification context processor tests
# ---------------------------------------------------------------------------

@tag("integration")
class NotificationContextProcessorTest(TestCase):

    def test_authenticated_user_sees_unread_count(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        Notification.objects.create(user=user, message='Unread 1')
        Notification.objects.create(user=user, message='Unread 2')
        Notification.objects.create(user=user, message='Read', is_read=True)
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['unread_notification_count'], 2)

    def test_anonymous_user_sees_zero_count(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['unread_notification_count'], 0)

    def test_badge_display_under_nine(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        for i in range(5):
            Notification.objects.create(user=user, message=f'Msg {i}')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['notification_badge_display'], '5')

    def test_badge_display_nine_plus(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        for i in range(12):
            Notification.objects.create(user=user, message=f'Msg {i}')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['notification_badge_display'], '9+')

    def test_badge_display_exactly_nine(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        for i in range(9):
            Notification.objects.create(user=user, message=f'Msg {i}')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['notification_badge_display'], '9')

    def test_badge_display_zero(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.context['notification_badge_display'], '0')


# ---------------------------------------------------------------------------
# Notification list view tests
# ---------------------------------------------------------------------------

@tag("integration")
class NotificationListViewTest(TestCase):

    def test_notification_list_requires_login(self):
        response = self.client.get(reverse('notification_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_notification_list_shows_users_notifications(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        other = User.objects.create_user(username='otheruser', password='testpass123')
        Notification.objects.create(user=user, message='My notif')
        Notification.objects.create(user=other, message='Other notif')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('notification_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My notif')
        self.assertNotContains(response, 'Other notif')

    def test_notification_list_ordered_newest_first(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        Notification.objects.create(user=user, message='First')
        Notification.objects.create(user=user, message='Second')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('notification_list'))
        content = response.content.decode()
        self.assertGreater(content.index('Second'), 0)
        first_pos = content.index('First')
        second_pos = content.index('Second')
        self.assertLess(second_pos, first_pos)


# ---------------------------------------------------------------------------
# Notification mark-read tests
# ---------------------------------------------------------------------------

@tag("integration")
class NotificationMarkReadTest(TestCase):

    def test_mark_read_requires_login(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Test')
        response = self.client.post(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_mark_read_marks_as_read(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Test')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_mark_read_redirects_to_notification_url(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(
            user=user, message='Test',
            url='/games/1/', url_label='Edit',
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/games/1/')

    def test_mark_read_redirects_to_list_when_no_url(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Test')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('notification_list'))

    def test_mark_read_requires_post(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Test')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, 405)

    def test_cannot_mark_other_users_notification(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        other = User.objects.create_user(username='otheruser', password='testpass123')
        notif = Notification.objects.create(user=other, message='Other notif')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, 404)

    def test_mark_read_already_read_is_idempotent(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Test', is_read=True)
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, 302)
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_mark_read_rejects_external_url(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(
            user=user, message='Test',
            url='https://evil.com/phishing',
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('notification_list'))

    def test_mark_read_rejects_http_scheme(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(
            user=user, message='Test',
            url='http://example.com/path',
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('notification_list'))


# ---------------------------------------------------------------------------
# Notification mark-all-read tests
# ---------------------------------------------------------------------------

@tag("integration")
class NotificationMarkAllReadTest(TestCase):

    def test_mark_all_read_requires_login(self):
        response = self.client.post(reverse('notification_mark_all_read'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_mark_all_read_marks_all_as_read(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        Notification.objects.create(user=user, message='One')
        Notification.objects.create(user=user, message='Two')
        Notification.objects.create(user=user, message='Three')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_mark_all_read'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(user=user, is_read=False).count(), 0)
        self.assertEqual(Notification.objects.filter(user=user, is_read=True).count(), 3)

    def test_mark_all_read_does_not_affect_other_users(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        other = User.objects.create_user(username='otheruser', password='testpass123')
        Notification.objects.create(user=user, message='Mine')
        Notification.objects.create(user=other, message='Theirs')
        self.client.login(username='testuser', password='testpass123')
        self.client.post(reverse('notification_mark_all_read'))
        self.assertEqual(Notification.objects.filter(user=other, is_read=False).count(), 1)

    def test_mark_all_read_requires_post(self):
        User.objects.create_user(username='testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('notification_mark_all_read'))
        self.assertEqual(response.status_code, 405)


# ---------------------------------------------------------------------------
# Notification delete-selected tests
# ---------------------------------------------------------------------------

@tag("integration")
class NotificationDeleteSelectedTest(TestCase):

    def test_delete_selected_requires_login(self):
        response = self.client.post(reverse('notification_delete_selected'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_delete_selected_deletes_chosen_notifications(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif1 = Notification.objects.create(user=user, message='Read 1', is_read=True)
        notif2 = Notification.objects.create(user=user, message='Read 2', is_read=True)
        Notification.objects.create(user=user, message='Unread')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_delete_selected'), {
            'selected_notifications': [notif1.pk, notif2.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(user=user).count(), 1)

    def test_delete_selected_does_not_delete_other_users(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        other = User.objects.create_user(username='otheruser', password='testpass123')
        other_notif = Notification.objects.create(user=other, message='Other', is_read=True)
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_delete_selected'), {
            'selected_notifications': [other_notif.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(user=other).count(), 1)

    def test_delete_selected_does_not_delete_unread(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Unread', is_read=False)
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_delete_selected'), {
            'selected_notifications': [notif.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(user=user).count(), 1)

    def test_delete_selected_with_no_selection(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        Notification.objects.create(user=user, message='Keep', is_read=True)
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('notification_delete_selected'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Notification.objects.filter(user=user).count(), 1)

    def test_delete_selected_requires_post(self):
        User.objects.create_user(username='testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('notification_delete_selected'))
        self.assertEqual(response.status_code, 405)


# ---------------------------------------------------------------------------
# Missing complexity notification on login tests
# ---------------------------------------------------------------------------

@tag("integration")
class MissingComplexityNotificationOnLoginTest(TestCase):

    def test_notifications_generated_on_login(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        BoardGame.objects.create(name='Catan', owner=user)
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'testpass123',
        })
        notifs = Notification.objects.filter(user=user, notification_type='missing_complexity')
        self.assertEqual(notifs.count(), 1)

    def test_no_notifications_when_all_games_have_complexity(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        BoardGame.objects.create(name='Catan', owner=user, complexity='medium')
        response = self.client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'testpass123',
        })
        notifs = Notification.objects.filter(user=user, notification_type='missing_complexity')
        self.assertEqual(notifs.count(), 0)


# ---------------------------------------------------------------------------
# AJAX notification mark-read tests
# ---------------------------------------------------------------------------

@tag("integration")
class AjaxNotificationMarkReadTest(TestCase):

    def test_ajax_mark_read_returns_json(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Test')
        self.client.login(username='testuser', password='testpass123')
        resp = self.client.post(
            reverse('notification_mark_read', kwargs={'pk': notif.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'read')

    def test_ajax_mark_read_marks_as_read(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Test')
        self.client.login(username='testuser', password='testpass123')
        self.client.post(
            reverse('notification_mark_read', kwargs={'pk': notif.pk}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_non_ajax_mark_read_still_redirects(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(user=user, message='Test')
        self.client.login(username='testuser', password='testpass123')
        resp = self.client.post(reverse('notification_mark_read', kwargs={'pk': notif.pk}))
        self.assertEqual(resp.status_code, 302)


# ---------------------------------------------------------------------------
# Notification link rendering tests
# ---------------------------------------------------------------------------

@tag("integration")
class NotificationLinkRenderingTest(TestCase):

    def test_notification_with_url_renders_link_to_target_not_mark_read(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(
            user=user,
            message='Edit your game',
            url='/games/1/edit/',
            url_label='Edit Game',
            notification_type='missing_complexity',
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('notification_list'))
        mark_read_url = reverse('notification_mark_read', kwargs={'pk': notif.pk})
        self.assertContains(response, 'href="/games/1/edit/"')
        self.assertContains(response, 'Edit Game')
        self.assertNotContains(response, f'href="{mark_read_url}"')

    def test_notification_without_url_renders_plain_message(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        Notification.objects.create(
            user=user,
            message='Something happened',
            notification_type='general',
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('notification_list'))
        self.assertContains(response, 'Something happened')

    def test_unread_notification_shows_mark_read_button(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(
            user=user,
            message='Unread notif',
            url='/games/1/edit/',
            url_label='Edit Game',
            is_read=False,
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('notification_list'))
        mark_read_url = reverse('notification_mark_read', kwargs={'pk': notif.pk})
        self.assertContains(response, f'action="{mark_read_url}"')
        self.assertContains(response, 'Mark as Read')

    def test_read_notification_does_not_show_mark_read_button(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        notif = Notification.objects.create(
            user=user,
            message='Read notif',
            url='/games/1/edit/',
            url_label='Edit Game',
            is_read=True,
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('notification_list'))
        mark_read_url = reverse('notification_mark_read', kwargs={'pk': notif.pk})
        self.assertNotContains(response, f'action="{mark_read_url}"')

    def test_notification_with_url_no_label_still_renders_message(self):
        user = User.objects.create_user(username='testuser', password='testpass123')
        Notification.objects.create(
            user=user,
            message='No label notif',
            url='/games/1/',
            url_label='',
            notification_type='general',
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('notification_list'))
        self.assertContains(response, 'No label notif')
        self.assertNotContains(response, 'href="/games/1/"')

    def test_friend_request_shows_profile_link_not_mark_read_link(self):
        requester = User.objects.create_user(username='alice', password='testpass123')
        receiver = User.objects.create_user(username='bob', password='testpass123')
        notif = Notification.objects.create(
            user=receiver,
            message='alice sent you a friend request.',
            url=f'/profile/{requester.username}/',
            url_label='View Profile',
            notification_type='friend_request',
            is_read=False,
        )
        self.client.login(username='bob', password='testpass123')
        response = self.client.get(reverse('notification_list'))
        self.assertContains(response, 'href="/profile/alice/"')
        self.assertContains(response, 'View Profile')
        mark_read_url = reverse('notification_mark_read', kwargs={'pk': notif.pk})
        self.assertNotContains(response, f'href="{mark_read_url}"')

    def test_friend_request_message_does_not_have_mark_read_click_handler(self):
        requester = User.objects.create_user(username='alice', password='testpass123')
        receiver = User.objects.create_user(username='bob', password='testpass123')
        notif = Notification.objects.create(
            user=receiver,
            message='alice sent you a friend request.',
            url=f'/profile/{requester.username}/',
            url_label='View Profile',
            notification_type='friend_request',
            is_read=False,
        )
        self.client.login(username='bob', password='testpass123')
        response = self.client.get(reverse('notification_list'))
        content = response.content.decode()
        self.assertNotIn('data-mark-read-url', content)

    def test_read_friend_request_notification_link_goes_to_profile(self):
        requester = User.objects.create_user(username='alice', password='testpass123')
        receiver = User.objects.create_user(username='bob', password='testpass123')
        notif = Notification.objects.create(
            user=receiver,
            message='alice sent you a friend request.',
            url=f'/profile/{requester.username}/',
            url_label='View Profile',
            notification_type='friend_request',
            is_read=True,
        )
        self.client.login(username='bob', password='testpass123')
        response = self.client.get(reverse('notification_list'))
        self.assertContains(response, 'href="/profile/alice/"')
        mark_read_url = reverse('notification_mark_read', kwargs={'pk': notif.pk})
        self.assertNotContains(response, f'href="{mark_read_url}"')
