"""
routes/auth.py — Kimlik doğrulama (authentication) rotaları.

admin_login     : Giriş sayfası (GET + POST)
logout          : Güvenli çıkış
change_password : Şifre değiştirme
"""

import os
import secrets
import logging

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session
)
from flask_login import login_user, logout_user, login_required, current_user
from flask_limiter.util import get_remote_address

from extensions import db, limiter
from models import Admin, AuditLog
from utils.helpers import (
    ph_hash, ph_verify, ph_needs_upgrade, DUMMY_HASH,
    validate_password, audit, safe_redirect
)
from services.security import is_account_locked, record_attempt, verify_recaptcha

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


# ── Giriş ──────────────────────────────────────────────────────────

def _login_rate_key():
    """IP + kullanıcı adı: aynı ağdan (ör. üniversite ağı) giren farklı
    adminler birbirinin giriş limitini tüketmez."""
    username = (request.form.get('username') or '').strip().lower()[:50]
    return f'{get_remote_address()}|{username}'


# Limitler yalnızca giriş DENEMELERİNE (POST) uygulanır; giriş sayfasını
# açmak (GET) bu limitleri tüketmez. Eskiden sayfayı 4. kez açan admin 429 alıyordu.
@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute; 20 per hour; 50 per day",
               key_func=_login_rate_key, methods=['POST'])   # hesap + IP başına
@limiter.limit("20 per minute; 100 per hour",
               methods=['POST'])                             # IP başına genel tavan
@limiter.limit("60 per minute", methods=['GET'])             # sayfa açma (cömert)
def admin_login():
    """Admin giriş sayfası ve işlemi."""
    recaptcha_site_key = os.getenv('RECAPTCHA_SITE_KEY', '')

    if current_user.is_authenticated:
        return redirect(url_for('admin.admin_dashboard'))

    if request.method == 'POST':
        if not verify_recaptcha(request.form.get('g-recaptcha-response', ''), action='login'):
            flash('Bot dogrulamasi basarisiz. Lutfen tekrar deneyin.', 'danger')
            return render_template('login.html', recaptcha_site_key=recaptcha_site_key)

        username   = request.form.get('username', '').strip()
        password   = request.form.get('password', '')
        ip_address = request.remote_addr

        # Brute-force kilit kontrolü
        if is_account_locked(username, ip_address):
            flash('Cok fazla basarisiz deneme. Lutfen daha sonra tekrar deneyin.', 'danger')
            return render_template('login.html', recaptcha_site_key=recaptcha_site_key)

        admin = Admin.query.filter_by(username=username).first()

        # Timing attack önlemi — kullanıcı yoksa bile hash kontrolü yap
        hash_to_check = admin.password_hash if admin else DUMMY_HASH
        password_ok   = ph_verify(password, hash_to_check)

        if admin and password_ok:
            record_attempt(username, ip_address, success=True)

            # Hash upgrade gerekiyorsa (bcrypt → argon2id)
            if ph_needs_upgrade(admin.password_hash):
                admin.password_hash = ph_hash(password)
                logger.info(f"Admin '{username}' hash'i argon2id'e yukseltildi.")

            # Session token rotation
            new_token = secrets.token_hex(32)
            admin.session_token = new_token
            db.session.commit()

            login_user(admin, remember=False)
            session['session_token'] = new_token
            # 30 dk hareketsizlikte oturum düşsün (PERMANENT_SESSION_LIFETIME);
            # her istekte süre yenilenir.
            session.permanent = True

            # Audit log
            db.session.add(AuditLog(
                admin=username, ip_address=ip_address,
                action='admin_giris', detail=f'Basarili giris | IP: {ip_address}'
            ))
            db.session.commit()
            return safe_redirect(request.args.get('next'), url_for('admin.admin_dashboard'))
        else:
            record_attempt(username, ip_address, success=False)
            flash('Kullanici adi veya sifre hatali!', 'danger')

    return render_template('login.html', recaptcha_site_key=recaptcha_site_key)


# ── Çıkış ──────────────────────────────────────────────────────────

@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """Güvenli çıkış — session token invalidate.
    Sadece POST + CSRF: başka bir site admini habersizce çıkış yaptıramaz."""
    audit('admin_cikis', 'Guvenli cikis yapildi')
    if current_user.is_authenticated:
        current_user.session_token = None
        db.session.commit()
    logout_user()
    session.clear()
    flash('Guvenli cikis yapildi.', 'info')
    return redirect(url_for('auth.admin_login'))


# ── Şifre değiştir ─────────────────────────────────────────────────

@auth_bp.route('/admin/change_password', methods=['POST'])
@login_required
def change_password():
    """Admin şifre değiştirme işlemi."""
    current_pw = request.form.get('current_password', '')
    new_pw     = request.form.get('new_password', '')
    confirm_pw = request.form.get('confirm_password', '')

    if not ph_verify(current_pw, current_user.password_hash):
        flash('Mevcut sifreniz yanlis!', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    if new_pw != confirm_pw:
        flash('Yeni sifreler eslesmiyor!', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    if current_pw == new_pw:
        flash('Yeni sifre mevcut sifreden farkli olmalidir!', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    pw_errors = validate_password(new_pw)
    if pw_errors:
        for err in pw_errors:
            flash(f'Sifre hatasi: {err}', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    current_user.password_hash = ph_hash(new_pw)
    current_user.session_token = None
    db.session.commit()
    audit('sifre_degistir', 'Admin sifresi degistirildi — tum oturumlar sonlandirildi')
    logout_user()
    session.clear()
    flash('Sifreniz basariyla degistirildi. Lutfen yeni sifrenizle giris yapin.', 'success')
    return redirect(url_for('auth.admin_login'))
