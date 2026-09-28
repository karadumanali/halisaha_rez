"""
config.py — Uygulama konfigürasyonu.

Tüm ortam değişkenleri ve Flask ayarları burada merkezi olarak yönetilir.
Development / Production ayrımı sınıf miras yapısıyla sağlanır.
"""

import os
import logging
import logging.handlers
from datetime import timedelta

base_dir = os.path.dirname(os.path.abspath(__file__))


class BaseConfig:
    """Tüm ortamlarda geçerli olan temel ayarlar."""

    BASE_DIR = base_dir

    # ── Secret Key (zorunlu) ────────────────────────────────────────
    SECRET_KEY = os.getenv('SECRET_KEY')

    # ── Veritabanı ──────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI        = os.getenv('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_POOL_SIZE           = 10
    SQLALCHEMY_MAX_OVERFLOW        = 20
    SQLALCHEMY_POOL_TIMEOUT        = 30
    SQLALCHEMY_POOL_PRE_PING       = True
    SQLALCHEMY_POOL_RECYCLE        = 280
    SQLALCHEMY_ENGINE_OPTIONS      = {
        'pool_pre_ping': True,
        'pool_recycle': 280,
    }

    # ── Oturum ──────────────────────────────────────────────────────
    SESSION_PERMANENT          = True
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_COOKIE_HTTPONLY    = True
    SESSION_COOKIE_SAMESITE    = 'Lax'
    SESSION_COOKIE_NAME        = 'sks_sid'

    # ── Upload ──────────────────────────────────────────────────────
    MAX_CONTENT_LENGTH  = 5 * 1024 * 1024  # 5 MB
    ALLOWED_EXTENSIONS  = {'pdf', 'png', 'jpg', 'jpeg'}

    _default_upload     = os.path.join(base_dir, 'uploads', 'receipts')
    UPLOAD_FOLDER       = os.getenv('UPLOAD_PATH', '').strip() or _default_upload
    PITCH_IMAGES_FOLDER = os.path.join(base_dir, 'static', 'uploads', 'pitches')
    LOGO_FOLDER         = os.path.join(base_dir, 'static', 'uploads')

    # ── Rate Limiter ────────────────────────────────────────────────
    REDIS_URL      = os.getenv('REDIS_URL', 'memory://')
    RATELIMIT_DEFAULT = ["500 per day", "100 per hour"]

    # ── Proxy ───────────────────────────────────────────────────────
    PROXY_COUNT = int(os.getenv('PROXY_COUNT', '0'))

    # ── Mail ────────────────────────────────────────────────────────
    MAIL_USERNAME  = os.getenv('MAIL_USERNAME')
    MAIL_PASSWORD  = os.getenv('MAIL_PASSWORD')
    ADMIN_EMAIL    = os.getenv('ADMIN_EMAIL')

    # ── reCAPTCHA ───────────────────────────────────────────────────
    RECAPTCHA_SECRET_KEY = os.getenv('RECAPTCHA_SECRET_KEY', '')
    RECAPTCHA_SITE_KEY   = os.getenv('RECAPTCHA_SITE_KEY', '')
    RECAPTCHA_MIN_SCORE  = 0.5

    # ── CORS ────────────────────────────────────────────────────────
    CORS_ORIGIN = os.getenv('CORS_ORIGIN', '')

    # ── IBAN ────────────────────────────────────────────────────────
    SITE_IBAN = os.getenv('SITE_IBAN', '')

    @staticmethod
    def validate():
        """Başlangıçta kritik ayarları doğrula."""
        secret = os.getenv('SECRET_KEY')
        if not secret:
            raise RuntimeError(
                "SECRET_KEY ortam degiskeni ZORUNLUDUR! "
                ".env dosyanizi kontrol edin. "
                "Uretmek icin: python3 -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if len(secret) < 32:
            raise RuntimeError(
                f"SECRET_KEY en az 32 karakter olmalidir! "
                f"Mevcut uzunluk: {len(secret)}. "
                "Uretmek icin: python3 -c \"import secrets; print(secrets.token_hex(32))\""
            )


class DevelopmentConfig(BaseConfig):
    """Geliştirme ortamı ayarları."""
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    """Production ortamı ayarları."""
    DEBUG   = False
    TESTING = False
    SESSION_COOKIE_SECURE = True

    @staticmethod
    def validate():
        BaseConfig.validate()
        # Production'da reCAPTCHA zorunlu
        if not os.getenv('RECAPTCHA_SECRET_KEY'):
            raise RuntimeError(
                "RECAPTCHA_SECRET_KEY prodüksiyonda zorunludur. "
                ".env dosyasına RECAPTCHA_SECRET_KEY ve RECAPTCHA_SITE_KEY ekleyin."
            )

    @staticmethod
    def init_app(app):
        """Production-specific logging setup."""
        log_dir = os.path.join(BaseConfig.BASE_DIR, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'app.log'),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.WARNING)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        ))
        app.logger.addHandler(file_handler)
        logging.getLogger().addHandler(file_handler)


# ── Ortam seçici ────────────────────────────────────────────────────

config_map = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
}


def get_config():
    """FLASK_ENV ortam değişkenine göre uygun config sınıfını döndürür."""
    env = os.getenv('FLASK_ENV', 'development').lower()
    return config_map.get(env, DevelopmentConfig)
