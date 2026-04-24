from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from club.models import Group, GroupMembership

User = get_user_model()


class AdminConfirmationTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(username='admin', password='testpass123')
        self.other_admin = User.objects.create_user(username='other_admin', password='testpass123')
        self.organizer = User.objects.create_user(username='organizer', password='testpass123')
        self.member = User.objects.create_user(username='member', password='testpass123')
        self.group = Group.objects.create(name='Test Group', slug='test-group')
        GroupMembership.objects.create(user=self.admin, group=self.group, role='admin')
        GroupMembership.objects.create(user=self.other_admin, group=self.group, role='admin')
        GroupMembership.objects.create(user=self.organizer, group=self.group, role='organizer')
        GroupMembership.objects.create(user=self.member, group=self.group, role='member')

    def _post_action(self, user_id, action, confirmed=None):
        data = {'user_id': user_id, 'action': action}
        if confirmed is not None:
            data['confirmed'] = confirmed
        return self.client.post(
            reverse('group_members_manage', kwargs={'slug': self.group.slug}),
            data,
        )

    def test_demoting_admin_without_confirmation_renders_confirm_page(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'demote_member')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Are you sure')
        membership = GroupMembership.objects.get(user=self.other_admin, group=self.group)
        self.assertEqual(membership.role, 'admin')

    def test_demoting_admin_with_confirmation_performs_demotion(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'demote_member', confirmed='true')
        self.assertEqual(response.status_code, 200)
        membership = GroupMembership.objects.get(user=self.other_admin, group=self.group)
        self.assertEqual(membership.role, 'member')

    def test_removing_admin_without_confirmation_renders_confirm_page(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'remove')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Are you sure')
        self.assertTrue(
            GroupMembership.objects.filter(user=self.other_admin, group=self.group, role='admin').exists()
        )

    def test_removing_admin_with_confirmation_performs_removal(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'remove', confirmed='true')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            GroupMembership.objects.filter(user=self.other_admin, group=self.group).exists()
        )

    def test_demoting_admin_to_organizer_without_confirmation(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'demote_organizer')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Are you sure')
        membership = GroupMembership.objects.get(user=self.other_admin, group=self.group)
        self.assertEqual(membership.role, 'admin')

    def test_demoting_admin_to_organizer_with_confirmation(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'demote_organizer', confirmed='true')
        self.assertEqual(response.status_code, 200)
        membership = GroupMembership.objects.get(user=self.other_admin, group=self.group)
        self.assertEqual(membership.role, 'organizer')

    def test_non_admin_demotion_works_without_confirmation(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.organizer.pk, 'demote_member')
        self.assertEqual(response.status_code, 200)
        membership = GroupMembership.objects.get(user=self.organizer, group=self.group)
        self.assertEqual(membership.role, 'member')

    def test_non_admin_removal_works_without_confirmation(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.member.pk, 'remove')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            GroupMembership.objects.filter(user=self.member, group=self.group).exists()
        )

    def test_confirmation_page_shows_removal_warning(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'remove')
        self.assertContains(response, 'votes and RSVPs')

    def test_confirmation_page_cancel_link(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.other_admin.pk, 'demote_member')
        self.assertContains(response, reverse('group_members_manage', kwargs={'slug': self.group.slug}))

    def test_non_admin_demote_organizer_no_confirmation(self):
        self.client.login(username='admin', password='testpass123')
        response = self._post_action(self.organizer.pk, 'demote_organizer')
        self.assertEqual(response.status_code, 200)
        membership = GroupMembership.objects.get(user=self.organizer, group=self.group)
        self.assertEqual(membership.role, 'organizer')
