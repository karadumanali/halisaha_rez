"""
cli.py — Özel Flask CLI komutları.

Kullanım:
    flask create-admin      -> 'yonetici' hesabı yoksa rastgele şifreyle oluşturur

Veritabanı şeması için Flask-Migrate komutları kullanılır:
    flask db upgrade        -> Bekleyen migration'ları uygular
    flask db migrate -m ".."-> Model değişikliğinden yeni migration üretir
"""

import secrets
import string
import logging

import click

from extensions import db
from models import Admin
from utils.helpers import ph_hash


logger = logging.getLogger(__name__)

ADMIN_USERNAME = 'yonetici'


@click.command('create-admin')
def create_admin_command():
    """İlk yönetici hesabını oluştur (zaten varsa dokunmaz)."""
    if Admin.query.filter_by(username=ADMIN_USERNAME).first():
        click.echo(f"'{ADMIN_USERNAME}' hesabi zaten mevcut — atlandi.")
        return

    # Güvenli rastgele şifre — sabit şifre ASLA kullanılmaz
    alfabe    = string.ascii_letters + string.digits + "!@#$%^&*"
    ilk_sifre = ''.join(secrets.choice(alfabe) for _ in range(20))

    db.session.add(Admin(username=ADMIN_USERNAME, password_hash=ph_hash(ilk_sifre)))
    db.session.commit()

    # Şifre yalnızca terminale yazılır, log'a ASLA yazılmaz
    click.echo("=" * 60)
    click.echo("  YENI ADMIN HESABI OLUSTURULDU")
    click.echo(f"  Kullanici adi : {ADMIN_USERNAME}")
    click.echo(f"  Sifre         : {ilk_sifre}")
    click.echo("  !! Bu sifreyi simdi not alin, bir daha gosterilmez !!")
    click.echo("  !! Giris yapip sifrenizi hemen degistirin !!")
    click.echo("=" * 60)
    logger.info("Yeni admin hesabi olusturuldu (sifre konsola yazildi).")


def register_commands(app):
    """CLI komutlarını app'e kaydet."""
    app.cli.add_command(create_admin_command)
