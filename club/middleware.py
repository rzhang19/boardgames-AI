from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core.cache import caches
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.utils import timezone

import zoneinfo as _zoneinfo

EXEMPT_PATHS = ('/beta-access/', '/static/', '/admin/')


class SiteLockdownMiddleware:

    EXEMPT_PATHS = ('/login/', '/logout/', '/admin/', '/static/')
    LOCKDOWN_BLOCKED_GET_PATHS = ('/register/',)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from club.models import SiteSettings
        site_settings = SiteSettings.load()

        if not site_settings.site_lockdown_active:
            return self.get_response(request)

        if request.user.is_authenticated and request.user.is_superuser:
            return self.get_response(request)

        if (
            request.user.is_authenticated
            and request.user.is_site_admin
            and site_settings.site_lockdown_allow_site_admins
        ):
            return self.get_response(request)

        if request.path.startswith(self.EXEMPT_PATHS):
            return self.get_response(request)

        for blocked_path in self.LOCKDOWN_BLOCKED_GET_PATHS:
            if request.path.startswith(blocked_path):
                return redirect('/login/')

        if request.method == 'POST':
            return HttpResponseForbidden(
                'This action is not available during site lockdown.'
            )

        return self.get_response(request)


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


RATE_LIMIT_CONFIG = {
    '/login/': {'limit': 5, 'window': 60},
    '/register/': {'limit': 3, 'window': 3600},
    '/password_reset/': {'limit': 5, 'window': 60},
    '/beta-access/': {'limit': 5, 'window': 60},
}


class RateLimitMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method != 'POST':
            return self.get_response(request)

        if getattr(settings, 'RATE_LIMIT_ENABLED', True) is False:
            return self.get_response(request)

        config = None
        for path, cfg in RATE_LIMIT_CONFIG.items():
            if request.path == path:
                config = cfg
                break

        if config is None:
            return self.get_response(request)

        ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
        cache_key = f'rl:{request.path}:{ip}'

        rl_cache = caches['rate_limit']
        count = rl_cache.get(cache_key, 0)
        if count >= config['limit']:
            retry_after = config['window']
            response = render(request, '429.html', {
                'retry_after': retry_after,
            }, status=429)
            response['Retry-After'] = str(retry_after)
            return response

        rl_cache.set(cache_key, count + 1, config['window'])

        return self.get_response(request)
