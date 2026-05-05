import json

from django.test import TestCase, tag, Client
from django.contrib.auth import get_user_model

from club.models import GameTag, EventTag, TagRequest, Notification

User = get_user_model()


@tag("unit")
class GameTagSearchViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='searcher', password='testpass123'
        )
        self.client.login(username='searcher', password='testpass123')

    def test_search_returns_matching_tags(self):
        GameTag.objects.create(name='racing')
        GameTag.objects.create(name='role playing')
        response = self.client.get('/tags/game/search/', {'q': 'rac'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        names = [t['name'] for t in data]
        self.assertIn('racing', names)
        self.assertNotIn('role playing', names)

    def test_search_empty_query_returns_empty(self):
        response = self.client.get('/tags/game/search/', {'q': ''})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_search_no_query_param_returns_empty(self):
        response = self.client.get('/tags/game/search/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_search_requires_authentication(self):
        self.client.logout()
        response = self.client.get('/tags/game/search/', {'q': 'strat'})
        self.assertEqual(response.status_code, 302)

    def test_search_returns_id_and_name(self):
        tag = GameTag.objects.create(name='racing')
        response = self.client.get('/tags/game/search/', {'q': 'rac'})
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['id'], tag.pk)
        self.assertEqual(data[0]['name'], 'racing')


@tag("unit")
class EventTagSearchViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='eventsearcher', password='testpass123'
        )
        self.client.login(username='eventsearcher', password='testpass123')

    def test_search_returns_matching_event_tags(self):
        EventTag.objects.create(name='tournament')
        EventTag.objects.create(name='casual')
        response = self.client.get('/tags/event/search/', {'q': 'tour'})
        data = response.json()
        names = [t['name'] for t in data]
        self.assertIn('tournament', names)
        self.assertNotIn('casual', names)

    def test_search_requires_authentication(self):
        self.client.logout()
        response = self.client.get('/tags/event/search/', {'q': 'tour'})
        self.assertEqual(response.status_code, 302)


@tag("unit")
class TagRequestSubmitViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.verified_user = User.objects.create_user(
            username='verified', password='testpass123', email_verified=True
        )
        self.admin = User.objects.create_user(
            username='siteadmin', password='testpass123',
            is_site_admin=True, email_verified=True,
        )
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123',
            email_verified=True,
        )

    def test_verified_user_can_submit_tag_request(self):
        self.client.login(username='verified', password='testpass123')
        response = self.client.post('/tags/request/', json.dumps({
            'name': 'racing', 'tag_type': 'game',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(TagRequest.objects.filter(name='racing', tag_type='game').exists())

    def test_unverified_user_cannot_submit_request(self):
        unverified = User.objects.create_user(
            username='unverified', password='testpass123', email_verified=False
        )
        self.client.login(username='unverified', password='testpass123')
        response = self.client.post('/tags/request/', json.dumps({
            'name': 'racing', 'tag_type': 'game',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_submit_request(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post('/tags/request/', json.dumps({
            'name': 'racing', 'tag_type': 'game',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_superuser_cannot_submit_request(self):
        self.client.login(username='superuser', password='testpass123')
        response = self.client.post('/tags/request/', json.dumps({
            'name': 'racing', 'tag_type': 'game',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_request_requires_authentication(self):
        response = self.client.post('/tags/request/', json.dumps({
            'name': 'racing', 'tag_type': 'game',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 302)

    def test_request_stores_name_lowercase(self):
        self.client.login(username='verified', password='testpass123')
        self.client.post('/tags/request/', json.dumps({
            'name': 'Racing', 'tag_type': 'game',
        }), content_type='application/json')
        req = TagRequest.objects.first()
        self.assertEqual(req.name, 'racing')

    def test_duplicate_pending_request_rejected(self):
        self.client.login(username='verified', password='testpass123')
        self.client.post('/tags/request/', json.dumps({
            'name': 'racing', 'tag_type': 'game',
        }), content_type='application/json')
        response = self.client.post('/tags/request/', json.dumps({
            'name': 'racing', 'tag_type': 'game',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_invalid_tag_type_rejected(self):
        self.client.login(username='verified', password='testpass123')
        response = self.client.post('/tags/request/', json.dumps({
            'name': 'racing', 'tag_type': 'invalid',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)


@tag("unit")
class AdminTagAddViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='siteadmin', password='testpass123',
            is_site_admin=True, email_verified=True,
        )
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123',
            email_verified=True,
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123', email_verified=True,
        )

    def test_admin_can_add_game_tag(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post('/admin-settings/tags/game/add/', json.dumps({
            'name': 'racing',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(GameTag.objects.filter(name='racing').exists())

    def test_admin_can_add_event_tag(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post('/admin-settings/tags/event/add/', json.dumps({
            'name': 'tournament',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(EventTag.objects.filter(name='tournament').exists())

    def test_regular_user_cannot_add_tag(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.post('/admin-settings/tags/game/add/', json.dumps({
            'name': 'racing',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 403)

    def test_duplicate_tag_returns_error(self):
        GameTag.objects.create(name='racing')
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post('/admin-settings/tags/game/add/', json.dumps({
            'name': 'racing',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_tag_stored_lowercase(self):
        self.client.login(username='siteadmin', password='testpass123')
        self.client.post('/admin-settings/tags/game/add/', json.dumps({
            'name': 'Racing',
        }), content_type='application/json')
        tag = GameTag.objects.get(name='racing')
        self.assertEqual(tag.created_by, self.admin)


@tag("unit")
class AdminTagManagementViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123',
            email_verified=True,
        )
        self.admin = User.objects.create_user(
            username='siteadmin', password='testpass123',
            is_site_admin=True, email_verified=True,
        )
        self.regular = User.objects.create_user(
            username='regular', password='testpass123', email_verified=True,
        )

    def test_admin_can_view_tag_management_page(self):
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get('/admin-settings/tags/')
        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_view_tag_management(self):
        self.client.login(username='regular', password='testpass123')
        response = self.client.get('/admin-settings/tags/')
        self.assertEqual(response.status_code, 403)

    def test_tag_management_lists_game_tags(self):
        GameTag.objects.create(name='racing')
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get('/admin-settings/tags/')
        self.assertContains(response, 'racing')

    def test_tag_management_lists_event_tags(self):
        EventTag.objects.create(name='tournament')
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get('/admin-settings/tags/?tab=event')
        self.assertContains(response, 'tournament')

    def test_tag_management_lists_pending_requests(self):
        user = User.objects.create_user(username='requester', password='testpass123')
        TagRequest.objects.create(name='racing', tag_type='game', requested_by=user)
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.get('/admin-settings/tags/?tab=requests')
        self.assertContains(response, 'racing')


@tag("unit")
class AdminTagDeleteViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username='superuser', password='testpass123',
            email_verified=True,
        )
        self.admin = User.objects.create_user(
            username='siteadmin', password='testpass123',
            is_site_admin=True, email_verified=True,
        )

    def test_superuser_can_delete_game_tag(self):
        tag = GameTag.objects.create(name='racing')
        self.client.login(username='superuser', password='testpass123')
        response = self.client.post(f'/admin-settings/tags/game/{tag.pk}/delete/')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(GameTag.objects.filter(pk=tag.pk).exists())

    def test_site_admin_cannot_delete_tag(self):
        tag = GameTag.objects.create(name='racing')
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post(f'/admin-settings/tags/game/{tag.pk}/delete/')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(GameTag.objects.filter(pk=tag.pk).exists())

    def test_delete_confirmation_page_shows_usage_count(self):
        from club.models import BoardGame
        tag = GameTag.objects.create(name='racing')
        user = User.objects.create_user(username='delowner', password='testpass123')
        game1 = BoardGame.objects.create(name='Game1', owner=user)
        game2 = BoardGame.objects.create(name='Game2', owner=user)
        game1.tags.add(tag)
        game2.tags.add(tag)
        self.client.login(username='superuser', password='testpass123')
        response = self.client.get(f'/admin-settings/tags/game/{tag.pk}/delete/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2')


@tag("unit")
class TagRequestApproveRejectTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            username='siteadmin', password='testpass123',
            is_site_admin=True, email_verified=True,
        )
        self.requester = User.objects.create_user(
            username='requester', password='testpass123', email_verified=True,
        )

    def test_approve_creates_tag_and_notifies_requester(self):
        req = TagRequest.objects.create(
            name='racing', tag_type='game', requested_by=self.requester
        )
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post(f'/admin-settings/tags/request/{req.pk}/approve/')
        self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved')
        self.assertEqual(req.reviewed_by, self.admin)
        self.assertTrue(GameTag.objects.filter(name='racing').exists())
        self.assertTrue(Notification.objects.filter(
            user=self.requester,
            notification_type='tag_request_approved',
        ).exists())

    def test_reject_does_not_create_tag(self):
        req = TagRequest.objects.create(
            name='racing', tag_type='game', requested_by=self.requester
        )
        self.client.login(username='siteadmin', password='testpass123')
        response = self.client.post(f'/admin-settings/tags/request/{req.pk}/reject/')
        self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, 'rejected')
        self.assertEqual(req.reviewed_by, self.admin)
        self.assertFalse(GameTag.objects.filter(name='racing').exists())

    def test_approve_event_tag_creates_event_tag(self):
        req = TagRequest.objects.create(
            name='tournament', tag_type='event', requested_by=self.requester
        )
        self.client.login(username='siteadmin', password='testpass123')
        self.client.post(f'/admin-settings/tags/request/{req.pk}/approve/')
        self.assertTrue(EventTag.objects.filter(name='tournament').exists())

    def test_regular_user_cannot_approve(self):
        regular = User.objects.create_user(
            username='regular', password='testpass123', email_verified=True,
        )
        req = TagRequest.objects.create(
            name='racing', tag_type='game', requested_by=self.requester
        )
        self.client.login(username='regular', password='testpass123')
        response = self.client.post(f'/admin-settings/tags/request/{req.pk}/approve/')
        self.assertEqual(response.status_code, 403)
        req.refresh_from_db()
        self.assertEqual(req.status, 'pending')
