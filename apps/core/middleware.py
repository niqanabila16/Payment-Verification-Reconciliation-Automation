"""Extra security headers."""

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "worker-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


class SecurityHeadersMiddleware:
    """
    - Content-Security-Policy: only same-origin scripts/styles (templates contain no inline JS/CSS).
    - Cache-Control: no-store on pages for signed-in users, so financial data is not kept in
      shared-computer browser caches (the offline Teller form is cached explicitly by the service worker).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.user.is_authenticated and not request.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response
