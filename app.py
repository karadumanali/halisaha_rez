"""
app.py — Application Factory.

create_app() tüm bileşenleri (extensions, blueprints, hooks, scheduler)
bir araya getirir. Modüler mimari sayesinde her parça bağımsız test edilebilir.
"""

import os
import logging

from flask import Flask, session
from werkzeug.middleware.proxy_fix import ProxyFix

from config import get_config
from extensions import db, migrate, csrf, limiter, login_manager
from models import Admin


logger = logging.getLogger(__name__)


def create_app(config_class=None):
    """
    Flask Application Factory.

    Args:
        config_class: Opsiyonel config sınıfı. None ise ortam değişkenine göre seçilir.
    """
    app = Flask(__name__)

    # ── 1. Konfigürasyon ──────────────────────────────────────────
    if config_class is None:
        config_class = get_config()
    app.config.from_object(config_class)

    # Config doğrulaması
    config_class.validate()

    # ProxyFix (reverse proxy arkasında gerçek IP)
    proxy_count = int(os.getenv('PROXY_COUNT', '0'))
    if proxy_count > 0:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=proxy_count,
            x_proto=proxy_count,
            x_host=proxy_count
        )

    # ── 2. Extension'ları başlat ──────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)

    # ── 3. User loader ────────────────────────────────────────────
    @login_manager.user_loader
    def load_user(user_id):
        """Session token doğrulaması ile kullanıcı yükle."""
        admin = db.session.get(Admin, int(user_id))
        if admin is None:
            return None
        stored_token  = session.get('session_token')
        if not admin.session_token or admin.session_token != stored_token:
            return None
        return admin

    # ── 4. Blueprint'leri kaydet ──────────────────────────────────
    from routes import register_blueprints
    register_blueprints(app)

    # ── 5. Before/After request hook'ları ─────────────────────────
    from services.security import generate_csp_nonce, apply_security_headers

    @app.before_request
    def _before_request():
        generate_csp_nonce()

    @app.after_request
    def _after_request(response):
        return apply_security_headers(response)

    # ── 6. Template context processors ────────────────────────────
    from flask import g

    @app.context_processor
    def inject_csp_nonce():
        """Tüm template'lere csp_nonce değişkenini enjekte et."""
        return {'csp_nonce': getattr(g, 'csp_nonce', '')}

    # ── 7. Hata sayfalarını kaydet ────────────────────────────────
    from services.security import register_error_handlers
    register_error_handlers(app)

    # ── 8. Upload klasörlerini oluştur ────────────────────────────
    for folder_key in ('UPLOAD_FOLDER', 'PITCH_IMAGES_FOLDER'):
        folder_path = app.config.get(folder_key)
        if folder_path:
            os.makedirs(folder_path, exist_ok=True)

    # ── 9. Scheduler'ı başlat ─────────────────────────────────────
    from services.scheduler import init_scheduler
    init_scheduler(app)

    # ── 10. CLI komutları ─────────────────────────────────────────
    # Şema: `flask db upgrade`  |  İlk admin: `flask create-admin`
    from cli import register_commands
    register_commands(app)

    return app


def check_db_revision(app):
    """
    Veritabanı şeması en son migration'da değilse uyarı ver.

    Şema artık açılışta otomatik oluşturulmaz (create_all kaldırıldı);
    `flask db upgrade` unutulursa hata sayfaları yerine bu net uyarı görülür.
    """
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory

    try:
        with app.app_context():
            config = app.extensions['migrate'].migrate.get_config()
            heads  = set(ScriptDirectory.from_config(config).get_heads())
            with db.engine.connect() as conn:
                current = set(MigrationContext.configure(conn).get_current_heads())
    except Exception as e:
        logger.warning(f"Veritabani surum kontrolu yapilamadi: {e}")
        return

    if current != heads:
        logger.warning(
            "VERITABANI SEMASI GUNCEL DEGIL (mevcut: %s, beklenen: %s). "
            "Uygulamayi baslatmadan once `flask db upgrade` calistirin.",
            ', '.join(sorted(current)) or 'yok', ', '.join(sorted(heads)),
        )
