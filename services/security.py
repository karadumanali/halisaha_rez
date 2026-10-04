"""
security.py — Güvenlik servisleri.

Brute-force koruması, reCAPTCHA doğrulama, CSP nonce üretimi,
MIME tespit ve güvenlik header'ları burada yönetilir.
"""

import os
import secrets
import logging

import requests as http_requests
from flask import request, g, render_template
from datetime import datetime, timedelta

from models import db, LoginAttempt
from utils.constants import LOCKOUT_ATTEMPTS, LOCKOUT_MINUTES, ERROR_PAGES
from utils.timeutil import now_tr

logger = logging.getLogger(__name__)


# ── Brute-force koruması ────────────────────────────────────────────

def is_account_locked(username: str, ip: str) -> bool:
    """IP veya kullanıcı adı bazlı hesap kilidi kontrolü."""
    cutoff = now_tr() - timedelta(minutes=LOCKOUT_MINUTES)

    fails_by_username = LoginAttempt.query.filter(
        LoginAttempt.username     == username,
        LoginAttempt.attempted_at  > cutoff,
        LoginAttempt.success      == False  # noqa: E712
    ).count()

    fails_by_ip = LoginAttempt.query.filter(
        LoginAttempt.ip_address   == ip,
        LoginAttempt.attempted_at  > cutoff,
        LoginAttempt.success      == False  # noqa: E712
    ).count()

    return fails_by_username >= LOCKOUT_ATTEMPTS or fails_by_ip >= LOCKOUT_ATTEMPTS


def record_attempt(username: str, ip: str, success: bool):
    """Giriş denemesini kaydet."""
    db.session.add(LoginAttempt(
        ip_address=ip, username=username,
        attempted_at=now_tr(), success=success
    ))
    db.session.commit()


# ── reCAPTCHA v3 ────────────────────────────────────────────────────

def verify_recaptcha(token: str, action: str = 'submit') -> bool:
    """reCAPTCHA v3 token doğrulaması."""
    recaptcha_secret = os.getenv('RECAPTCHA_SECRET_KEY', '')
    min_score = 0.5

    if not recaptcha_secret:
        return True
    if not token:
        return False
    try:
        resp = http_requests.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data={'secret': recaptcha_secret, 'response': token},
            timeout=5
        )
        data = resp.json()
        return (
            data.get('success') is True
            and data.get('score', 0) >= min_score
            and data.get('action', '') == action
        )
    except Exception:
        logger.warning("reCAPTCHA dogrulama istegi basarisiz.")
        return os.getenv('FLASK_ENV') != 'production'


# ── CSP Nonce üretimi ──────────────────────────────────────────────

def generate_csp_nonce():
    """Her request için benzersiz CSP nonce üret."""
    g.csp_nonce = secrets.token_urlsafe(16)


# ── MIME tespiti ────────────────────────────────────────────────────

_MAGIC_BYTES = {
    b'\xff\xd8\xff':       'image/jpeg',
    b'\x89PNG\r\n\x1a\n': 'image/png',
    b'%PDF':               'application/pdf',
}


def detect_mime(file_bytes: bytes) -> str:
    """Dosyanın magic bytes'larından MIME tipini tespit et."""
    for sig, mime in _MAGIC_BYTES.items():
        if file_bytes.startswith(sig):
            return mime
    return ''


# ── Güvenlik header'ları ────────────────────────────────────────────

def apply_security_headers(response):
    """After-request hook: tüm güvenlik header'larını ekle."""
    if response.status_code == 200 and response.content_type and \
       response.content_type.startswith('text/html'):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"]        = "no-cache"
        response.headers["Expires"]       = "0"

    response.headers['X-Frame-Options']        = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection']       = '0'
    response.headers['Referrer-Policy']        = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy']     = 'camera=(), microphone=(), geolocation=()'

    # CORS
    allowed_origin = os.getenv('CORS_ORIGIN', '')
    if allowed_origin:
        response.headers['Access-Control-Allow-Origin'] = allowed_origin
    else:
        response.headers['Access-Control-Allow-Origin'] = 'null'

    # CSP
    nonce = getattr(g, 'csp_nonce', '')
    response.headers['Content-Security-Policy'] = (
        f"default-src 'self'; "
        f"script-src 'self' https://cdn.jsdelivr.net https://www.google.com "
        f"https://www.gstatic.com 'nonce-{nonce}'; "
        f"style-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com "
        f"https://fonts.googleapis.com 'nonce-{nonce}'; "
        f"font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        f"img-src 'self' data:; "
        f"connect-src 'self'; "
        f"frame-src https://www.google.com; "
        f"frame-ancestors 'none'; "
        f"form-action 'self'; "
        f"report-uri /csp-report; "
        f"report-to csp-endpoint"
    )

    from flask import current_app
    if not current_app.debug:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    response.headers['Report-To'] = (
        '{"group":"csp-endpoint","max_age":10886400,'
        '"endpoints":[{"url":"/csp-report"}]}'
    )

    response.headers.pop('Server', None)
    return response


# ── Hata sayfaları ──────────────────────────────────────────────────

def _render_error(code, e):
    """Özel hata sayfası render fonksiyonu."""
    if code == 500:
        logger.error(f"500 hatasi: {e}")
    info = ERROR_PAGES.get(code, {
        'title':      'Hata',
        'message':    'Beklenmeyen bir hata olustu.',
        'icon':       'exclamation-circle',
        'icon_color': 'var(--gray-400)',
    })
    return render_template('error.html', code=code, **info), code


def register_error_handlers(app):
    """Tüm hata handler'larını app'e kaydet."""

    @app.errorhandler(404)
    def page_not_found(e):
        return _render_error(404, e)

    @app.errorhandler(500)
    def internal_server_error(e):
        return _render_error(500, e)

    @app.errorhandler(429)
    def too_many_requests(e):
        return _render_error(429, e)

    @app.errorhandler(403)
    def forbidden(e):
        return _render_error(403, e)
