"""
extensions.py — Flask extension'ları.

Circular import sorununu çözmek için tüm extension nesneleri
burada oluşturulur, init_app() ile app'e bağlanır.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sqlalchemy import MetaData

# ── Extension nesneleri (henüz app'e bağlı değil) ──────────────────

# Constraint isimlendirme kuralı: SQLite ve PostgreSQL'de aynı isimler
# oluşur, böylece migration'lar constraint'leri isimle bulup değiştirebilir.
naming_convention = {
    'ix': 'ix_%(column_0_label)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    'pk': 'pk_%(table_name)s',
}

db = SQLAlchemy(metadata=MetaData(naming_convention=naming_convention))

# render_as_batch: SQLite ALTER TABLE kısıtlamalarını aşmak için (app.py'de verilir)
migrate = Migrate()

csrf = CSRFProtect()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["500 per day", "100 per hour"],
)

login_manager = LoginManager()
login_manager.login_view             = 'auth.admin_login'
login_manager.login_message          = 'Bu sayfaya erisim icin giris yapmaniz gerekiyor.'
login_manager.login_message_category = 'warning'
