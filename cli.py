"""
cli.py — Özel Flask CLI komutları (yönetici hesapları).

Kullanım:
    flask create-admin [KULLANICI_ADI]       -> Yeni admin hesabı (varsayılan: yonetici),
                                               rastgele şifreyle oluşturur
    flask rename-admin ESKI_AD YENI_AD       -> Admin kullanıcı adını değiştirir (şifre aynı kalır)
    flask list-admins                        -> Tüm admin hesaplarını listeler
    flask reset-admin-password KULLANICI_ADI -> Şifresini unutan admine yeni rastgele şifre verir

Örnek (3 ayrı admin):
    flask rename-admin yonetici yonetici1
    flask create-admin yonetici2
    flask create-admin yonetici3

Veritabanı şeması için Flask-Migrate komutları kullanılır:
    flask db upgrade        -> Bekleyen migration'ları uygular
    flask db migrate -m ".."-> Model değişikliğinden yeni migration üretir
"""

import re
import secrets
import string
import logging

import click
from flask.cli import with_appcontext

from extensions import db
from models import Admin
from utils.helpers import ph_hash, validate_password


logger = logging.getLogger(__name__)

ADMIN_USERNAME = 'yonetici'
_USERNAME_RE   = re.compile(r'^[A-Za-z0-9_.\-]{3,50}$')


def _validate_username(username):
    if not _USERNAME_RE.match(username):
        raise click.BadParameter(
            'Kullanici adi 3-50 karakter olmali; sadece harf (Turkce karakter haric), '
            'rakam, nokta, alt cizgi ve tire icerebilir.'
        )


def _generate_password(length=20):
    """Şifre politikasına (validate_password) uyan güvenli rastgele şifre üret."""
    alfabe = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        sifre = ''.join(secrets.choice(alfabe) for _ in range(length))
        if not validate_password(sifre):
            return sifre


def _print_credentials(baslik, username, sifre):
    # Şifre yalnızca terminale yazılır, log'a ASLA yazılmaz
    click.echo("=" * 60)
    click.echo(f"  {baslik}")
    click.echo(f"  Kullanici adi : {username}")
    click.echo(f"  Sifre         : {sifre}")
    click.echo("  !! Bu sifreyi simdi not alin, bir daha gosterilmez !!")
    click.echo("  !! Giris yapip sifrenizi hemen degistirin !!")
    click.echo("=" * 60)


@click.command('create-admin')
@with_appcontext
@click.argument('username', required=False, default=ADMIN_USERNAME)
def create_admin_command(username):
    """Yeni yönetici hesabı oluştur (aynı adla hesap varsa dokunmaz)."""
    username = username.strip()
    _validate_username(username)
    if Admin.query.filter_by(username=username).first():
        click.echo(f"'{username}' hesabi zaten mevcut — atlandi.")
        return

    # Güvenli rastgele şifre — sabit şifre ASLA kullanılmaz
    ilk_sifre = _generate_password()
    db.session.add(Admin(username=username, password_hash=ph_hash(ilk_sifre)))
    db.session.commit()

    _print_credentials("YENI ADMIN HESABI OLUSTURULDU", username, ilk_sifre)
    logger.info("Yeni admin hesabi olusturuldu: %s (sifre konsola yazildi).", username)


@click.command('rename-admin')
@with_appcontext
@click.argument('old_username')
@click.argument('new_username')
def rename_admin_command(old_username, new_username):
    """Admin kullanıcı adını değiştir; şifre aynı kalır."""
    new_username = new_username.strip()
    _validate_username(new_username)
    admin = Admin.query.filter_by(username=old_username).first()
    if not admin:
        raise click.ClickException(f"'{old_username}' adinda bir admin bulunamadi.")
    if Admin.query.filter_by(username=new_username).first():
        raise click.ClickException(f"'{new_username}' adinda bir admin zaten var.")

    admin.username = new_username
    db.session.commit()
    click.echo(f"'{old_username}' -> '{new_username}' olarak degistirildi. Sifre ayni kaldi.")
    click.echo("Not: Eski denetim kayitlari eski kullanici adiyla gorunmeye devam eder.")
    logger.info("Admin kullanici adi degistirildi: %s -> %s", old_username, new_username)


@click.command('list-admins')
@with_appcontext
def list_admins_command():
    """Tüm admin hesaplarını listele."""
    admins = Admin.query.order_by(Admin.id).all()
    if not admins:
        click.echo("Hic admin hesabi yok. Olusturmak icin: flask create-admin KULLANICI_ADI")
        return
    for a in admins:
        click.echo(f"  #{a.id}  {a.username}")


@click.command('reset-admin-password')
@with_appcontext
@click.argument('username')
def reset_admin_password_command(username):
    """Admin şifresini rastgele yeni şifreyle sıfırla ve açık oturumlarını kapat."""
    admin = Admin.query.filter_by(username=username).first()
    if not admin:
        raise click.ClickException(f"'{username}' adinda bir admin bulunamadi.")

    yeni_sifre          = _generate_password()
    admin.password_hash = ph_hash(yeni_sifre)
    admin.session_token = None   # açık oturum varsa sonlandır
    db.session.commit()

    _print_credentials("ADMIN SIFRESI SIFIRLANDI", username, yeni_sifre)
    logger.info("Admin sifresi sifirlandi: %s (sifre konsola yazildi).", username)


def register_commands(app):
    """CLI komutlarını app'e kaydet."""
    app.cli.add_command(create_admin_command)
    app.cli.add_command(rename_admin_command)
    app.cli.add_command(list_admins_command)
    app.cli.add_command(reset_admin_password_command)
