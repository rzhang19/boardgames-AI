from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class EmailOrUsernameBackend(ModelBackend):

    def authenticate(self, request, username=None, password=None, **kwargs):
        user = None
        try:
            user = User.objects.get(email__iexact=username)
        except User.DoesNotExist:
            try:
                user = User.objects.get(username__iexact=username)
            except User.DoesNotExist:
                pass

        if user is None:
            User().set_password(password)
            return None

        if not user.check_password(password):
            return None

        if getattr(settings, 'REQUIRE_EMAIL_VERIFICATION', False) and user.email and not user.email_verified:
            return None

        return user
