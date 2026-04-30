from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from club.models import BoardGame, Event, EventAttendance, Group, GroupMembership, Notification, Vote
from club.borda import calculate_borda_scores
from club.notifications import notify_group_game_added, notify_group_game_deleted

User = get_user_model()


@tag("unit")
class BoardGameGroupOwnerTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='gameowner', password='testpass123'
        )
        cls.group = Group.objects.create(name='Test Group')

    def test_create_board_game_with_group_owner(self):
        game = BoardGame.objects.create(
            name='Group Catan',
            group=self.group,
            min_players=3,
            max_players=4,
            complexity='medium',
        )
        self.assertEqual(game.name, 'Group Catan')
        self.assertEqual(game.group, self.group)
        self.assertIsNone(game.owner)

    def test_create_board_game_with_user_owner(self):
        game = BoardGame.objects.create(
            name='User Catan',
            owner=self.user,
            min_players=3,
            max_players=4,
        )
        self.assertEqual(game.owner, self.user)
        self.assertIsNone(game.group)

    def test_create_board_game_with_both_owner_and_group_is_not_preferred(self):
        game = BoardGame.objects.create(
            name='Dual Owner Game',
            owner=self.user,
            group=self.group,
        )
        self.assertEqual(game.owner, self.user)
        self.assertEqual(game.group, self.group)

    def test_create_board_game_with_neither_owner_nor_group_possible(self):
        game = BoardGame.objects.create(
            name='Orphan Game',
        )
        self.assertIsNone(game.owner)
        self.assertIsNone(game.group)

    def test_group_owned_game_cascade_on_group_delete(self):
        game = BoardGame.objects.create(
            name='Doomed Game',
            group=self.group,
        )
        self.group.delete()
        self.assertFalse(BoardGame.objects.filter(pk=game.pk).exists())

    def test_user_owned_game_unaffected_by_unrelated_group_delete(self):
        other_group = Group.objects.create(name='Other Group')
        game = BoardGame.objects.create(
            name='Safe Game',
            owner=self.user,
        )
        other_group.delete()
        self.assertTrue(BoardGame.objects.filter(pk=game.pk).exists())

    def test_group_owned_game_bgg_fields(self):
        game = BoardGame.objects.create(
            name='BGG Group Game',
            group=self.group,
            bgg_id=42,
            bgg_link='https://boardgamegeek.com/boardgame/42/test',
        )
        self.assertEqual(game.bgg_id, 42)
        self.assertEqual(game.bgg_link, 'https://boardgamegeek.com/boardgame/42/test')

    def test_group_owned_game_complexity(self):
        game = BoardGame.objects.create(
            name='Complex Group Game',
            group=self.group,
            complexity='heavy',
        )
        self.assertEqual(game.complexity, 'heavy')

    def test_group_owned_game_string_representation(self):
        game = BoardGame.objects.create(
            name='Group Chess',
            group=self.group,
        )
        self.assertEqual(str(game), 'Group Chess')


@tag("unit")
class GroupGamesWithGroupOwnershipTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='member1', password='testpass123'
        )
        cls.other_user = User.objects.create_user(
            username='member2', password='testpass123'
        )
        cls.outsider = User.objects.create_user(
            username='outsider', password='testpass123'
        )
        cls.group = Group.objects.create(name='Game Group')
        GroupMembership.objects.create(
            user=cls.user, group=cls.group, role='member'
        )
        GroupMembership.objects.create(
            user=cls.other_user, group=cls.group, role='member'
        )

    def test_games_includes_user_owned_games(self):
        game = BoardGame.objects.create(name='User Game', owner=self.user)
        self.assertIn(game, self.group.games())

    def test_games_includes_group_owned_games(self):
        game = BoardGame.objects.create(name='Group Game', group=self.group)
        self.assertIn(game, self.group.games())

    def test_games_includes_both_user_and_group_owned(self):
        user_game = BoardGame.objects.create(name='User Game', owner=self.user)
        group_game = BoardGame.objects.create(name='Group Game', group=self.group)
        games = self.group.games()
        self.assertIn(user_game, games)
        self.assertIn(group_game, games)
        self.assertEqual(games.count(), 2)

    def test_games_excludes_other_group_owned_games(self):
        other_group = Group.objects.create(name='Other Group')
        game = BoardGame.objects.create(name='Other Group Game', group=other_group)
        self.assertNotIn(game, self.group.games())

    def test_games_excludes_outsider_user_owned_games(self):
        game = BoardGame.objects.create(
            name='Outsider Game', owner=self.outsider
        )
        self.assertNotIn(game, self.group.games())

    def test_group_game_does_not_appear_in_other_group_games(self):
        group2 = Group.objects.create(name='Second Group')
        game = BoardGame.objects.create(name='Group Game', group=self.group)
        self.assertNotIn(game, group2.games())

    def test_games_count_reflects_both_types(self):
        BoardGame.objects.create(name='User Game 1', owner=self.user)
        BoardGame.objects.create(name='User Game 2', owner=self.other_user)
        BoardGame.objects.create(name='Group Game 1', group=self.group)
        self.assertEqual(self.group.games().count(), 3)

    def test_member_leaving_does_not_remove_group_owned_games(self):
        group_game = BoardGame.objects.create(
            name='Group Game', group=self.group
        )
        GroupMembership.objects.filter(
            user=self.user, group=self.group
        ).delete()
        self.assertIn(group_game, self.group.games())

    def test_group_owned_game_from_disbanded_group_still_queryable(self):
        game = BoardGame.objects.create(name='Group Game', group=self.group)
        self.group.disbanded_at = timezone.now()
        self.group.save()
        self.assertTrue(BoardGame.objects.filter(pk=game.pk).exists())


@tag("integration")
class GroupGameAddViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.outsider = User.objects.create_user(
            username='outsider', password='testpass123'
        )
        cls.group = Group.objects.create(name='Game Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )
        GroupMembership.objects.create(
            user=cls.member, group=cls.group, role='member'
        )

    def test_add_page_requires_login(self):
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': self.group.slug})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_organizer_can_access_add_page(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': self.group.slug})
        )
        self.assertEqual(response.status_code, 200)

    def test_member_cannot_access_add_page(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': self.group.slug})
        )
        self.assertEqual(response.status_code, 403)

    def test_outsider_cannot_access_add_page(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': self.group.slug})
        )
        self.assertEqual(response.status_code, 403)

    def test_create_group_game_with_all_fields(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('group_game_add', kwargs={'slug': self.group.slug}),
            {
                'name': 'Group Catan',
                'description': 'Group copy of Catan',
                'min_players': 3,
                'max_players': 4,
                'complexity': 'medium',
            },
        )
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Group Catan')
        self.assertEqual(game.group, self.group)
        self.assertIsNone(game.owner)
        self.assertEqual(game.description, 'Group copy of Catan')
        self.assertEqual(game.min_players, 3)
        self.assertEqual(game.max_players, 4)
        self.assertEqual(game.complexity, 'medium')
        self.assertEqual(
            response.url, reverse('game_detail', kwargs={'pk': game.pk})
        )

    def test_create_group_game_with_required_fields_only(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('group_game_add', kwargs={'slug': self.group.slug}),
            {
                'name': 'Group Chess',
                'min_players': 2,
                'max_players': 2,
                'complexity': 'light',
            },
        )
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Group Chess')
        self.assertEqual(game.group, self.group)
        self.assertIsNone(game.owner)
        self.assertEqual(game.description, '')

    def test_create_group_game_without_name_fails(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('group_game_add', kwargs={'slug': self.group.slug}),
            {'name': '', 'min_players': 2, 'max_players': 4, 'complexity': 'light'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            BoardGame.objects.filter(group=self.group).exists()
        )

    def test_create_group_game_without_complexity_fails(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('group_game_add', kwargs={'slug': self.group.slug}),
            {'name': 'No Complexity', 'min_players': 2, 'max_players': 4},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            BoardGame.objects.filter(name='No Complexity').exists()
        )

    def test_group_game_appears_in_group_games(self):
        self.client.login(username='organizer', password='testpass123')
        self.client.post(
            reverse('group_game_add', kwargs={'slug': self.group.slug}),
            {
                'name': 'Group Risk',
                'min_players': 2,
                'max_players': 6,
                'complexity': 'medium',
            },
        )
        self.assertIn(
            BoardGame.objects.get(name='Group Risk'), self.group.games()
        )

    def test_create_group_game_with_bgg_id(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('group_game_add', kwargs={'slug': self.group.slug}),
            {
                'name': 'BGG Group Game',
                'min_players': 2,
                'max_players': 4,
                'bgg_id': 42,
                'complexity': 'medium',
            },
        )
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='BGG Group Game')
        self.assertEqual(game.bgg_id, 42)

    def test_create_group_game_with_unlimited_max_players(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('group_game_add', kwargs={'slug': self.group.slug}),
            {
                'name': 'Unlimited Group Game',
                'min_players': 2,
                'max_players_unlimited': 'on',
                'complexity': 'light',
            },
        )
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Unlimited Group Game')
        self.assertEqual(game.max_players, 0)

    def test_admin_can_access_add_page(self):
        admin = User.objects.create_user(
            username='groupadmin', password='testpass123'
        )
        GroupMembership.objects.create(
            user=admin, group=self.group, role='admin'
        )
        self.client.login(username='groupadmin', password='testpass123')
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': self.group.slug})
        )
        self.assertEqual(response.status_code, 200)

    def test_nonexistent_group_returns_404(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': 'nonexistent'})
        )
        self.assertEqual(response.status_code, 404)

    def test_disbanded_group_returns_403(self):
        self.group.disbanded_at = timezone.now()
        self.group.save()
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('group_game_add', kwargs={'slug': self.group.slug})
        )
        self.assertEqual(response.status_code, 403)


@tag("integration")
class GroupGameEditViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.outsider = User.objects.create_user(
            username='outsider', password='testpass123'
        )
        cls.group = Group.objects.create(name='Game Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )
        GroupMembership.objects.create(
            user=cls.member, group=cls.group, role='member'
        )
        cls.game = BoardGame.objects.create(
            name='Group Catan',
            group=cls.group,
            min_players=3,
            max_players=4,
            complexity='medium',
        )

    def test_organizer_can_access_edit_page(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('game_edit', kwargs={'pk': self.game.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_organizer_can_update_group_game(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.game.pk}),
            {
                'name': 'Group Catan: Updated',
                'description': 'Now with expansion',
                'min_players': 3,
                'max_players': 6,
                'complexity': 'medium_heavy',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.game.refresh_from_db()
        self.assertEqual(self.game.name, 'Group Catan: Updated')
        self.assertEqual(self.game.max_players, 6)
        self.assertEqual(self.game.group, self.group)
        self.assertIsNone(self.game.owner)

    def test_member_cannot_access_edit_page(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('game_edit', kwargs={'pk': self.game.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_member_cannot_update_group_game(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.game.pk}),
            {
                'name': 'Hacked',
                'min_players': 2,
                'max_players': 2,
                'complexity': 'light',
            },
        )
        self.assertEqual(response.status_code, 403)
        self.game.refresh_from_db()
        self.assertEqual(self.game.name, 'Group Catan')

    def test_outsider_cannot_edit_group_game(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(
            reverse('game_edit', kwargs={'pk': self.game.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_group_admin_can_edit_group_game(self):
        admin = User.objects.create_user(
            username='groupadmin', password='testpass123'
        )
        GroupMembership.objects.create(
            user=admin, group=self.group, role='admin'
        )
        self.client.login(username='groupadmin', password='testpass123')
        response = self.client.post(
            reverse('game_edit', kwargs={'pk': self.game.pk}),
            {
                'name': 'Admin Edited',
                'min_players': 2,
                'max_players': 4,
                'complexity': 'heavy',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.game.refresh_from_db()
        self.assertEqual(self.game.name, 'Admin Edited')

    def test_superuser_can_edit_group_game(self):
        User.objects.create_superuser(
            username='super', password='superpass123'
        )
        self.client.login(username='super', password='superpass123')
        response = self.client.get(
            reverse('game_edit', kwargs={'pk': self.game.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_owner_of_user_game_still_can_edit(self):
        user_game = BoardGame.objects.create(
            name='User Game', owner=self.organizer,
            min_players=2, max_players=4, complexity='light',
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('game_edit', kwargs={'pk': user_game.pk})
        )
        self.assertEqual(response.status_code, 200)


@tag("integration")
class GroupGameDeleteViewTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.outsider = User.objects.create_user(
            username='outsider', password='testpass123'
        )
        cls.group = Group.objects.create(name='Game Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )
        GroupMembership.objects.create(
            user=cls.member, group=cls.group, role='member'
        )
        cls.game = BoardGame.objects.create(
            name='Group Catan',
            group=cls.group,
            min_players=3,
            max_players=4,
            complexity='medium',
        )

    def test_organizer_can_access_delete_page(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('game_delete', kwargs={'pk': self.game.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_organizer_can_delete_group_game(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('game_delete', kwargs={'pk': self.game.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BoardGame.objects.filter(pk=self.game.pk).exists())

    def test_member_cannot_access_delete_page(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('game_delete', kwargs={'pk': self.game.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_member_cannot_delete_group_game(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.post(
            reverse('game_delete', kwargs={'pk': self.game.pk})
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(BoardGame.objects.filter(pk=self.game.pk).exists())

    def test_outsider_cannot_delete_group_game(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.post(
            reverse('game_delete', kwargs={'pk': self.game.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_group_admin_can_delete_group_game(self):
        admin = User.objects.create_user(
            username='groupadmin', password='testpass123'
        )
        GroupMembership.objects.create(
            user=admin, group=self.group, role='admin'
        )
        self.client.login(username='groupadmin', password='testpass123')
        response = self.client.post(
            reverse('game_delete', kwargs={'pk': self.game.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BoardGame.objects.filter(pk=self.game.pk).exists())

    def test_superuser_can_delete_group_game(self):
        User.objects.create_superuser(
            username='super', password='superpass123'
        )
        self.client.login(username='super', password='superpass123')
        response = self.client.post(
            reverse('game_delete', kwargs={'pk': self.game.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BoardGame.objects.filter(pk=self.game.pk).exists())

    def test_owner_of_user_game_still_can_delete(self):
        user_game = BoardGame.objects.create(
            name='User Game', owner=self.organizer,
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.post(
            reverse('game_delete', kwargs={'pk': user_game.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BoardGame.objects.filter(pk=user_game.pk).exists())


@tag("integration")
class GroupGameDetailDisplayTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.group = Group.objects.create(name='Display Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )
        GroupMembership.objects.create(
            user=cls.member, group=cls.group, role='member'
        )

    def test_group_game_detail_shows_group_name_as_owner(self):
        game = BoardGame.objects.create(
            name='Group Game', group=self.group,
            min_players=2, max_players=4, complexity='light',
        )
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.group.name)
        self.assertContains(response, '(Group)')

    def test_user_game_detail_shows_username_as_owner(self):
        game = BoardGame.objects.create(
            name='User Game', owner=self.organizer,
            min_players=2, max_players=4, complexity='light',
        )
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(response, self.organizer.username)
        self.assertNotContains(response, '(Group)')

    def test_organizer_sees_edit_delete_buttons_on_group_game(self):
        game = BoardGame.objects.create(
            name='Group Game', group=self.group,
            min_players=2, max_players=4, complexity='light',
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertContains(response, reverse('game_edit', kwargs={'pk': game.pk}))
        self.assertContains(response, reverse('game_delete', kwargs={'pk': game.pk}))

    def test_member_does_not_see_edit_delete_buttons_on_group_game(self):
        game = BoardGame.objects.create(
            name='Group Game', group=self.group,
            min_players=2, max_players=4, complexity='light',
        )
        self.client.login(username='member', password='testpass123')
        response = self.client.get(reverse('game_detail', kwargs={'pk': game.pk}))
        self.assertNotContains(response, reverse('game_edit', kwargs={'pk': game.pk}))
        self.assertNotContains(response, reverse('game_delete', kwargs={'pk': game.pk}))

    def test_delete_confirmation_shows_group_owned_warning(self):
        game = BoardGame.objects.create(
            name='Group Game', group=self.group,
            min_players=2, max_players=4, complexity='light',
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(reverse('game_delete', kwargs={'pk': game.pk}))
        self.assertContains(response, 'group-owned game')
        self.assertContains(response, self.group.name)


@tag("integration")
class GroupGamesPageDisplayTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.group = Group.objects.create(name='Games Page Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )
        GroupMembership.objects.create(
            user=cls.member, group=cls.group, role='member'
        )

    def test_organizer_sees_add_group_game_button(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('group_games', kwargs={'slug': self.group.slug})
        )
        self.assertContains(response, reverse('group_game_add', kwargs={'slug': self.group.slug}))

    def test_member_does_not_see_add_group_game_button(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('group_games', kwargs={'slug': self.group.slug})
        )
        self.assertNotContains(response, reverse('group_game_add', kwargs={'slug': self.group.slug}))

    def test_group_game_shows_group_name_in_owner_column(self):
        BoardGame.objects.create(
            name='Group Catan', group=self.group,
            min_players=3, max_players=4, complexity='medium',
        )
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('group_games', kwargs={'slug': self.group.slug})
        )
        self.assertContains(response, '(Group)')

    def test_user_game_shows_username_in_owner_column(self):
        BoardGame.objects.create(
            name='User Game', owner=self.member,
            min_players=2, max_players=4, complexity='light',
        )
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('group_games', kwargs={'slug': self.group.slug})
        )
        self.assertContains(response, self.member.username)

    def test_filter_hides_group_owned_games(self):
        BoardGame.objects.create(
            name='Group Game', group=self.group,
            min_players=2, max_players=4, complexity='light',
        )
        BoardGame.objects.create(
            name='User Game', owner=self.member,
            min_players=2, max_players=4, complexity='light',
        )
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('group_games', kwargs={'slug': self.group.slug}),
            {'group_owned': '0'},
        )
        self.assertNotContains(response, 'Group Game')
        self.assertContains(response, 'User Game')


@tag("integration")
class GroupDashboardAddButtonTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.group = Group.objects.create(name='Dashboard Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )
        GroupMembership.objects.create(
            user=cls.member, group=cls.group, role='member'
        )

    def test_organizer_sees_add_group_game_on_dashboard(self):
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('group_dashboard', kwargs={'slug': self.group.slug})
        )
        self.assertContains(response, reverse('group_game_add', kwargs={'slug': self.group.slug}))

    def test_member_does_not_see_add_group_game_on_dashboard(self):
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('group_dashboard', kwargs={'slug': self.group.slug})
        )
        self.assertNotContains(response, reverse('group_game_add', kwargs={'slug': self.group.slug}))


@tag("integration")
class GroupGameVotingIntegrationTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.group = Group.objects.create(name='Voting Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )
        GroupMembership.objects.create(
            user=cls.member, group=cls.group, role='member'
        )
        cls.event = Event.objects.create(
            title='Game Night',
            date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=cls.organizer,
            group=cls.group,
        )
        EventAttendance.objects.create(user=cls.member, event=cls.event)

    def test_group_game_appears_in_vote_page_games(self):
        group_game = BoardGame.objects.create(
            name='Group Catan', group=self.group,
            min_players=3, max_players=4, complexity='medium',
        )
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('event_vote', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk,
            })
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(group_game, response.context['games'])

    def test_attendee_can_vote_for_group_owned_game(self):
        group_game = BoardGame.objects.create(
            name='Group Catan', group=self.group,
            min_players=3, max_players=4, complexity='medium',
        )
        self.client.login(username='member', password='testpass123')
        response = self.client.post(
            reverse('event_vote', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk,
            }),
            {
                'form-TOTAL_FORMS': '1',
                'form-INITIAL_FORMS': '0',
                'form-MIN_NUM_FORMS': '0',
                'form-MAX_NUM_FORMS': '1000',
                'form-0-board_game': str(group_game.pk),
                'form-0-rank': '1',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Vote.objects.filter(
            user=self.member, event=self.event,
            board_game=group_game, rank=1,
        ).exists())

    def test_results_display_group_owned_game_name(self):
        group_game = BoardGame.objects.create(
            name='Group Catan', group=self.group,
            min_players=3, max_players=4, complexity='medium',
        )
        Vote.objects.create(
            user=self.member, event=self.event,
            board_game=group_game, rank=1,
        )
        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk,
            })
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Group Catan')

    def test_mixed_user_and_group_games_in_vote_pool(self):
        user_game = BoardGame.objects.create(
            name='User Chess', owner=self.organizer,
            min_players=2, max_players=2, complexity='light',
        )
        group_game = BoardGame.objects.create(
            name='Group Catan', group=self.group,
            min_players=3, max_players=4, complexity='medium',
        )
        self.client.login(username='member', password='testpass123')
        response = self.client.get(
            reverse('event_vote', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk,
            })
        )
        games = list(response.context['games'])
        self.assertIn(user_game, games)
        self.assertIn(group_game, games)


@tag("unit")
class GroupGameBordaScoreTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.group = Group.objects.create(name='Borda Group')
        cls.event = Event.objects.create(
            title='Borda Event',
            date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=cls.organizer,
            group=cls.group,
        )
        cls.group_game = BoardGame.objects.create(
            name='Group Catan', group=cls.group,
            min_players=3, max_players=4, complexity='medium',
        )
        cls.user_game = BoardGame.objects.create(
            name='User Chess', owner=cls.organizer,
            min_players=2, max_players=2, complexity='light',
        )

    def test_borda_score_for_group_owned_game(self):
        user = User.objects.create_user(username='voter', password='testpass123')
        EventAttendance.objects.create(user=user, event=self.event)
        Vote.objects.create(
            user=user, event=self.event,
            board_game=self.group_game, rank=1,
        )
        Vote.objects.create(
            user=user, event=self.event,
            board_game=self.user_game, rank=2,
        )
        scores = calculate_borda_scores(self.event)
        self.assertEqual(scores[self.group_game.pk], 2)
        self.assertEqual(scores[self.user_game.pk], 1)

    def test_borda_group_game_scores_equal_to_user_game_with_same_votes(self):
        user1 = User.objects.create_user(username='voter1', password='testpass123')
        EventAttendance.objects.create(user=user1, event=self.event)
        Vote.objects.create(
            user=user1, event=self.event,
            board_game=self.group_game, rank=1,
        )
        Vote.objects.create(
            user=user1, event=self.event,
            board_game=self.user_game, rank=2,
        )
        user2 = User.objects.create_user(username='voter2', password='testpass123')
        EventAttendance.objects.create(user=user2, event=self.event)
        Vote.objects.create(
            user=user2, event=self.event,
            board_game=self.group_game, rank=2,
        )
        Vote.objects.create(
            user=user2, event=self.event,
            board_game=self.user_game, rank=1,
        )
        scores = calculate_borda_scores(self.event)
        self.assertEqual(scores[self.group_game.pk], scores[self.user_game.pk])


@tag("unit")
class NotifyGroupGameAddedTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.outsider = User.objects.create_user(
            username='outsider', password='testpass123'
        )
        cls.group = Group.objects.create(name='Game Notif Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )
        GroupMembership.objects.create(
            user=cls.member, group=cls.group, role='member'
        )

    def test_notifies_all_members_except_actor(self):
        game = BoardGame.objects.create(name='Group Catan', group=self.group)
        notify_group_game_added(self.group, game, self.organizer)
        self.assertTrue(Notification.objects.filter(user=self.member).exists())
        self.assertFalse(Notification.objects.filter(user=self.organizer).exists())
        self.assertFalse(Notification.objects.filter(user=self.outsider).exists())

    def test_notification_content(self):
        game = BoardGame.objects.create(name='Group Catan', group=self.group)
        notify_group_game_added(self.group, game, self.organizer)
        notif = Notification.objects.get(user=self.member)
        self.assertEqual(notif.notification_type, 'group_game_added')
        self.assertIn('Group Catan', notif.message)
        self.assertIn('Game Notif Group', notif.message)
        self.assertEqual(notif.url, f'/groups/{self.group.slug}/games/')
        self.assertEqual(notif.url_label, 'View Games')

    def test_disbanded_group_sends_no_notification(self):
        self.group.disbanded_at = timezone.now()
        self.group.save()
        game = BoardGame.objects.create(name='Group Catan', group=self.group)
        notify_group_game_added(self.group, game, self.organizer)
        self.assertEqual(Notification.objects.count(), 0)


@tag("unit")
class NotifyGroupGameDeletedTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.outsider = User.objects.create_user(
            username='outsider', password='testpass123'
        )
        cls.group = Group.objects.create(name='Del Notif Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )
        GroupMembership.objects.create(
            user=cls.member, group=cls.group, role='member'
        )

    def test_notifies_all_members_except_actor(self):
        notify_group_game_deleted(self.group, 'Group Catan', self.organizer)
        self.assertTrue(Notification.objects.filter(user=self.member).exists())
        self.assertFalse(Notification.objects.filter(user=self.organizer).exists())
        self.assertFalse(Notification.objects.filter(user=self.outsider).exists())

    def test_notification_content(self):
        notify_group_game_deleted(self.group, 'Group Catan', self.organizer)
        notif = Notification.objects.get(user=self.member)
        self.assertEqual(notif.notification_type, 'group_game_deleted')
        self.assertIn('Group Catan', notif.message)
        self.assertIn('Del Notif Group', notif.message)
        self.assertEqual(notif.url, f'/groups/{self.group.slug}/games/')
        self.assertEqual(notif.url_label, 'View Games')

    def test_disbanded_group_sends_no_notification(self):
        self.group.disbanded_at = timezone.now()
        self.group.save()
        notify_group_game_deleted(self.group, 'Group Catan', self.organizer)
        self.assertEqual(Notification.objects.count(), 0)


@tag("integration")
class GroupGameNotificationIntegrationTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.group = Group.objects.create(name='Integration Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )
        GroupMembership.objects.create(
            user=cls.member, group=cls.group, role='member'
        )

    def test_add_group_game_sends_notification(self):
        self.client.login(username='organizer', password='testpass123')
        self.client.post(
            reverse('group_game_add', kwargs={'slug': self.group.slug}),
            {
                'name': 'Group Catan',
                'min_players': 3,
                'max_players': 4,
                'complexity': 'medium',
            },
        )
        self.assertTrue(Notification.objects.filter(user=self.member).exists())
        notif = Notification.objects.get(user=self.member)
        self.assertEqual(notif.notification_type, 'group_game_added')
        self.assertFalse(Notification.objects.filter(user=self.organizer).exists())

    def test_add_user_game_does_not_send_group_notification(self):
        self.client.login(username='organizer', password='testpass123')
        self.client.post(
            reverse('game_add'),
            {
                'name': 'User Chess',
                'min_players': 2,
                'max_players': 2,
                'complexity': 'light',
            },
        )
        self.assertFalse(
            Notification.objects.filter(notification_type='group_game_added').exists()
        )

    def test_delete_group_game_sends_notification(self):
        game = BoardGame.objects.create(
            name='Group Catan', group=self.group,
            min_players=3, max_players=4, complexity='medium',
        )
        self.client.login(username='organizer', password='testpass123')
        self.client.post(reverse('game_delete', kwargs={'pk': game.pk}))
        self.assertTrue(Notification.objects.filter(user=self.member).exists())
        notif = Notification.objects.get(user=self.member)
        self.assertEqual(notif.notification_type, 'group_game_deleted')
        self.assertIn('Group Catan', notif.message)

    def test_delete_user_game_does_not_send_group_notification(self):
        game = BoardGame.objects.create(
            name='User Chess', owner=self.organizer,
            min_players=2, max_players=2, complexity='light',
        )
        self.client.login(username='organizer', password='testpass123')
        self.client.post(reverse('game_delete', kwargs={'pk': game.pk}))
        self.assertFalse(
            Notification.objects.filter(notification_type='group_game_deleted').exists()
        )


@tag("integration")
class GroupOwnedGameFullFlowTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.organizer = User.objects.create_user(
            username='organizer', password='testpass123'
        )
        cls.member = User.objects.create_user(
            username='member', password='testpass123'
        )
        cls.group = Group.objects.create(name='Full Flow Group')
        GroupMembership.objects.create(
            user=cls.organizer, group=cls.group, role='organizer'
        )
        GroupMembership.objects.create(
            user=cls.member, group=cls.group, role='member'
        )
        cls.event = Event.objects.create(
            title='Full Flow Event',
            date='2026-06-01T18:00:00Z',
            voting_deadline='2026-06-01T18:00:00Z',
            created_by=cls.organizer,
            group=cls.group,
        )
        EventAttendance.objects.create(user=cls.member, event=cls.event)
        EventAttendance.objects.create(user=cls.organizer, event=cls.event)

    def test_full_group_game_lifecycle(self):
        self.client.login(username='organizer', password='testpass123')

        response = self.client.post(
            reverse('group_game_add', kwargs={'slug': self.group.slug}),
            {
                'name': 'Group Catan',
                'description': 'A group copy of Catan',
                'min_players': 3,
                'max_players': 4,
                'complexity': 'medium',
            },
        )
        self.assertEqual(response.status_code, 302)
        game = BoardGame.objects.get(name='Group Catan')
        self.assertEqual(game.group, self.group)
        self.assertIsNone(game.owner)

        Notification.objects.filter(notification_type='group_game_added').delete()

        self.assertIn(game, self.group.games())

        response = self.client.get(
            reverse('group_games', kwargs={'slug': self.group.slug})
        )
        self.assertContains(response, 'Group Catan')

        response = self.client.get(
            reverse('event_vote', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk,
            })
        )
        self.assertIn(game, list(response.context['games']))

        self.client.login(username='member', password='testpass123')
        response = self.client.post(
            reverse('event_vote', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk,
            }),
            {
                'form-TOTAL_FORMS': '1',
                'form-INITIAL_FORMS': '0',
                'form-MIN_NUM_FORMS': '0',
                'form-MAX_NUM_FORMS': '1000',
                'form-0-board_game': str(game.pk),
                'form-0-rank': '1',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Vote.objects.filter(
            user=self.member, event=self.event, board_game=game
        ).exists())

        scores = calculate_borda_scores(self.event)
        self.assertEqual(scores[game.pk], 1)

        self.client.login(username='organizer', password='testpass123')
        response = self.client.get(
            reverse('event_results', kwargs={
                'slug': self.group.slug, 'pk': self.event.pk,
            })
        )
        self.assertContains(response, 'Group Catan')
        self.assertContains(response, '1')

        Notification.objects.all().delete()

        response = self.client.post(
            reverse('game_edit', kwargs={'pk': game.pk}),
            {
                'name': 'Group Catan: Updated',
                'description': 'Now with expansion',
                'min_players': 3,
                'max_players': 6,
                'complexity': 'medium_heavy',
            },
        )
        self.assertEqual(response.status_code, 302)
        game.refresh_from_db()
        self.assertEqual(game.name, 'Group Catan: Updated')
        self.assertEqual(game.max_players, 6)

        Notification.objects.all().delete()

        response = self.client.post(
            reverse('game_delete', kwargs={'pk': game.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BoardGame.objects.filter(pk=game.pk).exists())

        self.assertTrue(
            Notification.objects.filter(
                notification_type='group_game_deleted',
            ).exists()
        )
