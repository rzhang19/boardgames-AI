from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.shortcuts import redirect

EXEMPT_PATHS = ('/beta-access/', '/static/', '/admin/')


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
