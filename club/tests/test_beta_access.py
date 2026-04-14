from django.contrib.auth.hashers import make_password
from django.core.signing import TimestampSigner
from django.test import TestCase, override_settings
from django.urls import reverse


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
