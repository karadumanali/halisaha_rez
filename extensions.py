"""
extensions.py — Flask extension'ları.

Circular import sorununu çözmek için tüm extension nesneleri
burada oluşturulur, init_app() ile app'e bağlanır.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ── Extension nesneleri (henüz app'e bağlı değil) ──────────────────

db = SQLAlchemy()

csrf = CSRFProtect()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["500 per day", "100 per hour"],
)

login_manager = LoginManager()
login_manager.login_view             = 'auth.admin_login'
login_manager.login_message          = 'Bu sayfaya erisim icin giris yapmaniz gerekiyor.'
login_manager.login_message_category = 'warning'
