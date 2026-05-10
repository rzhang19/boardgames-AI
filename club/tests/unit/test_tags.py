from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from club.models import EventTag, TagRequest

User = get_user_model()


@tag("unit")
class EventTagModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='eventtagowner', password='testpass123'
        )

    def test_create_event_tag_stores_name_lowercase(self):
        tag = EventTag.objects.create(name='Tournament')
        self.assertEqual(tag.name, 'tournament')

    def test_event_tag_string_representation(self):
        tag = EventTag.objects.create(name='Tournament')
        self.assertEqual(str(tag), 'tournament')

    def test_event_tag_unique_name_constraint(self):
        EventTag.objects.create(name='tournament')
        with self.assertRaises(IntegrityError):
            EventTag.objects.create(name='tournament')

    def test_event_tag_case_insensitive_unique(self):
        EventTag.objects.create(name='tournament')
        with self.assertRaises(IntegrityError):
            EventTag.objects.create(name='TOURNAMENT')

    def test_event_tag_optional_created_by(self):
        tag = EventTag.objects.create(name='tournament')
        self.assertIsNone(tag.created_by)

    def test_event_tag_with_created_by(self):
        tag = EventTag.objects.create(name='tournament', created_by=self.user)
        self.assertEqual(tag.created_by, self.user)

    def test_event_tag_ordering_by_name(self):
        EventTag.objects.create(name='ztag_zebra')
        EventTag.objects.create(name='atag_alpha')
        tags = list(EventTag.objects.filter(name__endswith='tag_zebra') | EventTag.objects.filter(name__endswith='tag_alpha'))
        tag_names = [t.name for t in tags]
        self.assertLess(tag_names.index('atag_alpha'), tag_names.index('ztag_zebra'))

    def test_seed_data_exists(self):
        self.assertTrue(EventTag.objects.filter(name='party').exists())
        self.assertTrue(EventTag.objects.filter(name='long form').exists())
        self.assertTrue(EventTag.objects.filter(name='private').exists())


@tag("unit")
class TagRequestModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='requester', password='testpass123'
        )

    def test_create_tag_request_stores_name_lowercase(self):
        req = TagRequest.objects.create(
            name='Racing', tag_type='game', requested_by=self.user
        )
        self.assertEqual(req.name, 'racing')

    def test_tag_request_default_status_is_pending(self):
        req = TagRequest.objects.create(
            name='racing', tag_type='game', requested_by=self.user
        )
        self.assertEqual(req.status, 'pending')

    def test_tag_request_string_representation(self):
        req = TagRequest.objects.create(
            name='Racing', tag_type='game', requested_by=self.user
        )
        self.assertIn('racing', str(req))
        self.assertIn('game', str(req))
        self.assertIn('pending', str(req))

    def test_tag_request_unique_pending_constraint(self):
        TagRequest.objects.create(
            name='racing', tag_type='game', requested_by=self.user
        )
        with self.assertRaises(IntegrityError):
            TagRequest.objects.create(
                name='racing', tag_type='game', requested_by=self.user
            )

    def test_tag_request_same_name_different_type_allowed(self):
        TagRequest.objects.create(
            name='racing', tag_type='game', requested_by=self.user
        )
        req2 = TagRequest.objects.create(
            name='racing', tag_type='event', requested_by=self.user
        )
        self.assertIsNotNone(req2)

    def test_tag_request_rejected_allows_new_pending(self):
        TagRequest.objects.create(
            name='racing', tag_type='game', requested_by=self.user,
            status='rejected'
        )
        req2 = TagRequest.objects.create(
            name='racing', tag_type='game', requested_by=self.user
        )
        self.assertEqual(req2.status, 'pending')

    def test_tag_request_approved_allows_new_pending(self):
        TagRequest.objects.create(
            name='racing', tag_type='game', requested_by=self.user,
            status='approved'
        )
        req2 = TagRequest.objects.create(
            name='racing', tag_type='game', requested_by=self.user
        )
        self.assertEqual(req2.status, 'pending')

    def test_tag_request_reviewed_by_and_at(self):
        admin = User.objects.create_user(
            username='admin', password='testpass123', is_site_admin=True
        )
        req = TagRequest.objects.create(
            name='racing', tag_type='game', requested_by=self.user,
            status='approved', reviewed_by=admin
        )
        self.assertEqual(req.reviewed_by, admin)
