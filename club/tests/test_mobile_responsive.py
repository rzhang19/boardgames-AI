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
        self.assertContains(response, 'data-label="Owned By"')


@tag("integration")
class EventListDataLabelsTest(TestCase):

    def test_event_list_table_has_data_labels(self):
        user = User.objects.create_user(username='org', password='testpass123')
        self.client.login(username='org', password='testpass123')

        from club.models import Event, Group
        from django.utils import timezone
        import datetime as dt
        group = Group.objects.create(name='Test Group')
        event = Event.objects.create(
            title='Test Event',
            date=timezone.now() + dt.timedelta(days=7),
            location='Test Location',
            created_by=user,
            voting_deadline=timezone.now() + dt.timedelta(days=6),
            group=group,
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

        from club.models import Event, BoardGame, EventAttendance, Vote, Group, GroupMembership
        from django.utils import timezone
        import datetime as dt
        group = Group.objects.create(name='Test Group')
        GroupMembership.objects.create(user=user, group=group, role='organizer')
        event = Event.objects.create(
            title='Result Event',
            date=timezone.now() + dt.timedelta(days=7),
            created_by=user,
            voting_open=False,
            voting_deadline=timezone.now() + dt.timedelta(days=6),
            group=group,
        )
        game = BoardGame.objects.create(name='Test Game', owner=user)
        EventAttendance.objects.create(user=user, event=event)
        Vote.objects.create(user=user, event=event, board_game=game, rank=1)

        response = self.client.get(reverse('event_results', kwargs={'slug': event.group.slug, 'pk': event.pk}))
        self.assertContains(response, 'data-label="Rank"')
        self.assertContains(response, 'data-label="Game"')
        self.assertContains(response, 'data-label="Score"')


def _read_css():
    css_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        '..', 'static', 'css', 'style.css'
    )
    css_path = os.path.normpath(css_path)
    with open(css_path, 'r') as f:
        return f.read()


def _extract_all_media_blocks(css, media_query):
    blocks = []
    start = 0
    while True:
        idx = css.find(media_query, start)
        if idx == -1:
            break
        brace_start = css.find('{', idx)
        if brace_start == -1:
            break
        brace_count = 1
        i = brace_start + 1
        while i < len(css) and brace_count > 0:
            if css[i] == '{':
                brace_count += 1
            elif css[i] == '}':
                brace_count -= 1
            i += 1
        blocks.append(css[brace_start + 1:i - 1])
        start = i
    return blocks


def _extract_css_rule(css, selector):
    idx = css.find(selector)
    if idx == -1:
        return ''
    brace_start = css.find('{', idx)
    if brace_start == -1:
        return ''
    brace_end = css.find('}', brace_start)
    if brace_end == -1:
        return ''
    return css[brace_start + 1:brace_end]


def _extract_mobile_nav_links_block(css):
    blocks = _extract_all_media_blocks(css, '@media (max-width: 600px)')
    for block in blocks:
        rule = _extract_css_rule(block, '.nav-links')
        if rule:
            return rule
    return ''


def _extract_mobile_nav_open_block(css):
    blocks = _extract_all_media_blocks(css, '@media (max-width: 600px)')
    for block in blocks:
        rule = _extract_css_rule(block, '.nav-links.nav-open')
        if rule:
            return rule
    return ''


def _read_base_template():
    from django.template.loader import get_template
    return get_template('base.html').template.source


@tag("integration")
class HamburgerMenuCSSMobileTest(TestCase):

    def setUp(self):
        self.css = _read_css()
        self.nav_links_rule = _extract_mobile_nav_links_block(self.css)
        self.nav_open_rule = _extract_mobile_nav_open_block(self.css)

    def test_mobile_nav_links_has_opaque_background(self):
        self.assertIn('background: var(--nav-bg)', self.nav_links_rule)

    def test_mobile_nav_links_has_box_shadow(self):
        self.assertIn('box-shadow', self.nav_links_rule)

    def test_mobile_nav_links_has_transform_origin(self):
        self.assertIn('transform-origin', self.nav_links_rule)

    def test_mobile_nav_links_has_scale_animation(self):
        self.assertIn('scaleY', self.nav_links_rule)

    def test_mobile_nav_links_has_transition(self):
        self.assertIn('transition', self.nav_links_rule)

    def test_mobile_nav_open_has_scale_open(self):
        self.assertIn('scaleY(1)', self.nav_open_rule)


@tag("integration")
class HamburgerMenuScriptTest(TestCase):

    def setUp(self):
        self.source = _read_base_template()

    def test_template_has_hamburger_menu_script_block(self):
        self.assertIn('<script id="nav-hamburger-menu">', self.source)

    def test_script_targets_hamburger_button(self):
        self.assertIn("getElementById('nav-hamburger-btn')", self.source)

    def test_script_toggles_nav_open(self):
        self.assertIn(".classList.toggle('nav-open')", self.source)

    def test_script_has_close_menu_function(self):
        self.assertIn('closeMenu', self.source)

    def test_script_has_click_outside_handler(self):
        self.assertIn("addEventListener('click'", self.source)

    def test_click_outside_consumes_click(self):
        self.assertIn('e.stopPropagation()', self.source)
        self.assertIn('e.preventDefault()', self.source)

    def test_script_has_scroll_close_handler(self):
        self.assertIn("addEventListener('scroll'", self.source)
