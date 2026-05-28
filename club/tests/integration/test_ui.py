import os

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core import mail
from django.core.signing import TimestampSigner
from django.test import TestCase, override_settings, tag
from django.urls import reverse
from django.utils import timezone

from club.models import BoardGame, Event, EventAttendance, Group, GroupMembership, Vote

User = get_user_model()


def _read_css():
    css_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        '..', 'static', 'css', 'style.css'
    )
    css_path = os.path.normpath(css_path)
    with open(css_path, 'r') as f:
        return f.read()


def _read_js():
    js_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        '..', 'static', 'js', 'unsaved-changes.js'
    )
    js_path = os.path.normpath(js_path)
    with open(js_path, 'r') as f:
        return f.read()


def _read_base_template():
    from django.template.loader import get_template
    return get_template('base.html').template.source


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


@tag("integration")
class CSSMobileResponsiveTest(TestCase):

    def test_css_file_contains_mobile_media_query(self):
        css = _read_css()
        self.assertIn('@media (max-width: 600px)', css)

    def test_css_file_contains_hamburger_styles(self):
        css = _read_css()
        self.assertIn('.nav-hamburger', css)
        self.assertIn('.nav-links', css)
        self.assertIn('.nav-open', css)

    def test_css_file_contains_nav_actions_styles(self):
        css = _read_css()
        self.assertIn('.nav-actions', css)

    def test_css_file_contains_card_based_table_styles(self):
        css = _read_css()
        self.assertIn('attr(data-label)', css)
        self.assertIn('thead', css)

    def test_css_file_contains_form_grid_mobile(self):
        css = _read_css()
        self.assertIn('.form-grid', css)
        self.assertIn('grid-template-columns: 1fr', css)


@tag("integration")
class BaseTemplateMobileTest(TestCase):

    def test_base_template_has_viewport_meta_tag(self):
        source = _read_base_template()
        self.assertIn('viewport', source)
        self.assertIn('width=device-width', source)

    def test_base_template_has_hamburger_button(self):
        source = _read_base_template()
        self.assertIn('nav-hamburger', source)

    def test_base_template_has_nav_links_container(self):
        source = _read_base_template()
        self.assertIn('nav-links', source)

    def test_base_template_has_nav_open_toggle(self):
        source = _read_base_template()
        self.assertIn('nav-open', source)

    def test_base_template_has_nav_actions_container(self):
        source = _read_base_template()
        self.assertIn('nav-actions', source)


@tag("integration")
class GameListDataLabelsTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
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
        import datetime as dt
        group = Group.objects.create(name='Test Group')
        GroupMembership.objects.create(user=user, group=group, role='member')
        Event.objects.create(
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


@tag("integration")
class StickyHeaderCSSTest(TestCase):

    def setUp(self):
        self.css = _read_css()
        self.rule = _extract_css_rule(self.css, '.sticky-header')

    def test_css_has_sticky_header_selector(self):
        self.assertIn('.sticky-header', self.css)

    def test_sticky_header_has_position_sticky(self):
        self.assertIn('position: sticky', self.rule)

    def test_sticky_header_has_top_zero(self):
        self.assertIn('top: 0', self.rule)

    def test_sticky_header_has_z_index(self):
        self.assertIn('z-index', self.rule)


@tag("integration")
class StickyHeaderTemplateTest(TestCase):

    def setUp(self):
        self.source = _read_base_template()

    def test_template_has_sticky_header_wrapper(self):
        self.assertIn('<div class="sticky-header">', self.source)

    def test_sticky_header_wraps_nav(self):
        sticky_start = self.source.find('<div class="sticky-header">')
        sticky_end = self.source.find('</div>\n    <main>', sticky_start)
        nav_start = self.source.find('<nav>', sticky_start)
        self.assertGreater(nav_start, sticky_start)
        self.assertLess(nav_start, sticky_end)

    def test_sticky_header_wraps_lockdown_banner(self):
        sticky_start = self.source.find('<div class="sticky-header">')
        sticky_end = self.source.find('</div>\n    <main>', sticky_start)
        banner_start = self.source.find('site-lockdown-banner', sticky_start)
        self.assertGreater(banner_start, sticky_start)
        self.assertLess(banner_start, sticky_end)

    def test_sticky_header_wraps_view_only_banner(self):
        sticky_start = self.source.find('<div class="sticky-header">')
        sticky_end = self.source.find('</div>\n    <main>', sticky_start)
        banner_start = self.source.find('view-only-banner', sticky_start)
        self.assertGreater(banner_start, sticky_start)
        self.assertLess(banner_start, sticky_end)

    def test_main_is_outside_sticky_header(self):
        sticky_start = self.source.find('<div class="sticky-header">')
        sticky_end = self.source.find('</div>\n    <main>', sticky_start)
        main_start = self.source.find('<main>')
        self.assertGreater(main_start, sticky_end)


@tag("integration")
class UserSettingsBannerTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
        )
        self.client.login(username='testuser', password='testpass123')

    def test_settings_page_has_unsaved_changes_banner(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'unsaved-changes-banner')

    def test_banner_contains_unsaved_changes_text(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'You have unsaved changes')

    def test_banner_has_save_button(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'unsaved-save-btn')

    def test_settings_page_includes_unsaved_changes_js(self):
        response = self.client.get(reverse('user_settings'))
        self.assertContains(response, 'unsaved-changes.js')

    def test_settings_page_no_bottom_save_button(self):
        response = self.client.get(reverse('user_settings'))
        content = response.content.decode()
        banner_end = content.find('</div>', content.find('unsaved-changes-banner'))
        after_banner = content[banner_end:]
        self.assertNotIn('>Save Settings<', after_banner)


@tag("integration")
class GroupSettingsBannerTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='admin', password='p')
        cls.group = Group.objects.create(name='Banner Group')
        GroupMembership.objects.create(user=cls.user, group=cls.group, role='admin')

    def setUp(self):
        self.client.login(username='admin', password='p')

    def test_group_settings_has_unsaved_changes_banner(self):
        response = self.client.get(f'/groups/{self.group.slug}/settings/')
        self.assertContains(response, 'unsaved-changes-banner')

    def test_banner_contains_unsaved_changes_text(self):
        response = self.client.get(f'/groups/{self.group.slug}/settings/')
        self.assertContains(response, 'You have unsaved changes')

    def test_banner_has_save_button(self):
        response = self.client.get(f'/groups/{self.group.slug}/settings/')
        self.assertContains(response, 'unsaved-save-btn')

    def test_group_settings_includes_unsaved_changes_js(self):
        response = self.client.get(f'/groups/{self.group.slug}/settings/')
        self.assertContains(response, 'unsaved-changes.js')

    def test_group_settings_no_bottom_save_button(self):
        response = self.client.get(f'/groups/{self.group.slug}/settings/')
        content = response.content.decode()
        banner_end = content.find('</div>', content.find('unsaved-changes-banner'))
        after_banner = content[banner_end:]
        self.assertNotIn('>Save Settings<', after_banner)


@tag("integration")
class PrivateEventSettingsBannerTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='creator', password='p')
        cls.event = Event.objects.create(
            title='Private Event',
            date=timezone.now() + __import__('datetime').timedelta(days=7),
            created_by=cls.user,
            voting_deadline=timezone.now() + __import__('datetime').timedelta(days=6),
        )

    def setUp(self):
        self.client.login(username='creator', password='p')

    def test_private_event_settings_has_unsaved_changes_banner(self):
        response = self.client.get(f'/events/{self.event.pk}/settings/')
        self.assertContains(response, 'unsaved-changes-banner')

    def test_banner_contains_unsaved_changes_text(self):
        response = self.client.get(f'/events/{self.event.pk}/settings/')
        self.assertContains(response, 'You have unsaved changes')

    def test_banner_has_save_button(self):
        response = self.client.get(f'/events/{self.event.pk}/settings/')
        self.assertContains(response, 'unsaved-save-btn')

    def test_private_event_settings_includes_unsaved_changes_js(self):
        response = self.client.get(f'/events/{self.event.pk}/settings/')
        self.assertContains(response, 'unsaved-changes.js')

    def test_private_event_settings_no_bottom_save_button(self):
        response = self.client.get(f'/events/{self.event.pk}/settings/')
        content = response.content.decode()
        banner_end = content.find('</div>', content.find('unsaved-changes-banner'))
        after_banner = content[banner_end:]
        self.assertNotIn('>Save Settings<', after_banner)


@tag("integration")
class UnsavedChangesStaticFilesTest(TestCase):

    def test_js_file_exists(self):
        js = _read_js()
        self.assertTrue(len(js) > 0)

    def test_js_has_form_snapshot_logic(self):
        js = _read_js()
        self.assertIn('snapshot', js)

    def test_js_has_dirty_check_logic(self):
        js = _read_js()
        self.assertIn('isDirty', js)

    def test_js_has_beforeunload_handler(self):
        js = _read_js()
        self.assertIn('beforeunload', js)

    def test_js_has_banner_toggle(self):
        js = _read_js()
        self.assertIn('unsaved-banner', js)
        self.assertIn('classList', js)
        self.assertIn('active', js)

    def test_css_has_banner_styles(self):
        css = _read_css()
        self.assertIn('.unsaved-changes-banner', css)

    def test_css_has_fixed_position(self):
        css = _read_css()
        self.assertIn('position: fixed', css)

    def test_css_banner_has_dark_theme_support(self):
        css = _read_css()
        self.assertIn('[data-applied-theme="dark"] .unsaved-changes-banner', css)


@tag("integration")
@override_settings(BETA_ACCESS_CODE_HASH=make_password('testbeta'))
class BetaAccessGateActiveTest(TestCase):

    def test_redirects_to_beta_access_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/beta-access/')

    def test_redirects_to_beta_access_for_protected_page(self):
        response = self.client.get('/games/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/beta-access/')

    def test_static_path_not_redirected(self):
        response = self.client.get('/static/css/style.css')
        self.assertNotEqual(response.status_code, 302)
        self.assertNotEqual(response.url if hasattr(response, 'url') else '', '/beta-access/')

    def test_admin_path_not_redirected_to_beta(self):
        response = self.client.get('/admin/')
        self.assertNotIn('/beta-access/', response.url if hasattr(response, 'url') else '')

    def test_beta_access_page_renders(self):
        response = self.client.get('/beta-access/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Beta Access')

    def test_correct_code_redirects_to_dashboard_and_sets_cookie(self):
        response = self.client.post('/beta-access/', {'access_code': 'testbeta'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        self.assertIn('beta_access', response.cookies)

    def test_correct_code_sets_cookie_with_90_day_max_age(self):
        response = self.client.post('/beta-access/', {'access_code': 'testbeta'})
        cookie = response.cookies['beta_access']
        self.assertEqual(cookie['max-age'], 90 * 86400)

    def test_wrong_code_shows_error(self):
        response = self.client.post('/beta-access/', {'access_code': 'wrongcode'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invalid access code')

    def test_valid_cookie_passes_through(self):
        signer = TimestampSigner()
        signed = signer.sign('granted')
        self.client.cookies['beta_access'] = signed
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_tampered_cookie_redirects_to_beta(self):
        self.client.cookies['beta_access'] = 'tampered_value'
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/beta-access/')


@tag("integration")
@override_settings(BETA_ACCESS_CODE_HASH='')
class BetaAccessGateInactiveTest(TestCase):

    def test_no_redirect_when_gate_inactive(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_beta_access_page_redirects_when_gate_inactive(self):
        response = self.client.get('/beta-access/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')

    def test_no_redirect_with_old_cookie_when_gate_inactive(self):
        signer = TimestampSigner()
        signed = signer.sign('granted')
        self.client.cookies['beta_access'] = signed
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)


@tag("integration")
class FeedbackPageAccessTest(TestCase):

    def setUp(self):
        self.verified_user = User.objects.create_user(
            username='verified', password='testpass123',
            email='verified@example.com', email_verified=True,
        )
        self.unverified_user = User.objects.create_user(
            username='unverified', password='testpass123',
            email='unverified@example.com', email_verified=False,
        )

    def test_verified_user_can_access_feedback_page(self):
        self.client.login(username='verified', password='testpass123')
        response = self.client.get(reverse('feedback'))
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_user_redirected_to_login(self):
        response = self.client.get(reverse('feedback'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_unverified_user_redirected(self):
        self.client.login(username='unverified', password='testpass123')
        response = self.client.get(reverse('feedback'))
        self.assertEqual(response.status_code, 302)

    def test_unverified_user_gets_error_message(self):
        self.client.login(username='unverified', password='testpass123')
        response = self.client.get(reverse('feedback'), follow=True)
        messages = list(response.context['messages'])
        self.assertTrue(any('verify' in str(m.message).lower() for m in messages))


@tag("integration")
class FeedbackFormPreFillTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
            email='prefill@example.com', email_verified=True,
        )
        self.client.login(username='testuser', password='testpass123')

    @override_settings(FEEDBACK_TARGET_EMAIL='admin@example.com')
    def test_email_field_prefilled_with_user_email(self):
        response = self.client.get(reverse('feedback'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'prefill@example.com')


@tag("integration")
class FeedbackSubmissionTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser', password='testpass123',
            email='test@example.com', email_verified=True,
        )
        self.client.login(username='testuser', password='testpass123')

    @override_settings(
        FEEDBACK_TARGET_EMAIL='admin@example.com',
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_successful_submission_sends_email(self):
        self.client.post(reverse('feedback'), {
            'feedback_type': 'bug',
            'email': 'test@example.com',
            'message': 'Something is broken.',
        })
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['admin@example.com'])

    @override_settings(
        FEEDBACK_TARGET_EMAIL='admin@example.com',
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_email_subject_includes_type_and_username(self):
        self.client.post(reverse('feedback'), {
            'feedback_type': 'bug',
            'email': 'test@example.com',
            'message': 'Something is broken.',
        })
        subject = mail.outbox[0].subject
        self.assertIn('Bug Report', subject)
        self.assertIn('testuser', subject)

    @override_settings(
        FEEDBACK_TARGET_EMAIL='admin@example.com',
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_email_body_contains_message(self):
        self.client.post(reverse('feedback'), {
            'feedback_type': 'feature',
            'email': 'test@example.com',
            'message': 'I want dark mode!',
        })
        body = mail.outbox[0].body
        self.assertIn('I want dark mode!', body)

    @override_settings(
        FEEDBACK_TARGET_EMAIL='admin@example.com',
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_email_body_contains_custom_email(self):
        self.client.post(reverse('feedback'), {
            'feedback_type': 'bug',
            'email': 'custom@example.com',
            'message': 'Hello',
        })
        body = mail.outbox[0].body
        self.assertIn('custom@example.com', body)

    @override_settings(
        FEEDBACK_TARGET_EMAIL='admin@example.com',
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_successful_submission_shows_success_message(self):
        response = self.client.post(reverse('feedback'), {
            'feedback_type': 'bug',
            'email': 'test@example.com',
            'message': 'Something is broken.',
        }, follow=True)
        messages = list(response.context['messages'])
        self.assertTrue(any('Thank you' in str(m.message) for m in messages))

    @override_settings(
        FEEDBACK_TARGET_EMAIL='admin@example.com',
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_submission_does_not_change_account_email(self):
        self.client.post(reverse('feedback'), {
            'feedback_type': 'bug',
            'email': 'different@example.com',
            'message': 'Hello',
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'test@example.com')

    def test_invalid_submission_does_not_send_email(self):
        self.client.post(reverse('feedback'), {
            'feedback_type': 'bug',
            'email': '',
            'message': 'Hello',
        })
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(
        FEEDBACK_TARGET_EMAIL='',
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_submission_without_target_email_shows_error(self):
        response = self.client.post(reverse('feedback'), {
            'feedback_type': 'bug',
            'email': 'test@example.com',
            'message': 'Hello',
        })
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(response.status_code, 200)

    @override_settings(
        FEEDBACK_TARGET_EMAIL='',
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    )
    def test_page_without_target_email_shows_unavailable(self):
        response = self.client.get(reverse('feedback'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'unavailable')


@tag("integration")
class FeedbackNavButtonTest(TestCase):

    def test_feedback_button_visible_for_verified_user(self):
        User.objects.create_user(
            username='verified', password='testpass123',
            email='v@example.com', email_verified=True,
        )
        self.client.login(username='verified', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('feedback'))

    def test_feedback_button_hidden_for_unverified_user(self):
        User.objects.create_user(
            username='unverified', password='testpass123',
            email='u@example.com', email_verified=False,
        )
        self.client.login(username='unverified', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, reverse('feedback'))

    def test_feedback_button_hidden_for_anonymous(self):
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, reverse('feedback'))


def _read_cookie_js():
    js_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        '..', 'static', 'js', 'cookie-consent.js'
    )
    js_path = os.path.normpath(js_path)
    with open(js_path, 'r') as f:
        return f.read()


@tag("integration")
class CookieBannerFunctionalTest(TestCase):

    def test_cookie_banner_present_in_base_template(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'cookie-banner')

    def test_cookie_consent_js_included_in_base_template(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'cookie-consent.js')

    def test_cookie_banner_css_exists(self):
        css = _read_css()
        self.assertIn('.cookie-banner', css)


@tag("integration")
class CookieBannerSecurityTest(TestCase):

    def test_banner_has_no_dismiss_only_button(self):
        response = self.client.get(reverse('dashboard'))
        content = response.content.decode()
        banner_start = content.find('id="cookie-banner"')
        if banner_start == -1:
            self.fail('cookie-banner element not found in rendered page')
        banner_end = content.find('</div>', content.find('</div>', banner_start) + 1)
        banner_html = content[banner_start:banner_end]
        self.assertNotIn('cookie-dismiss', banner_html)

    def test_banner_css_has_fixed_position(self):
        css = _read_css()
        rule = _extract_css_rule(css, '.cookie-banner')
        self.assertIn('position: fixed', rule)

    def test_cookie_js_sets_secure_flag_conditionally(self):
        js = _read_cookie_js()
        self.assertIn("window.location.protocol === 'https:'", js)
        self.assertIn('Secure', js)

    def test_cookie_js_sets_samesite_lax(self):
        js = _read_cookie_js()
        self.assertIn('SameSite=Lax', js)

    def test_cookie_js_validates_consent_values(self):
        js = _read_cookie_js()
        self.assertIn('essential', js)
        self.assertIn('all', js)

    def test_cookie_js_no_unsafe_dom_operations(self):
        js = _read_cookie_js()
        self.assertNotIn('innerHTML', js)
        self.assertNotIn('eval(', js)
        self.assertNotIn('document.write', js)
