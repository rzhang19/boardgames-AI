from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.urls import reverse

from club.models import BoardGame, Event, EventAttendance, Group, GroupMembership

User = get_user_model()


@tag("integration")
class GameAddOwnershipDropdownTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='gameowner', password='testpass123'
        )
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.group_admin = User.objects.create_user(
            username='groupadmin', password='testpass123'
        )
        cls.group = Group.objects.create(name='Test Group')
        cls.group2 = Group.objects.create(name='Other Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )
        GroupMembership.objects.create(
            user=cls.member, group=cls.group, role='member'
        )
        GroupMembership.objects.create(
            user=cls.group_admin, group=cls.group, role='admin'
        )
        GroupMembership.objects.create(
            user=cls.group_admin, group=cls.group2, role='admin'
        )

    def test_add_page_has_ownership_dropdown(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ownership_target')

    def test_add_page_shows_self_option(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertContains(response, 'Self')

    def test_add_page_shows_groups_for_organizer(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertContains(response, 'Test Group')

    def test_add_page_no_groups_for_user_without_organizer_role(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertNotContains(response, 'data-group-slug')

    def test_add_page_shows_multiple_groups_for_multi_group_admin(self):
        self.client.login(username='groupadmin', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertContains(response, 'Test Group')
        self.assertContains(response, 'Other Group')

    def test_default_ownership_is_self(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_add'))
        self.assertEqual(response.context['default_ownership'], 'self')

    def test_default_ownership_from_group_param(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('game_add'), {'group': self.group.slug}
        )
        self.assertEqual(
            response.context['default_ownership'],
            f'group:{self.group.slug}'
        )

    def test_default_ownership_from_event_param_with_group_event(self):
        self.client.login(username='organizer', password='testpass123')
        event = Event.objects.create(
            title='Test Event',
            date='2026-06-01T18:00:00Z',
            created_by=self.organizer,
            group=self.group,
            voting_deadline='2026-06-01T18:00:00Z',
        )
        response = self.client.get(
            reverse('game_add'), {'event': event.pk}
        )
        self.assertEqual(
            response.context['default_ownership'],
            f'group:{self.group.slug}'
        )

    def test_default_ownership_from_event_param_with_private_event(self):
        self.client.login(username='gameowner', password='testpass123')
        event = Event.objects.create(
            title='Private Event',
            date='2026-06-01T18:00:00Z',
            created_by=self.user,
            voting_deadline='2026-06-01T18:00:00Z',
        )
        response = self.client.get(
            reverse('game_add'), {'event': event.pk}
        )
        self.assertEqual(response.context['default_ownership'], 'self')

    def test_create_game_with_ownership_self(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'My Game',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
            'ownership_target': 'self',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='My Game')
        self.assertEqual(game.owner, self.user)
        self.assertIsNone(game.group)

    def test_create_game_with_ownership_group(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Group Game',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
            'ownership_target': f'group:{self.group.slug}',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Group Game')
        self.assertIsNone(game.owner)
        self.assertEqual(game.group, self.group)

    def test_create_game_with_ownership_group_not_organizer_fails(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Sneaky Game',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
            'ownership_target': f'group:{self.group.slug}',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoardGame.objects.filter(name='Sneaky Game').exists())

    def test_create_game_with_invalid_group_slug_fails(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Bad Group Game',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
            'ownership_target': 'group:nonexistent',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoardGame.objects.filter(name='Bad Group Game').exists())

    def test_create_game_with_invalid_ownership_format_fails(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Bad Format Game',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
            'ownership_target': 'invalid',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BoardGame.objects.filter(name='Bad Format Game').exists())

    def test_create_game_with_no_ownership_defaults_to_self(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Default Game',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Default Game')
        self.assertEqual(game.owner, self.user)
        self.assertIsNone(game.group)

    def test_create_game_with_empty_ownership_defaults_to_self(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.post(reverse('game_add'), {
            'name': 'Empty Owner Game',
            'min_players': 2,
            'max_players': 4,
            'complexity': 'medium',
            'ownership_target': '',
        })
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Empty Owner Game')
        self.assertEqual(game.owner, self.user)
        self.assertIsNone(game.group)

    def test_suggested_always_contains_self(self):
        self.client.login(username='gameowner', password='testpass123')
        response = self.client.get(reverse('game_add'))
        suggested = response.context.get('suggested_groups', [])
        self.assertIn('self', suggested)

    def test_suggested_contains_event_group_when_event_param(self):
        self.client.login(username='organizer', password='testpass123')
        event = Event.objects.create(
            title='Test Event',
            date='2026-06-01T18:00:00Z',
            created_by=self.organizer,
            group=self.group,
            voting_deadline='2026-06-01T18:00:00Z',
        )
        response = self.client.get(
            reverse('game_add'), {'event': event.pk}
        )
        suggested = response.context.get('suggested_groups', [])
        self.assertIn('self', suggested)
        self.assertIn(self.group.slug, suggested)


@tag("integration")
class GameEditOwnershipTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username='owner', password='testpass123'
        )
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.group_admin = User.objects.create_user(
            username='groupadmin', password='testpass123'
        )
        cls.group = Group.objects.create(name='Edit Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )
        GroupMembership.objects.create(
            user=cls.member, group=cls.group, role='member'
        )
        GroupMembership.objects.create(
            user=cls.group_admin, group=cls.group, role='admin'
        )
        cls.user_game = BoardGame.objects.create(
            name='User Catan', owner=cls.owner,
            min_players=3, max_players=4, complexity='medium',
        )
        cls.group_game = BoardGame.objects.create(
            name='Group Catan', group=cls.group,
            min_players=3, max_players=4, complexity='medium',
        )

    def test_edit_page_has_ownership_dropdown(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(
            reverse('game_edit', kwargs={'pk': self.user_game.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ownership_target')

    def test_edit_page_shows_current_ownership_as_self(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.get(
            reverse('game_edit', kwargs={'pk': self.user_game.pk})
        )
        self.assertEqual(
            response.context['current_ownership'], 'self'
        )

    def test_edit_page_shows_current_ownership_as_group(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('game_edit', kwargs={'pk': self.group_game.pk})
        )
        self.assertEqual(
            response.context['current_ownership'],
            f'group:{self.group.slug}'
        )

    def test_owner_can_change_to_group(self):
        self.client.login(username='owner', password='testpass123')
        GroupMembership.objects.create(
            user=self.owner, group=self.group, role='organizer'
        )
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.user_game.pk}),
            {
                'name': 'User Catan',
                'min_players': 3,
                'max_players': 4,
                'complexity': 'medium',
                'ownership_target': f'group:{self.group.slug}',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user_game.refresh_from_db()
        self.assertIsNone(self.user_game.owner)
        self.assertEqual(self.user_game.group, self.group)

    def test_organizer_can_change_group_game_to_self(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.group_game.pk}),
            {
                'name': 'Group Catan',
                'min_players': 3,
                'max_players': 4,
                'complexity': 'medium',
                'ownership_target': 'self',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.group_game.refresh_from_db()
        self.assertEqual(self.group_game.owner, self.organizer)
        self.assertIsNone(self.group_game.group)

    def test_member_cannot_change_ownership(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.group_game.pk}),
            {
                'name': 'Group Catan',
                'min_players': 3,
                'max_players': 4,
                'complexity': 'medium',
                'ownership_target': 'self',
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_cannot_change_to_group_not_organizer_of(self):
        other_group = Group.objects.create(name='No Access Group')
        self.client.login(username='owner', password='testpass123')
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.user_game.pk}),
            {
                'name': 'User Catan',
                'min_players': 3,
                'max_players': 4,
                'complexity': 'medium',
                'ownership_target': f'group:{other_group.slug}',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.user_game.refresh_from_db()
        self.assertEqual(self.user_game.owner, self.owner)
        self.assertIsNone(self.user_game.group)

    def test_ownership_unchanged_does_not_require_confirmation(self):
        self.client.login(username='owner', password='testpass123')
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.user_game.pk}),
            {
                'name': 'User Catan Updated',
                'min_players': 3,
                'max_players': 4,
                'complexity': 'medium',
                'ownership_target': 'self',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user_game.refresh_from_db()
        self.assertEqual(self.user_game.name, 'User Catan Updated')

    def test_group_admin_can_change_group_game_ownership(self):
        self.client.login(username='groupadmin', password='testpass123')
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.group_game.pk}),
            {
                'name': 'Group Catan',
                'min_players': 3,
                'max_players': 4,
                'complexity': 'medium',
                'ownership_target': 'self',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.group_game.refresh_from_db()
        self.assertEqual(self.group_game.owner, self.group_admin)
        self.assertIsNone(self.group_game.group)


@tag("integration")
class GroupGameAddRedirectTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.group = Group.objects.create(name='Redirect Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )

    def test_group_game_add_redirects_to_game_add(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': self.group.slug})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('group=', response.url)
        self.assertIn(self.group.slug, response.url)
        self.assertIn(reverse('game_add'), response.url)

    def test_group_game_add_post_still_works_via_redirect(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('group_game_add', kwargs={'slug': self.group.slug}),
            {
                'name': 'Redirect Game',
                'min_players': 2,
                'max_players': 4,
                'complexity': 'medium',
                'ownership_target': f'group:{self.group.slug}',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        game = BoardGame.objects.get(name='Redirect Game')
        self.assertEqual(game.group, self.group)
        self.assertIsNone(game.owner)

    def test_group_game_add_requires_login(self):
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': self.group.slug})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_group_game_add_nonexistent_group_404(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': 'nonexistent'})
        )
        self.assertEqual(response.status_code, 404)

    def test_group_game_add_disbanded_group_403(self):
        from django.utils import timezone
        self.group.disbanded_at = timezone.now()
        self.group.save()
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': self.group.slug})
        )
        self.assertEqual(response.status_code, 403)
        self.group.disbanded_at = None
        self.group.save()

    def test_group_game_add_member_forbidden(self):
        member = User.objects.create_user(
            username='member2', password='testpass123'
        )
        GroupMembership.objects.create(
            user=member, group=self.group, role='member'
        )
        self.client.login(username='member2', password='testpass123')
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': self.group.slug})
        )
        self.assertEqual(response.status_code, 403)
