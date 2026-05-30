from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from club.models import (
    ActivityFeedItem,
    Event,
    Group,
    GroupInvite,
    GroupJoinRequest,
    GroupMembership,
)

User = get_user_model()

FUTURE_DATE = (timezone.now() + timedelta(days=30)).strftime('%Y-%m-%d')


def _create_user(username, password='testpass123', **kwargs):
    return User.objects.create_user(username=username, password=password, **kwargs)


def _create_group(creator, name='Test Group'):
    group = Group.objects.create(name=name, created_by=creator)
    GroupMembership.objects.create(user=creator, group=group, role='admin')
    return group


@tag("integration")
class ActivityFeedPageViewTest(TestCase):

    def setUp(self):
        self.user = _create_user('member')
        self.group = _create_group(self.user)

    def test_activity_page_requires_login(self):
        response = self.client.get(reverse('activity_feed'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_activity_page_returns_200_for_authenticated_user(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('activity_feed'))
        self.assertEqual(response.status_code, 200)

    def test_activity_page_uses_correct_template(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('activity_feed'))
        self.assertTemplateUsed(response, 'club/activity_feed.html')


@tag("integration")
class ActivityFeedVisibilityIntegrationTest(TestCase):

    def setUp(self):
        self.admin = _create_user('admin', is_site_admin=True)
        self.group = _create_group(self.admin, name='Activity Group')
        self.member = _create_user('member')
        GroupMembership.objects.create(user=self.member, group=self.group, role='member')
        self.outsider = _create_user('outsider')

    def test_event_created_activity_appears_for_group_member(self):
        self.client.login(username='admin', password='testpass123')
        self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Board Game Night',
            'date': FUTURE_DATE,
            'time': '18:00',
        })
        self.client.logout()
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('activity_feed'))
        self.assertContains(response, 'Board Game Night')

    def test_event_created_activity_not_visible_to_outsider(self):
        self.client.login(username='admin', password='testpass123')
        self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Secret Night',
            'date': FUTURE_DATE,
            'time': '18:00',
        })
        self.client.logout()
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(reverse('activity_feed'))
        self.assertNotContains(response, 'Secret Night')

    def test_event_updated_activity_appears_for_group_member(self):
        self.client.login(username='admin', password='testpass123')
        self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Update Me',
            'date': FUTURE_DATE,
            'time': '18:00',
        })
        event = Event.objects.get(title='Update Me')
        self.client.post(reverse('event_edit', kwargs={'slug': self.group.slug, 'pk': event.pk}), {
            'title': 'Updated Title',
            'date': FUTURE_DATE,
            'time': '19:00',
        })
        self.client.logout()
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('activity_feed'))
        self.assertContains(response, 'Updated Title')

    def test_member_joined_visible_to_admin_not_member(self):
        new_user = _create_user('newuser')
        self.client.login(username='newuser', password='testpass123')
        self.client.post(reverse('group_join', kwargs={'slug': self.group.slug}))
        self.client.logout()
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(reverse('activity_feed'))
        self.assertContains(response, 'newuser')
        self.client.logout()
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('activity_feed'))
        self.assertNotContains(response, 'newuser')


@tag("integration")
class ActivityFeedCreatedFromViewsTest(TestCase):

    def setUp(self):
        self.admin = _create_user('admin', is_site_admin=True)
        self.group = _create_group(self.admin)

    def test_event_add_creates_activity_item(self):
        self.client.login(username='admin', password='testpass123')
        self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Test Event',
            'date': FUTURE_DATE,
            'time': '18:00',
        })
        self.assertEqual(
            ActivityFeedItem.objects.filter(activity_type='event_created').count(), 1
        )
        item = ActivityFeedItem.objects.first()
        self.assertEqual(item.actor, self.admin)
        self.assertEqual(item.event.title, 'Test Event')
        self.assertEqual(item.group, self.group)

    def test_event_edit_creates_activity_item(self):
        self.client.login(username='admin', password='testpass123')
        self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Edit Test',
            'date': FUTURE_DATE,
            'time': '18:00',
        })
        event = Event.objects.get(title='Edit Test')
        ActivityFeedItem.objects.all().delete()
        self.client.post(reverse('event_edit', kwargs={'slug': self.group.slug, 'pk': event.pk}), {
            'title': 'Edit Test Updated',
            'date': FUTURE_DATE,
            'time': '19:00',
        })
        self.assertEqual(
            ActivityFeedItem.objects.filter(activity_type='event_updated').count(), 1
        )
        item = ActivityFeedItem.objects.first()
        self.assertEqual(item.actor, self.admin)

    def test_group_join_open_creates_activity_item(self):
        joiner = _create_user('joiner')
        self.client.login(username='joiner', password='testpass123')
        self.client.post(reverse('group_join', kwargs={'slug': self.group.slug}))
        self.assertEqual(
            ActivityFeedItem.objects.filter(activity_type='member_joined').count(), 1
        )
        item = ActivityFeedItem.objects.first()
        self.assertEqual(item.actor, joiner)
        self.assertEqual(item.group, self.group)

    def test_group_invite_accept_creates_activity_item(self):
        invitee = _create_user('invitee')
        invite = GroupInvite.objects.create(
            group=self.group,
            created_by=self.admin,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.login(username='invitee', password='testpass123')
        self.client.get(reverse('group_invite_accept', kwargs={'token': invite.token}))
        self.assertEqual(
            ActivityFeedItem.objects.filter(activity_type='member_joined').count(), 1
        )

    def test_join_request_approval_creates_activity_item(self):
        requester = _create_user('requester')
        self.group.join_policy = 'request'
        self.group.save()
        GroupMembership.objects.filter(user=requester).delete()
        jr = GroupJoinRequest.objects.create(
            user=requester,
            group=self.group,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.login(username='admin', password='testpass123')
        self.client.post(reverse('group_join_request_manage', kwargs={'slug': self.group.slug}), {
            'request_id': jr.pk,
            'action': 'approve',
        })
        self.assertEqual(
            ActivityFeedItem.objects.filter(activity_type='member_joined').count(), 1
        )


@tag("integration")
class ActivityFeedPaginationTest(TestCase):

    def setUp(self):
        self.admin = _create_user('admin', is_site_admin=True)
        self.group = _create_group(self.admin)
        self.member = _create_user('member')
        GroupMembership.objects.create(user=self.member, group=self.group, role='member')

    def test_pagination_at_50_items(self):
        self.client.login(username='admin', password='testpass123')
        for i in range(55):
            self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
                'title': f'Event {i}',
                'date': FUTURE_DATE,
                'time': '18:00',
            })
        self.client.logout()
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('activity_feed'))
        self.assertEqual(len(response.context['activities']), 50)
        self.assertTrue(response.context['page_obj'].has_next())
        response = self.client.get(reverse('activity_feed') + '?page=2')
        self.assertEqual(len(response.context['activities']), 5)


@tag("integration")
class DashboardActivityCardTest(TestCase):

    def setUp(self):
        self.admin = _create_user('admin', is_site_admin=True)
        self.group = _create_group(self.admin)
        self.member = _create_user('member')
        GroupMembership.objects.create(user=self.member, group=self.group, role='member')

    def test_dashboard_shows_recent_activities(self):
        self.client.login(username='admin', password='testpass123')
        self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Dashboard Event',
            'date': FUTURE_DATE,
            'time': '18:00',
        })
        self.client.logout()
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Dashboard Event')

    def test_dashboard_shows_show_more_link(self):
        self.client.login(username='admin', password='testpass123')
        self.client.post(reverse('event_add', kwargs={'slug': self.group.slug}), {
            'title': 'Some Event',
            'date': FUTURE_DATE,
            'time': '18:00',
        })
        self.client.logout()
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('activity_feed'))

    def test_dashboard_shows_empty_state_when_no_activity(self):
        quiet_group = _create_group(_create_user('quietadmin'))
        member = _create_user('quietmember')
        GroupMembership.objects.create(user=member, group=quiet_group, role='member')
        self.client.login(username='quietmember', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
