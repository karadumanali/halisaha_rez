"""
routes/ — Blueprint kayıt paketi.

Tüm Blueprint'ler burada toplanır ve register_blueprints() ile
application factory'ye tek seferde kayıt edilir.
"""

from routes.public import public_bp
from routes.auth import auth_bp
from routes.admin import admin_bp


def register_blueprints(app):
    """Tüm Blueprint'leri Flask uygulamasına kaydet."""
    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
