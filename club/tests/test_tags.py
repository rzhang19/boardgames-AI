from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from club.models import BoardGame, Event, EventAttendance, GameTag, EventTag, Group, TagRequest

User = get_user_model()


@tag("unit")
class GameTagModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='tagowner', password='testpass123'
        )

    def test_create_game_tag_stores_name_lowercase(self):
        tag = GameTag.objects.create(name='Racing')
        self.assertEqual(tag.name, 'racing')

    def test_game_tag_string_representation(self):
        tag = GameTag.objects.create(name='Racing')
        self.assertEqual(str(tag), 'racing')

    def test_game_tag_unique_name_constraint(self):
        GameTag.objects.create(name='racing')
        with self.assertRaises(IntegrityError):
            GameTag.objects.create(name='racing')

    def test_game_tag_case_insensitive_unique(self):
        GameTag.objects.create(name='racing')
        with self.assertRaises(IntegrityError):
            GameTag.objects.create(name='RACING')

    def test_game_tag_mixed_case_unique(self):
        GameTag.objects.create(name='Racing')
        with self.assertRaises(IntegrityError):
            GameTag.objects.create(name='RACING')

    def test_game_tag_optional_created_by(self):
        tag = GameTag.objects.create(name='racing')
        self.assertIsNone(tag.created_by)

    def test_game_tag_with_created_by(self):
        tag = GameTag.objects.create(name='racing', created_by=self.user)
        self.assertEqual(tag.created_by, self.user)

    def test_game_tag_created_at_auto_set(self):
        tag = GameTag.objects.create(name='racing')
        self.assertIsNotNone(tag.created_at)

    def test_game_tag_max_length(self):
        name = 'a' * 25
        tag = GameTag.objects.create(name=name)
        self.assertEqual(len(tag.name), 25)

    def test_game_tag_ordering_by_name(self):
        GameTag.objects.create(name='ztag_zebra')
        GameTag.objects.create(name='atag_alpha')
        GameTag.objects.create(name='mtag_middle')
        tags = list(GameTag.objects.filter(name__endswith='tag_zebra') | GameTag.objects.filter(name__endswith='tag_alpha') | GameTag.objects.filter(name__endswith='tag_middle'))
        tag_names = [t.name for t in tags]
        self.assertLess(tag_names.index('atag_alpha'), tag_names.index('mtag_middle'))
        self.assertLess(tag_names.index('mtag_middle'), tag_names.index('ztag_zebra'))

    def test_seed_data_exists(self):
        self.assertTrue(GameTag.objects.filter(name='strategy').exists())
        self.assertTrue(GameTag.objects.filter(name='party').exists())
        self.assertTrue(GameTag.objects.filter(name='cooperative').exists())
        self.assertTrue(GameTag.objects.filter(name='worker placement').exists())
        self.assertTrue(GameTag.objects.filter(name='engine building').exists())
        self.assertTrue(GameTag.objects.filter(name='deck builder').exists())


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


@tag("unit")
class BoardGameTagTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='gameowner', password='testpass123'
        )

    def test_board_game_can_have_tags(self):
        game = BoardGame.objects.create(name='Catan', owner=self.user)
        tag1 = GameTag.objects.create(name='racing')
        tag2 = GameTag.objects.create(name='trading')
        game.tags.add(tag1, tag2)
        self.assertEqual(game.tags.count(), 2)
        self.assertIn(tag1, game.tags.all())

    def test_board_game_can_have_no_tags(self):
        game = BoardGame.objects.create(name='Chess', owner=self.user)
        self.assertEqual(game.tags.count(), 0)

    def test_board_game_tags_are_game_tags_not_event_tags(self):
        game = BoardGame.objects.create(name='Catan', owner=self.user)
        game_tag = GameTag.objects.create(name='racing')
        event_tag = EventTag.objects.create(name='tournament')
        game.tags.add(game_tag)
        self.assertIn(game_tag, game.tags.all())
        self.assertNotIn(event_tag, game.tags.all())

    def test_game_tag_reverse_relation(self):
        game = BoardGame.objects.create(name='Catan', owner=self.user)
        tag = GameTag.objects.create(name='racing')
        game.tags.add(tag)
        self.assertIn(game, tag.tagged_games.all())

    def test_filter_games_by_tag(self):
        game1 = BoardGame.objects.create(name='Catan', owner=self.user)
        game2 = BoardGame.objects.create(name='Uno', owner=self.user)
        tag = GameTag.objects.create(name='racing')
        game1.tags.add(tag)
        strategy_games = BoardGame.objects.filter(tags=tag)
        self.assertIn(game1, strategy_games)
        self.assertNotIn(game2, strategy_games)


@tag("unit")
class EventTagRelationTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='eventadmin', password='testpass123', is_site_admin=True
        )
        self.group = Group.objects.create(name='Tag Test Group')

    def _create_event(self, title='Test Event'):
        from django.utils import timezone
        date = timezone.now() + timezone.timedelta(days=7)
        return Event.objects.create(
            title=title, date=date, voting_deadline=date,
            created_by=self.admin, group=self.group,
        )

    def test_event_can_have_tags(self):
        event = self._create_event()
        tag1 = EventTag.objects.create(name='tournament')
        tag2 = EventTag.objects.create(name='casual')
        event.tags.add(tag1, tag2)
        self.assertEqual(event.tags.count(), 2)

    def test_event_can_have_no_tags(self):
        event = self._create_event()
        self.assertEqual(event.tags.count(), 0)

    def test_event_tags_are_event_tags_not_game_tags(self):
        event = self._create_event()
        event_tag = EventTag.objects.create(name='tournament')
        game_tag = GameTag.objects.create(name='racing')
        event.tags.add(event_tag)
        self.assertIn(event_tag, event.tags.all())
        self.assertNotIn(game_tag, event.tags.all())

    def test_event_tag_reverse_relation(self):
        event = self._create_event()
        tag = EventTag.objects.create(name='tournament')
        event.tags.add(tag)
        self.assertIn(event, tag.tagged_events.all())

    def test_filter_events_by_tag(self):
        event1 = self._create_event('Party Night')
        event2 = self._create_event('Tournament')
        tag = EventTag.objects.create(name='tournament')
        event1.tags.add(tag)
        tagged_events = Event.objects.filter(tags=tag)
        self.assertIn(event1, tagged_events)
        self.assertNotIn(event2, tagged_events)
