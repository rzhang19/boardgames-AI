import os

from django.test import TestCase, override_settings, tag
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.templatetags.static import static

User = get_user_model()


@tag("integration")
class CSSMobileResponsiveTest(TestCase):

    def test_css_file_contains_mobile_media_query(self):
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '..', 'static', 'css', 'style.css'
        )
        css_path = os.path.normpath(css_path)
        with open(css_path, 'r') as f:
            css = f.read()
        self.assertIn('@media (max-width: 600px)', css)

    def test_css_file_contains_hamburger_styles(self):
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '..', 'static', 'css', 'style.css'
        )
        css_path = os.path.normpath(css_path)
        with open(css_path, 'r') as f:
            css = f.read()
        self.assertIn('.nav-hamburger', css)
        self.assertIn('.nav-links', css)
        self.assertIn('.nav-open', css)

    def test_css_file_contains_nav_actions_styles(self):
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '..', 'static', 'css', 'style.css'
        )
        css_path = os.path.normpath(css_path)
        with open(css_path, 'r') as f:
            css = f.read()
        self.assertIn('.nav-actions', css)

    def test_css_file_contains_card_based_table_styles(self):
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '..', 'static', 'css', 'style.css'
        )
        css_path = os.path.normpath(css_path)
        with open(css_path, 'r') as f:
            css = f.read()
        self.assertIn('attr(data-label)', css)
        self.assertIn('thead', css)

    def test_css_file_contains_form_grid_mobile(self):
        css_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '..', 'static', 'css', 'style.css'
        )
        css_path = os.path.normpath(css_path)
        with open(css_path, 'r') as f:
            css = f.read()
        self.assertIn('.form-grid', css)
        self.assertIn('grid-template-columns: 1fr', css)


@tag("integration")
class BaseTemplateMobileTest(TestCase):

    def test_base_template_has_viewport_meta_tag(self):
        from django.template.loader import get_template
        template = get_template('base.html')
        source = template.template.source
        self.assertIn('viewport', source)
        self.assertIn('width=device-width', source)

    def test_base_template_has_hamburger_button(self):
        from django.template.loader import get_template
        template = get_template('base.html')
        source = template.template.source
        self.assertIn('nav-hamburger', source)

    def test_base_template_has_nav_links_container(self):
        from django.template.loader import get_template
        template = get_template('base.html')
        source = template.template.source
        self.assertIn('nav-links', source)

    def test_base_template_has_nav_open_toggle(self):
        from django.template.loader import get_template
        template = get_template('base.html')
        source = template.template.source
        self.assertIn('nav-open', source)

    def test_base_template_has_nav_actions_container(self):
        from django.template.loader import get_template
        template = get_template('base.html')
        source = template.template.source
        self.assertIn('nav-actions', source)


@tag("integration")
class GameListDataLabelsTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')

        from club.models import BoardGame
        BoardGame.objects.create(name='Test Game', owner=self.user)

    def test_game_list_table_has_data_labels(self):
        response = self.client.get(reverse('game_list'))
        self.assertContains(response, 'data-label="Name"')
        self.assertContains(response, 'data-label="Players"')
        self.assertContains(response, 'data-label="Complexity"')
        self.assertContains(response, 'data-label="Owner"')


@tag("integration")
class EventListDataLabelsTest(TestCase):

    def test_event_list_table_has_data_labels(self):
        user = User.objects.create_user(username='org', password='testpass123', is_organizer=True)
        self.client.login(username='org', password='testpass123')

        from club.models import Event
        from django.utils import timezone
        import datetime as dt
        event = Event.objects.create(
            title='Test Event',
            date=timezone.now() + dt.timedelta(days=7),
            location='Test Location',
            created_by=user,
            voting_deadline=timezone.now() + dt.timedelta(days=6),
        )

        response = self.client.get(reverse('event_list'))
        self.assertContains(response, 'data-label="Title"')
        self.assertContains(response, 'data-label="Date"')
        self.assertContains(response, 'data-label="Location"')
        self.assertContains(response, 'data-label="Created By"')


@tag("integration")
class EventResultsDataLabelsTest(TestCase):

    def test_event_results_table_has_data_labels(self):
        user = User.objects.create_user(username='voter', password='testpass123')
        self.client.login(username='voter', password='testpass123')

        from club.models import Event, BoardGame, EventAttendance, Vote
        from django.utils import timezone
        import datetime as dt
        event = Event.objects.create(
            title='Result Event',
            date=timezone.now() + dt.timedelta(days=7),
            created_by=user,
            voting_open=False,
            voting_deadline=timezone.now() + dt.timedelta(days=6),
        )
        game = BoardGame.objects.create(name='Test Game', owner=user)
        EventAttendance.objects.create(user=user, event=event)
        Vote.objects.create(user=user, event=event, board_game=game, rank=1)

        response = self.client.get(reverse('event_results', kwargs={'pk': event.pk}))
        self.assertContains(response, 'data-label="Rank"')
        self.assertContains(response, 'data-label="Game"')
        self.assertContains(response, 'data-label="Score"')
