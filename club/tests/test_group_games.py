from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from club.models import BoardGame, Group, GroupMembership

User = get_user_model()


class GroupGamesViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='member1', password='testpass123')
        self.other_user = User.objects.create_user(username='member2', password='testpass123')
        self.outsider = User.objects.create_user(username='outsider', password='testpass123')
        self.group = Group.objects.create(name='Test Group', slug='test-group', discoverable=True)
        GroupMembership.objects.create(user=self.user, group=self.group, role='member')
        GroupMembership.objects.create(user=self.other_user, group=self.group, role='member')
        self.game1 = BoardGame.objects.create(name='Catan', owner=self.user, min_players=3, max_players=4)
        self.game2 = BoardGame.objects.create(name='Risk', owner=self.other_user, min_players=2, max_players=6)
        self.game3 = BoardGame.objects.create(
            name='Monopoly', owner=self.outsider, min_players=2, max_players=8
        )

    def test_requires_login(self):
        response = self.client.get(reverse('group_games', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_member_can_view_group_games(self):
        self.client.login(username='member1', password='testpass123')
        response = self.client.get(reverse('group_games', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 200)

    def test_shows_only_games_owned_by_group_members(self):
        self.client.login(username='member1', password='testpass123')
        response = self.client.get(reverse('group_games', kwargs={'slug': self.group.slug}))
        self.assertContains(response, 'Catan')
        self.assertContains(response, 'Risk')
        self.assertNotContains(response, 'Monopoly')

    def test_non_discoverable_group_hidden_from_non_members(self):
        self.group.discoverable = False
        self.group.save()
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(reverse('group_games', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 403)

    def test_discoverable_group_visible_to_non_members(self):
        self.client.login(username='outsider', password='testpass123')
        response = self.client.get(reverse('group_games', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 200)

    def test_leaving_group_removes_your_games(self):
        GroupMembership.objects.filter(user=self.user, group=self.group).delete()
        self.client.login(username='member2', password='testpass123')
        response = self.client.get(reverse('group_games', kwargs={'slug': self.group.slug}))
        self.assertNotContains(response, 'Catan')
        self.assertContains(response, 'Risk')

    def test_disbanded_group_returns_403(self):
        self.group.disbanded_at = timezone.now()
        self.group.save()
        self.client.login(username='member1', password='testpass123')
        response = self.client.get(reverse('group_games', kwargs={'slug': self.group.slug}))
        self.assertEqual(response.status_code, 403)

    def test_empty_state_when_no_members_own_games(self):
        group2 = Group.objects.create(name='Empty Group', slug='empty-group', discoverable=True)
        user_no_games = User.objects.create_user(username='nogames', password='testpass123')
        GroupMembership.objects.create(user=user_no_games, group=group2, role='member')
        self.client.login(username='member1', password='testpass123')
        response = self.client.get(reverse('group_games', kwargs={'slug': group2.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No members have added games yet')

    def test_games_link_to_game_detail(self):
        self.client.login(username='member1', password='testpass123')
        response = self.client.get(reverse('group_games', kwargs={'slug': self.group.slug}))
        self.assertContains(response, reverse('game_detail', kwargs={'pk': self.game1.pk}))

    def test_member_games_appear_in_all_their_groups(self):
        group2 = Group.objects.create(name='Other Group', slug='other-group', discoverable=True)
        GroupMembership.objects.create(user=self.user, group=group2, role='member')
        self.client.login(username='member1', password='testpass123')
        response = self.client.get(reverse('group_games', kwargs={'slug': group2.slug}))
        self.assertContains(response, 'Catan')

    def test_invalid_group_slug_returns_404(self):
        self.client.login(username='member1', password='testpass123')
        response = self.client.get(reverse('group_games', kwargs={'slug': 'nonexistent'}))
        self.assertEqual(response.status_code, 404)
