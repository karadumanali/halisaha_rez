"""
routes/public.py — Herkese acik (public) rotalar.

index        : Ana sayfa — sahalar + rezervasyon formu
busy_slots   : AJAX — secili tarih/saha icin dolu slotlar
reserve      : Yeni rezervasyon formu POST islemi
track        : Rezervasyon takip sayfasi
csp_report   : CSP ihlal raporu uc noktasi
"""

import os
import re
import logging
from datetime import datetime, timedelta

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, jsonify, current_app, Response, session
)

from extensions import db, limiter
from models import Pitch, Reservation, BlockedSlot
from utils.constants import VALID_SLOTS
from utils.helpers import get_real_ip
from services.security import verify_recaptcha
from services.file_handler import save_secure_receipt
from services.email import send_admin_notification

logger = logging.getLogger(__name__)

public_bp = Blueprint('public', __name__)


# ── CSP raporu ─────────────────────────────────────────────────────

@public_bp.route('/csp-report', methods=['POST'])
def csp_report():
    """CSP ihlal raporlarını yakala ve logla."""
    try:
        report = request.get_json(force=True, silent=True) or {}
        violation = report.get('csp-report', report)
        logger.warning(
            "CSP ihlali: blocked-uri=%s, violated-directive=%s, "
            "document-uri=%s, ip=%s",
            violation.get('blocked-uri', '-'),
            violation.get('violated-directive', '-'),
            violation.get('document-uri', '-'),
            get_real_ip()
        )
    except Exception as e:
        logger.error(f"CSP raporu islenirken hata olustu: {e}")
    return '', 204


# ── Ana sayfa ──────────────────────────────────────────────────────

@public_bp.route('/')
def index():
    """Ana sayfa: tüm sahaları listele, rezervasyon formu göster."""
    pitches = Pitch.query.all()
    today_date = datetime.now().date().isoformat()
    recaptcha_site_key = os.getenv('RECAPTCHA_SITE_KEY', '')
    return render_template(
        'index.html',
        pitches=pitches,
        today_date=today_date,
        recaptcha_site_key=recaptcha_site_key,
        site_iban=os.getenv('SITE_IBAN', '')
    )


# ── Dolu slot sorgulama (AJAX) ────────────────────────────────────

@public_bp.route('/busy_slots')
@limiter.limit("5 per minute")
def busy_slots():
    """Belirtilen tarih ve saha için dolu/kilitli slotları döndür."""
    date_str = request.args.get('date')
    try:
        pitch_id = int(request.args.get('pitch_id', 0))
    except (ValueError, TypeError):
        return jsonify({'busy': {}, 'blocked': {}})

    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception:
        return jsonify({'busy': {}, 'blocked': {}})

    busy_records = Reservation.query.filter_by(
        pitch_id=pitch_id, date=date_obj
    ).filter(Reservation.status.in_(['Pending', 'Approved'])).all()
    busy_dict = {r.time_slot: r.status for r in busy_records}

    blocked = BlockedSlot.query.filter_by(pitch_id=pitch_id, date=date_obj).all()
    blocked_dict = {b.time_slot: b.reason for b in blocked}

    return jsonify({'busy': busy_dict, 'blocked': blocked_dict})


# ── Rezervasyon oluşturma ──────────────────────────────────────────

@public_bp.route('/reserve', methods=['POST'])
@limiter.limit("3 per minute")
@limiter.limit("10 per day")
def reserve():
    """Yeni rezervasyon talebi oluştur."""

    # Honeypot tuzak alanı kontrolü
    if request.form.get('website', ''):
        logger.warning(f"Honeypot tetiklendi — IP: {request.remote_addr}")
        flash('Rezervasyon talebiniz alindi! Yonetici onayindan sonra kesinlesecektir.', 'success')
        return redirect(url_for('public.index'))

    # reCAPTCHA doğrulaması
    if not verify_recaptcha(request.form.get('g-recaptcha-response', ''), action='reserve'):
        flash('Bot dogrulamasi basarisiz. Lutfen tekrar deneyin.', 'danger')
        return redirect(url_for('public.index'))

    pitch_id      = request.form.get('pitch_id')
    date_str      = request.form.get('date')
    time_slot     = request.form.get('time_slot')
    customer_name = request.form.get('customer_name', '').strip()

    # Saat dilimi doğrulama
    if time_slot not in VALID_SLOTS:
        flash('Gecersiz saat dilimi!', 'danger')
        return redirect(url_for('public.index'))

    # Saha ID doğrulama
    try:
        pitch_id = int(pitch_id)
    except (ValueError, TypeError):
        flash('Gecersiz saha!', 'danger')
        return redirect(url_for('public.index'))

    # İsim doğrulama
    if not customer_name or len(customer_name) < 2 or len(customer_name) > 100:
        flash('Gecersiz isim! En az 2, en fazla 100 karakter olmalidir.', 'danger')
        return redirect(url_for('public.index'))

    if not re.match(r'^[a-zA-ZçÇğĞıİöÖşŞüÜ\s\-\.]+$', customer_name):
        flash('Isim sadece harf, bosluk ve tire icerebilir!', 'danger')
        return redirect(url_for('public.index'))

    # Telefon doğrulama
    raw_phone   = request.form.get('customer_phone', '')
    clean_phone = raw_phone.replace(" ", "")
    if not re.match(r"^05\d{9}$", clean_phone):
        flash('Gecersiz telefon! 05XX XXX XX XX formatinda 11 haneli girin.', 'danger')
        return redirect(url_for('public.index'))

    # E-posta doğrulama
    customer_email = request.form.get('customer_email', '').strip()
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", customer_email):
        flash('Gecersiz e-posta!', 'danger')
        return redirect(url_for('public.index'))

    # Tarih doğrulama
    try:
        date_obj     = datetime.strptime(date_str, '%Y-%m-%d').date()
        _now         = datetime.now()
        current_date = _now.date()
        current_time = _now.time()
        max_date     = (_now + timedelta(days=31)).date()

        if date_obj < current_date:
            flash('Gecmis bir tarihe rezervasyon yapilamaz!', 'danger')
            return redirect(url_for('public.index'))

        if date_obj > max_date:
            flash('En fazla 1 ay ilerisine rezervasyon yapilabilir!', 'danger')
            return redirect(url_for('public.index'))

        # Hafta sonu kontrolü (5=Cumartesi, 6=Pazar)
        if date_obj.weekday() >= 5:
            flash('Hafta sonlari rezervasyon yapilamaz! Lutfen hafta ici bir tarih secin.', 'danger')
            return redirect(url_for('public.index'))

        if date_obj == current_date:
            start_time_str = time_slot.split(' - ')[0].strip()
            if datetime.strptime(start_time_str, '%H:%M').time() <= current_time:
                flash('Sectiginiz saat dilimi gecmistir!', 'danger')
                return redirect(url_for('public.index'))
    except (ValueError, IndexError, AttributeError):
        flash('Gecersiz tarih veya saat!', 'danger')
        return redirect(url_for('public.index'))

    # Kilitli slot kontrolü
    blocked = BlockedSlot.query.filter_by(
        pitch_id=pitch_id, date=date_obj, time_slot=time_slot
    ).first()
    if blocked:
        flash(f'Bu saat dilimi kilitli: {blocked.reason}', 'danger')
        return redirect(url_for('public.index'))

    # Race condition önlemi — FOR UPDATE ile satır kilitle
    existing = Reservation.query.filter_by(
        pitch_id=pitch_id, date=date_obj, time_slot=time_slot
    ).filter(Reservation.status.in_(['Pending', 'Approved'])).with_for_update().first()
    if existing:
        flash('Bu saat dilimi dolu veya onay bekliyor!', 'danger')
        return redirect(url_for('public.index'))

    # Dekont dosyası kaydet
    saved_filename = save_secure_receipt(request.files.get('receipt'))
    if not saved_filename:
        flash('Gecersiz dosya! PDF, JPG veya PNG yukleyin.', 'danger')
        return redirect(url_for('public.index'))

    # Yeni rezervasyon oluştur
    new_res = Reservation(
        pitch_id=pitch_id, date=date_obj, time_slot=time_slot,
        customer_name=customer_name, customer_phone=clean_phone,
        customer_email=customer_email, receipt_filename=saved_filename
    )
    db.session.add(new_res)

    # UNIQUE constraint ihlalini yakala (race condition son savunma hattı)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Bu saat dilimi dolu veya onay bekliyor!', 'danger')
        return redirect(url_for('public.index'))

    send_admin_notification(customer_name, date_obj, time_slot)

    # Takip kodunu session'a kaydet — redirect sonrasi success sayfasinda gosterilecek
    session['tracking_code'] = new_res.tracking_code
    session['tracking_pitch'] = new_res.pitch.name
    session['tracking_date'] = date_obj.strftime('%d.%m.%Y')
    session['tracking_slot'] = time_slot

    return redirect(url_for('public.reservation_success'))


# ── Rezervasyon basarili sayfasi ───────────────────────────────────

@public_bp.route('/rezervasyon-basarili')
def reservation_success():
    """Rezervasyon basarili — takip kodunu goster."""
    tracking_code  = session.pop('tracking_code', None)
    tracking_pitch = session.pop('tracking_pitch', None)
    tracking_date  = session.pop('tracking_date', None)
    tracking_slot  = session.pop('tracking_slot', None)

    if not tracking_code:
        return redirect(url_for('public.index'))

    return render_template(
        'reservation_success.html',
        tracking_code=tracking_code,
        pitch_name=tracking_pitch,
        date_str=tracking_date,
        time_slot=tracking_slot,
        hide_fab=True
    )


# ── Rezervasyon takip/sorgulama ───────────────────────────────────

@public_bp.route('/rezervasyon-sorgula')
def track_reservation_page():
    """Rezervasyon takip sayfasi — form goster."""
    return render_template('track.html', reservation=None, searched=False, hide_fab=True)


@public_bp.route('/rezervasyon-sorgula', methods=['POST'])
@limiter.limit("10 per minute")
def track_reservation():
    """Takip koduna gore rezervasyon durumunu sorgula."""
    code = request.form.get('tracking_code', '').strip().upper()

    if not code:
        flash('Lutfen takip kodunuzu girin.', 'warning')
        return render_template('track.html', reservation=None, searched=False, hide_fab=True)

    reservation = Reservation.query.filter_by(tracking_code=code).first()
    return render_template('track.html', reservation=reservation, searched=True, code=code, hide_fab=True)


# ── security.txt ───────────────────────────────────────────────────

@public_bp.route('/.well-known/security.txt')
def security_txt():
    """Güvenlik araştırmacıları için iletişim bilgileri."""
    file_path = os.path.join(current_app.root_path, 'static', '.well-known', 'security.txt')
    try:
        content = open(file_path, encoding='utf-8').read()
        return Response(content, mimetype='text/plain')
    except FileNotFoundError:
        return ('', 404)
