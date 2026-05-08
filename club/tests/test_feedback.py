from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings, tag
from django.urls import reverse

User = get_user_model()


@tag("unit")
class FeedbackFormTest(TestCase):

    def test_feedback_type_choices(self):
        from club.forms import FeedbackForm
        form = FeedbackForm()
        choice_values = [c[0] for c in form.fields['feedback_type'].choices]
        self.assertEqual(choice_values, ['bug', 'feature', 'admin', 'community', 'other'])

    def test_message_max_length(self):
        from club.forms import FeedbackForm
        form = FeedbackForm(data={
            'feedback_type': 'bug',
            'email': 'test@example.com',
            'message': 'x' * 1001,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('message', form.errors)

    def test_email_field_required(self):
        from club.forms import FeedbackForm
        form = FeedbackForm(data={
            'feedback_type': 'bug',
            'email': '',
            'message': 'Hello',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_message_field_required(self):
        from club.forms import FeedbackForm
        form = FeedbackForm(data={
            'feedback_type': 'bug',
            'email': 'test@example.com',
            'message': '',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('message', form.errors)

    def test_valid_form(self):
        from club.forms import FeedbackForm
        form = FeedbackForm(data={
            'feedback_type': 'feature',
            'email': 'test@example.com',
            'message': 'I would love a dark mode!',
        })
        self.assertTrue(form.is_valid())

    def test_invalid_email_rejected(self):
        from club.forms import FeedbackForm
        form = FeedbackForm(data={
            'feedback_type': 'bug',
            'email': 'not-an-email',
            'message': 'Hello',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)


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
        response = self.client.post(reverse('feedback'), {
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
        response = self.client.post(reverse('feedback'), {
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
        response = self.client.post(reverse('feedback'), {
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
        response = self.client.post(reverse('feedback'), {
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
        response = self.client.post(reverse('feedback'), {
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


@tag("unit")
class FeedbackConnectionTest(TestCase):

    def test_send_real_emails_false_returns_none(self):
        from club.views import _get_feedback_connection
        with self.settings(SEND_REAL_EMAILS=False):
            self.assertIsNone(_get_feedback_connection())

    def test_send_real_emails_true_returns_smtp_connection(self):
        from django.core.mail.backends.smtp import EmailBackend
        from club.views import _get_feedback_connection
        with self.settings(SEND_REAL_EMAILS=True):
            connection = _get_feedback_connection()
            self.assertIsInstance(connection, EmailBackend)
