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

from sqlalchemy import func, or_

from extensions import db, limiter
from models import Pitch, Reservation, BlockedSlot, PitchTimeSlot, CustomerType, AuditLog
from utils.constants import ACTIVE_STATUSES, MAX_RESERVATIONS_PER_PERSON_PER_DAY
from utils.helpers import get_real_ip
from utils.timeutil import now_tr, today_tr
from services.security import verify_recaptcha
from services.file_handler import save_secure_receipt, delete_receipt
from services.email import send_admin_notification, send_customer_received_email

logger = logging.getLogger(__name__)

public_bp = Blueprint('public', __name__)

# Kampüs ağında tüm öğrenciler tek IP ile göründüğü için (NAT) herkese açık
# sayfaların IP başına limitleri yüksek tutulur; aksi halde öğrenciler birbirinin
# limitini tüketip 429 alır. Bot/spam koruması reCAPTCHA + kişi başı kural ile.
PUBLIC_PAGE_LIMIT = "300 per minute"


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
@limiter.limit(PUBLIC_PAGE_LIMIT)
def index():
    """Ana sayfa: fiyatı tanımlı sahaları listele, rezervasyon formu göster."""
    pitches = [p for p in Pitch.query.filter_by(is_active=True).order_by(Pitch.id).all() if p.pricing]
    customer_types = CustomerType.query.order_by(CustomerType.id).all()
    today_date = today_tr().isoformat()
    recaptcha_site_key = os.getenv('RECAPTCHA_SITE_KEY', '')
    return render_template(
        'index.html',
        pitches=pitches,
        customer_types=customer_types,
        today_date=today_date,
        recaptcha_site_key=recaptcha_site_key,
        site_iban=os.getenv('SITE_IBAN', '')
    )


# ── Dolu slot sorgulama (AJAX) ────────────────────────────────────

@public_bp.route('/busy_slots')
@limiter.limit("600 per minute")
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
    ).filter(Reservation.status.in_(ACTIVE_STATUSES)).all()
    busy_dict = {r.time_slot: r.status for r in busy_records}

    blocked = BlockedSlot.query.filter_by(pitch_id=pitch_id, date=date_obj).all()
    blocked_dict = {b.time_slot: b.reason for b in blocked}

    # Sahaya özel tanımlı saat dilimlerini de döndür
    time_slots = PitchTimeSlot.query.filter_by(pitch_id=pitch_id)\
        .order_by(PitchTimeSlot.start_hour).all()
    available_slots = [ts.label for ts in time_slots]

    return jsonify({
        'busy': busy_dict,
        'blocked': blocked_dict,
        'available_slots': available_slots
    })


# ── Rezervasyon oluşturma ──────────────────────────────────────────

@public_bp.route('/reserve', methods=['POST'])
@limiter.limit("20 per minute; 300 per day")   # IP (kampüs) tavanı; kişi başı kural aşağıda
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
    ctype_id      = request.form.get('customer_type_id')
    date_str      = request.form.get('date')
    time_slot     = request.form.get('time_slot')
    customer_name = request.form.get('customer_name', '').strip()

    # Saha ID doğrulama
    try:
        pitch_id = int(pitch_id)
    except (ValueError, TypeError):
        flash('Gecersiz saha!', 'danger')
        return redirect(url_for('public.index'))

    # Müşteri tipi + ücret doğrulama — ücret istemciden değil, DB'den alınır
    pitch = db.session.get(Pitch, pitch_id)
    if pitch is None or not pitch.is_active:
        flash('Gecersiz saha!', 'danger')
        return redirect(url_for('public.index'))
    try:
        ctype_id = int(ctype_id)
    except (ValueError, TypeError):
        ctype_id = None
    price = pitch.price_for(ctype_id) if pitch and ctype_id else None
    if price is None:
        flash('Lutfen gecerli bir musteri tipi secin!', 'danger')
        return redirect(url_for('public.index'))

    # Saat dilimi doğrulama — sahaya özel tanımlı slotlardan mı?
    # (Slotlar müşteri tipinden bağımsız ortaktır: fiziksel saha tek)
    valid_slots = [ts.label for ts in pitch.time_slots]
    if time_slot not in valid_slots:
        flash('Gecersiz saat dilimi!', 'danger')
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
        _now         = now_tr()
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

    # Kişi başı kural: aynı telefon VEYA e-posta ile bugün oluşturulmuş en fazla
    # MAX_RESERVATIONS_PER_PERSON_PER_DAY aktif (bekleyen + onaylı) talep
    day_start = datetime.combine(current_date, datetime.min.time())
    person_today = Reservation.query.filter(
        Reservation.created_at >= day_start,
        Reservation.created_at < day_start + timedelta(days=1),
        Reservation.status.in_(ACTIVE_STATUSES),
        or_(Reservation.customer_phone == clean_phone,
            func.lower(Reservation.customer_email) == customer_email.lower())
    ).count()
    if person_today >= MAX_RESERVATIONS_PER_PERSON_PER_DAY:
        flash(f'Bir gunde en fazla {MAX_RESERVATIONS_PER_PERSON_PER_DAY} rezervasyon talebi '
              f'olusturabilirsiniz. Bugun zaten {person_today} aktif talebiniz var.', 'danger')
        return redirect(url_for('public.index'))

    # Race condition önlemi — FOR UPDATE ile satır kilitle
    existing = Reservation.query.filter_by(
        pitch_id=pitch_id, date=date_obj, time_slot=time_slot
    ).filter(Reservation.status.in_(ACTIVE_STATUSES)).with_for_update().first()
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
        customer_email=customer_email, receipt_filename=saved_filename,
        customer_type_id=ctype_id, price=price
    )
    db.session.add(new_res)

    # UNIQUE constraint ihlalini yakala (race condition son savunma hattı)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        delete_receipt(saved_filename)   # kayıt oluşmadı → yüklenen dekont diskte kalmasın
        flash('Bu saat dilimi dolu veya onay bekliyor!', 'danger')
        return redirect(url_for('public.index'))

    send_admin_notification(customer_name, date_obj, time_slot)

    # Müşteriye "talebiniz alındı" maili — sorgulama kodu ve takip linkiyle
    send_customer_received_email(
        customer_email, customer_name,
        tracking_code=new_res.tracking_code,
        pitch_name=new_res.pitch.name,
        date_str=date_obj.strftime('%d.%m.%Y'),
        time_slot=time_slot,
        ctype_name=new_res.customer_type.name,
        price=price,
        track_url=url_for('public.track_reservation_page', _external=True),
    )

    # Takip kodunu session'a kaydet — redirect sonrasi success sayfasinda gosterilecek
    session['tracking_code'] = new_res.tracking_code
    session['tracking_pitch'] = new_res.pitch.name
    session['tracking_date'] = date_obj.strftime('%d.%m.%Y')
    session['tracking_slot'] = time_slot
    session['tracking_ctype'] = new_res.customer_type.name
    session['tracking_price'] = price

    return redirect(url_for('public.reservation_success'))


# ── Rezervasyon basarili sayfasi ───────────────────────────────────

@public_bp.route('/rezervasyon-basarili')
@limiter.limit(PUBLIC_PAGE_LIMIT)
def reservation_success():
    """Rezervasyon basarili — takip kodunu goster."""
    tracking_code  = session.pop('tracking_code', None)
    tracking_pitch = session.pop('tracking_pitch', None)
    tracking_date  = session.pop('tracking_date', None)
    tracking_slot  = session.pop('tracking_slot', None)
    tracking_ctype = session.pop('tracking_ctype', None)
    tracking_price = session.pop('tracking_price', None)

    if not tracking_code:
        return redirect(url_for('public.index'))

    return render_template(
        'reservation_success.html',
        tracking_code=tracking_code,
        pitch_name=tracking_pitch,
        date_str=tracking_date,
        time_slot=tracking_slot,
        ctype_name=tracking_ctype,
        price=tracking_price,
        hide_fab=True
    )


# ── Rezervasyon takip/sorgulama ───────────────────────────────────

def _can_cancel(reservation) -> bool:
    """Kullanıcı iptal edebilir mi? Bekleyen/onaylı ve saati henüz başlamamış olmalı."""
    if reservation is None or reservation.status not in ACTIVE_STATUSES:
        return False
    try:
        start_str = reservation.time_slot.split(' - ')[0].strip()
        start = datetime.combine(reservation.date, datetime.strptime(start_str, '%H:%M').time())
    except (ValueError, IndexError, AttributeError):
        return False
    return start > now_tr()


def _render_track(reservation=None, searched=False, code=''):
    return render_template('track.html', reservation=reservation, searched=searched,
                           code=code, can_cancel=_can_cancel(reservation), hide_fab=True)


@public_bp.route('/rezervasyon-sorgula')
@limiter.limit(PUBLIC_PAGE_LIMIT)
def track_reservation_page():
    """Rezervasyon takip sayfasi — form goster."""
    return _render_track()


@public_bp.route('/rezervasyon-sorgula', methods=['POST'])
@limiter.limit("60 per minute")
def track_reservation():
    """Takip koduna gore rezervasyon durumunu sorgula."""
    code = request.form.get('tracking_code', '').strip().upper()

    if not code:
        flash('Lutfen takip kodunuzu girin.', 'warning')
        return _render_track()

    reservation = Reservation.query.filter_by(tracking_code=code).first()
    return _render_track(reservation, searched=True, code=code)


@public_bp.route('/rezervasyon-iptal', methods=['POST'])
@limiter.limit("30 per minute")
def cancel_reservation():
    """Kullanıcı kendi rezervasyonunu iptal eder: takip kodu + kayıtlı telefon gerekir."""
    code  = request.form.get('tracking_code', '').strip().upper()
    phone = request.form.get('customer_phone', '').replace(' ', '').strip()

    reservation = Reservation.query.filter_by(tracking_code=code).with_for_update().first() if code else None
    if reservation is None:
        flash('Rezervasyon bulunamadi.', 'danger')
        return _render_track(searched=bool(code), code=code)

    if not phone or phone != reservation.customer_phone:
        flash('Telefon numarasi bu rezervasyondaki numarayla eslesmiyor.', 'danger')
        return _render_track(reservation, searched=True, code=code)

    if not _can_cancel(reservation):
        flash('Bu rezervasyon iptal edilemez (islem gormus veya saati gecmis).', 'warning')
        return _render_track(reservation, searched=True, code=code)

    old_status = reservation.status
    reservation.status = 'Cancelled'
    db.session.add(AuditLog(
        admin='musteri', ip_address=get_real_ip(), action='kullanici_iptal',
        detail=(f'kod={reservation.tracking_code} | musteri={reservation.customer_name} '
                f'| saha={reservation.pitch.name} | tarih={reservation.date} '
                f'| saat={reservation.time_slot} | onceki durum={old_status}')
    ))
    db.session.commit()
    flash('Rezervasyonunuz iptal edildi. Saat diger kullanicilara acildi.', 'success')
    return _render_track(reservation, searched=True, code=code)


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
