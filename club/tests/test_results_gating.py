from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.urls import reverse

from club.models import BoardGame, Event, EventAttendance, Group, GroupMembership, Vote

User = get_user_model()


def _make_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='admin')


def _make_group_organizer(user, group):
    GroupMembership.objects.create(user=user, group=group, role='organizer')


def _make_member(user, group):
    GroupMembership.objects.create(user=user, group=group, role='member')


@tag("integration")
class GroupEventResultsGatingTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        self.group_org = User.objects.create_user(
            username='group_org', password='testpass123'
        )
        self.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        self.outsider = User.objects.create_user(
            username='outsider', password='testpass123'
        )
        self.group = Group.objects.create(name='Results Gate Group')
        _make_organizer(self.organizer, self.group)
        _make_group_organizer(self.group_org, self.group)
        _make_member(self.member, self.group)
        self.event = Event.objects.create(
            title='Gated Event', date='2026-05-01T18:00:00Z',
            voting_deadline='2026-05-01T18:00:00Z',
            created_by=self.organizer, group=self.group
        )
        EventAttendance.objects.create(user=self.member, event=self.event)
        self.game = BoardGame.objects.create(name='Catan', owner=self.organizer)
        Vote.objects.create(
            user=self.member, event=self.event, board_game=self.game, rank=1
        )

    def test_organizer_can_view_results(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk
            })
        )
        self.assertEqual(response.status_code, 200)

    def test_group_organizer_can_view_results(self):
        self.client.login(username='group_org', password='testpass123')
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk
            })
        )
        self.assertEqual(response.status_code, 200)

    def test_regular_member_cannot_view_results(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk
            })
        )
        self.assertEqual(response.status_code, 403)

    def test_outsider_cannot_view_results(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk
            })
        )
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_cannot_view_results(self):
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk
            })
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_site_admin_can_view_results(self):
        site_admin = User.objects.create_user(
            username='siteadmin', password='testpass123', is_site_admin=True
        )
        _make_member(site_admin, self.group)
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk
            })
        )
        self.assertEqual(response.status_code, 200)


@tag("integration")
class PrivateEventResultsGatingTest(TestCase):

    def setUp(self):
        self.creator = User.objects.create_user(
            username='creator', password='testpass123'
        )
        self.attendee = User.objects.create_user(
            username='attendee', password='testpass123'
        )
        self.other_user = User.objects.create_user(
            username='other', password='testpass123'
        )
        self.event = Event.objects.create(
            title='Private Event', date='2026-05-01T18:00:00Z',
            voting_deadline='2026-05-01T18:00:00Z',
            created_by=self.creator,
            privacy='public',
        )
        EventAttendance.objects.create(user=self.attendee, event=self.event)
        self.game = BoardGame.objects.create(name='Wingspan', owner=self.creator)
        Vote.objects.create(
            user=self.attendee, event=self.event, board_game=self.game, rank=1
        )

    def test_creator_can_view_results(self):
        self.client.login(username='creator', password='testpass123')
        response = self.client.get(
            reverse('private_event_results', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_attendee_cannot_view_results(self):
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(
            reverse('private_event_results', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_other_user_cannot_view_results(self):
        self.client.login(username='other', password='testpass123')
        response = self.client.get(
            reverse('private_event_results', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_cannot_view_results(self):
        response = self.client.get(
            reverse('private_event_results', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_additional_organizer_can_view_results(self):
        add_org = User.objects.create_user(
            username='addorg', password='testpass123'
        )
        EventAttendance.objects.create(user=add_org, event=self.event)
        self.event.additional_organizers.add(add_org)
        self.client.login(username='addorg', password='testpass123')
        response = self.client.get(
            reverse('private_event_results', kwargs={'pk': self.event.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_group_event_redirects_from_private_url(self):
        group = Group.objects.create(name='Redirect Group')
        GroupMembership.objects.create(
            user=self.creator, group=group, role='admin'
        )
        group_event = Event.objects.create(
            title='Group Event', date='2026-05-01T18:00:00Z',
            voting_deadline='2026-05-01T18:00:00Z',
            created_by=self.creator, group=group,
        )
        self.client.login(username='creator', password='testpass123')
        response = self.client.get(
            reverse('private_event_results', kwargs={'pk': group_event.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse('event_results', kwargs={
                'slug': group.slug, 'pk': group_event.pk
            })
        )


@tag("integration")
class EventResultsTemplateTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        self.member = User.objects.create_user(
            username='member', password='testpass123'
        )

    def test_group_event_results_back_link_uses_group_url(self):
        group = Group.objects.create(name='Template Group')
        _make_organizer(self.organizer, group)
        event = Event.objects.create(
            title='Template Event', date='2026-05-01T18:00:00Z',
            voting_deadline='2026-05-01T18:00:00Z',
            created_by=self.organizer, group=group,
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': group.slug, 'pk': event.pk
            })
        )
        self.assertContains(
            response,
            reverse('event_detail', kwargs={
                'slug': group.slug, 'pk': event.pk
            })
        )

    def test_private_event_results_back_link_uses_private_url(self):
        event = Event.objects.create(
            title='Private Template Event', date='2026-05-01T18:00:00Z',
            voting_deadline='2026-05-01T18:00:00Z',
            created_by=self.organizer,
            privacy='public',
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('private_event_results', kwargs={'pk': event.pk})
        )
        self.assertContains(
            response,
            reverse('private_event_detail', kwargs={'pk': event.pk})
        )

    def test_group_event_detail_hides_results_link_from_member(self):
        group = Group.objects.create(name='Hide Results Group')
        _make_organizer(self.organizer, group)
        _make_member(self.member, group)
        event = Event.objects.create(
            title='Hide Event', date='2026-05-01T18:00:00Z',
            voting_deadline='2026-05-01T18:00:00Z',
            created_by=self.organizer, group=group,
        )
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('event_detail', kwargs={
                'slug': group.slug, 'pk': event.pk
            })
        )
        self.assertNotContains(response, 'View Results')

    def test_group_event_detail_shows_results_link_to_organizer(self):
        group = Group.objects.create(name='Show Results Group')
        _make_organizer(self.organizer, group)
        event = Event.objects.create(
            title='Show Event', date='2026-05-01T18:00:00Z',
            voting_deadline='2026-05-01T18:00:00Z',
            created_by=self.organizer, group=group,
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_detail', kwargs={
                'slug': group.slug, 'pk': event.pk
            })
        )
        self.assertContains(response, 'View Results')

    def test_private_event_detail_hides_results_link_from_attendee(self):
        event = Event.objects.create(
            title='Private Hide', date='2026-05-01T18:00:00Z',
            voting_deadline='2026-05-01T18:00:00Z',
            created_by=self.organizer,
            privacy='public',
        )
        EventAttendance.objects.create(user=self.member, event=event)
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('private_event_detail', kwargs={'pk': event.pk})
        )
        self.assertNotContains(response, 'Results')

    def test_private_event_detail_shows_results_link_to_creator(self):
        event = Event.objects.create(
            title='Private Show', date='2026-05-01T18:00:00Z',
            voting_deadline='2026-05-01T18:00:00Z',
            created_by=self.organizer,
            privacy='public',
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('private_event_detail', kwargs={'pk': event.pk})
        )
        self.assertContains(response, 'Results')


@tag("integration")
class EventVoteBackLinkTest(TestCase):

    def setUp(self):
        self.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        self.attendee = User.objects.create_user(
            username='attendee', password='testpass123'
        )

    def test_group_event_vote_back_link_uses_group_url(self):
        group = Group.objects.create(name='Vote Link Group')
        _make_organizer(self.organizer, group)
        _make_member(self.attendee, group)
        event = Event.objects.create(
            title='Vote Link Event', date='2026-05-01T18:00:00Z',
            voting_deadline='2026-05-01T18:00:00Z',
            created_by=self.organizer, group=group,
        )
        EventAttendance.objects.create(user=self.attendee, event=event)
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(
            reverse('event_vote', kwargs={
                'slug': group.slug, 'pk': event.pk
            })
        )
        self.assertContains(
            response,
            reverse('event_detail', kwargs={
                'slug': group.slug, 'pk': event.pk
            })
        )

    def test_private_event_vote_back_link_uses_private_url(self):
        event = Event.objects.create(
            title='Private Vote Link', date='2026-05-01T18:00:00Z',
            voting_deadline='2026-05-01T18:00:00Z',
            created_by=self.organizer,
            privacy='public',
        )
        EventAttendance.objects.create(user=self.attendee, event=event)
        self.client.login(username='attendee', password='testpass123')
        response = self.client.get(
            reverse('private_event_vote', kwargs={'pk': event.pk})
        )
        self.assertContains(
            response,
            reverse('private_event_detail', kwargs={'pk': event.pk})
        )
