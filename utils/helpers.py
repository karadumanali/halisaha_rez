"""
helpers.py — Genel yardımcı fonksiyonlar.

Şifre doğrulama, hash fonksiyonları, audit logging,
IP tespiti ve güvenli yönlendirme burada tanımlanır.
"""

import re
import logging
from urllib.parse import urlparse

from flask import request, redirect
from flask_login import current_user
from werkzeug.security import check_password_hash
from passlib.hash import argon2 as _argon2

from models import db, AuditLog

logger = logging.getLogger(__name__)


# ── Argon2id hash yardımcıları ──────────────────────────────────────

def ph_hash(password: str) -> str:
    """Şifreyi Argon2id ile hashle."""
    return _argon2.using(type="ID").hash(password)


def ph_verify(password: str, stored_hash: str) -> bool:
    """Şifreyi doğrula. Eski hash formatlarını da destekler."""
    if stored_hash.startswith("$argon2"):
        return _argon2.verify(password, stored_hash)
    return check_password_hash(stored_hash, password)


def ph_needs_upgrade(stored_hash: str) -> bool:
    """Hash'in Argon2id'e yükseltilmesi gerekip gerekmediğini kontrol et."""
    return not stored_hash.startswith("$argon2")


# ── Dummy hash (timing attack önlemi) ──────────────────────────────

DUMMY_HASH = ph_hash("__dummy_never_matches__")


# ── Şifre politikası ───────────────────────────────────────────────

def validate_password(password: str) -> list:
    """Şifre politikasını uygula. Hata listesi döndürür (boş = geçerli)."""
    errors = []
    if len(password) < 10:
        errors.append('En az 10 karakter olmalidir.')
    if not re.search(r'[A-Z]', password):
        errors.append('En az 1 buyuk harf (A-Z) icermelidir.')
    if not re.search(r'[a-z]', password):
        errors.append('En az 1 kucuk harf (a-z) icermelidir.')
    if not re.search(r'\d', password):
        errors.append('En az 1 rakam (0-9) icermelidir.')
    if not re.search(r'[!@#$%^&*()\-_=+\[\]{};:,./<>?\\|`~]', password):
        errors.append('En az 1 ozel karakter (!@#$%^&* vb.) icermelidir.')
    return errors


# ── Denetim kaydı (audit log) ──────────────────────────────────────

def audit(action: str, detail: str = ''):
    """Yönetici işlemlerini denetim tablosuna kaydet."""
    # Log injection önlemi
    action = re.sub(r'[\r\n\t]', ' ', action)[:100]
    detail = re.sub(r'[\r\n\t]', ' ', detail)[:500] if detail else ''
    try:
        db.session.add(AuditLog(
            admin      = current_user.username if current_user.is_authenticated else 'sistem',
            ip_address = get_real_ip(),
            action     = action,
            detail     = detail
        ))
        db.session.commit()
    except Exception as e:
        logger.warning(f"Audit log yazilamadi: {e}")


# ── IP tespiti ──────────────────────────────────────────────────────

def get_real_ip() -> str:
    """
    Gerçek IP adresini döndürür.
    ProxyFix aktifse request.remote_addr zaten proxy tarafından ayarlanır.
    Elle X-Forwarded-For okumuyoruz — spoofing riski var.
    """
    return request.remote_addr or ''


# ── Güvenli yönlendirme ────────────────────────────────────────────

def safe_redirect(next_url, fallback):
    """Open redirect saldırısını önleyen güvenli yönlendirme."""
    if next_url:
        parsed = urlparse(next_url)
        if not parsed.netloc and not parsed.scheme and next_url.startswith('/'):
            return redirect(next_url)
    return redirect(fallback)
