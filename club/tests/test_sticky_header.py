import os

from django.test import TestCase, tag


def _read_css():
    css_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        '..', 'static', 'css', 'style.css'
    )
    css_path = os.path.normpath(css_path)
    with open(css_path, 'r') as f:
        return f.read()


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


def _read_base_template():
    from django.template.loader import get_template
    return get_template('base.html').template.source


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
