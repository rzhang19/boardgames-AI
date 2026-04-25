from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.utils import timezone

import zoneinfo as _zoneinfo

EXEMPT_PATHS = ('/beta-access/', '/static/', '/admin/')


class MustChangePasswordMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (request.user.is_authenticated
                and request.user.must_change_password
                and not request.path.startswith('/change-password/')
                and not request.path.startswith('/logout/')
                and not request.path.startswith(EXEMPT_PATHS)):
            return redirect('forced_password_change')
        return self.get_response(request)


class BetaAccessMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        beta_hash = getattr(settings, 'BETA_ACCESS_CODE_HASH', '')
        if not beta_hash:
            return self.get_response(request)

        if request.path.startswith(EXEMPT_PATHS):
            return self.get_response(request)

        cookie = request.COOKIES.get('beta_access')
        if cookie:
            try:
                signer = TimestampSigner()
                signer.unsign(cookie, max_age=90 * 86400)
                return self.get_response(request)
            except (BadSignature, SignatureExpired):
                pass

        return redirect('/beta-access/')


class TimezoneMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            tz_name = getattr(request.user, 'timezone', 'UTC')
            try:
                tz = _zoneinfo.ZoneInfo(tz_name)
                timezone.activate(tz)
            except Exception:
                timezone.activate(_zoneinfo.ZoneInfo('UTC'))
        else:
            timezone.deactivate()
        return self.get_response(request)


class ViewOnlyMiddleware:

    EXEMPT_PATHS = ('/logout/', '/login/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            request.user.is_authenticated
            and getattr(request.user, 'is_view_only', False)
            and request.method == 'POST'
            and not request.path.startswith(self.EXEMPT_PATHS)
        ):
            return HttpResponseForbidden(
                'This action is not available in view-only mode.'
            )
        return self.get_response(request)
