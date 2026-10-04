"""
routes/admin.py — Yönetim paneli (admin) rotaları.

Tüm rotalar @login_required ile korunur.
URL prefix: /admin (Blueprint kayıt sırasında verilir)
"""

import os
import re
import logging
from datetime import datetime, timedelta, date as date_type

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, send_from_directory, make_response,
    current_app, jsonify
)
from flask_login import login_required, current_user
from sqlalchemy import func
from PIL import Image

from extensions import db, limiter
from models import (
    Pitch, PitchImage, Reservation, BlockedSlot,
    AuditLog, PitchTimeSlot, CustomerType, PitchPricing
)
from utils.constants import SLOT_GROUPS, SLOT_START_HOURS
from utils.helpers import audit, get_real_ip
from services.security import detect_mime
from services.file_handler import allowed_file, save_secure_pitch_image
from services.email import send_customer_approval_email
from services.pdf_report import generate_report
from services.scheduler import auto_expire_reservations, auto_cleanup_blocked_slots

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__)


# ── Dashboard ──────────────────────────────────────────────────────

@admin_bp.route('/')
@login_required
def admin_dashboard():
    """Admin ana paneli — istatistikler, rezervasyonlar, kilitli slotlar."""
    # Her sayfa açılışında otomatik temizlik
    auto_expire_reservations()
    auto_cleanup_blocked_slots()

    # Sayfalama
    page       = request.args.get('page', 1, type=int)
    per_page   = 20
    date_range = request.args.get('date_range', '')
    pitch_filter = request.args.get('pitch', 'all')
    ctype_filter = request.args.get('ctype', 'all')

    pitches        = Pitch.query.all()
    customer_types = CustomerType.query.order_by(CustomerType.id).all()

    # Temel sorgu
    query = Reservation.query

    # Tarih filtresi
    today = date_type.today()
    if date_range == 'today':
        query = query.filter(Reservation.date == today)
    elif date_range == 'week':
        week_start = today - timedelta(days=today.weekday())  # Pazartesi
        week_end   = week_start + timedelta(days=6)           # Pazar
        query = query.filter(Reservation.date >= week_start, Reservation.date <= week_end)
    elif date_range == 'month':
        month_start = today.replace(day=1)
        # Ayin son gunu
        if today.month == 12:
            month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        query = query.filter(Reservation.date >= month_start, Reservation.date <= month_end)

    # Saha filtresi
    if pitch_filter and pitch_filter != 'all':
        try:
            query = query.filter(Reservation.pitch_id == int(pitch_filter))
        except (ValueError, TypeError):
            pass

    # Müşteri tipi filtresi
    if ctype_filter and ctype_filter != 'all':
        try:
            query = query.filter(Reservation.customer_type_id == int(ctype_filter))
        except (ValueError, TypeError):
            pass

    pagination = query.order_by(
        Reservation.created_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    reservations = pagination.items

    # Filtrelenmis toplam
    filtered_count = pagination.total

    # Genel istatistikler (filtresiz)
    status_counts = dict(
        db.session.query(Reservation.status, func.count(Reservation.id))
        .group_by(Reservation.status).all()
    )
    total_count = sum(status_counts.values())

    blocked_slots = BlockedSlot.query.order_by(
        BlockedSlot.date.asc(), BlockedSlot.time_slot.asc()
    ).all()
    audit_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(200).all()

    return render_template(
        'admin.html',
        pitches=pitches,
        customer_types=customer_types,
        reservations=reservations,
        pagination=pagination,
        status_counts=status_counts,
        total_count=total_count,
        filtered_count=filtered_count,
        blocked_slots=blocked_slots,
        audit_logs=audit_logs,
        slot_groups=SLOT_GROUPS,
        now=datetime.now()
    )


# ── Slot kilitleme / kilit kaldırma ───────────────────────────────

@admin_bp.route('/block_slot', methods=['POST'])
@login_required
def block_slot():
    """Seçilen saha/tarih/saat kombinasyonlarını kilitle."""
    pitch_ids  = request.form.getlist('pitch_ids')
    dates      = request.form.getlist('dates')
    time_slots = request.form.getlist('time_slots')
    reason     = request.form.get('reason', 'Bakim / Rezerve').strip()[:200]

    if not pitch_ids or not dates or not time_slots:
        flash('Saha, tarih ve saat dilimi secmelisiniz!', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    added = 0
    skipped = 0
    for pitch_id in pitch_ids:
        for date_str in dates:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                continue
            for time_slot in time_slots:
                existing = BlockedSlot.query.filter_by(
                    pitch_id=pitch_id, date=date_obj, time_slot=time_slot
                ).first()
                if existing:
                    skipped += 1
                    continue
                db.session.add(BlockedSlot(
                    pitch_id=pitch_id, date=date_obj,
                    time_slot=time_slot, reason=reason
                ))
                added += 1

    db.session.commit()
    msg = f'{added} slot basariyla kilitlendi.'
    if skipped > 0:
        msg += f' ({skipped} slot zaten kilitliydi, atlandi.)'
    if added > 0:
        audit('slot_kilitle',
              f'{added} slot kilitlendi | saha_ids={pitch_ids} '
              f'| tarihler={dates} | saatler={time_slots} | sebep={reason}')
    flash(msg, 'success' if added > 0 else 'warning')
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/unblock_slot/<int:block_id>', methods=['POST'])
@login_required
def unblock_slot(block_id):
    """Belirtilen slot kilidini kaldır."""
    block = db.get_or_404(BlockedSlot, block_id)
    audit('slot_kilit_kaldir',
          f'saha={block.pitch.name} | tarih={block.date} '
          f'| saat={block.time_slot} | sebep={block.reason}')
    db.session.delete(block)
    db.session.commit()
    flash('Slot kilidi kaldirildi.', 'success')
    return redirect(url_for('admin.admin_dashboard'))


# ── Toplu slot kilit kaldırma ──────────────────────────────────────

@admin_bp.route('/bulk_unblock_slots', methods=['POST'])
@login_required
def bulk_unblock_slots():
    """Seçili slot kilitlerini toplu olarak kaldır."""
    block_ids = request.form.getlist('block_ids')
    if not block_ids:
        flash('Kaldirmak icin en az bir kilit secmelisiniz!', 'warning')
        return redirect(url_for('admin.admin_dashboard'))

    count = 0
    details = []
    for block_id in block_ids:
        try:
            block = db.session.get(BlockedSlot, int(block_id))
            if block:
                details.append(
                    f'{block.pitch.name} | {block.date} | {block.time_slot}'
                )
                db.session.delete(block)
                count += 1
        except (ValueError, TypeError):
            continue

    if count > 0:
        db.session.commit()
        audit('toplu_kilit_kaldir',
              f'{count} slot kilidi toplu olarak kaldirildi | detay: {"; ".join(details[:5])}'
              + (f' ... ve {count - 5} daha' if count > 5 else ''))
        flash(f'{count} slot kilidi basariyla kaldirildi.', 'success')
    else:
        flash('Secili kilitler bulunamadi.', 'warning')

    return redirect(url_for('admin.admin_dashboard'))


# ── Saha yönetimi ─────────────────────────────────────────────────

def _parse_price(value):
    """Formdaki ücreti doğrula; geçersizse None döner."""
    value = (value or '').strip()
    if not value.isdigit() or int(value) > 99999:
        return None
    return int(value)


def _parse_slot_hours(values):
    """Formdaki slot_hours değerlerini doğrula; geçerli saatleri sıralı döndür."""
    hours = set()
    for v in values:
        try:
            h = int(v)
        except (ValueError, TypeError):
            continue
        if h in SLOT_START_HOURS:
            hours.add(h)
    return sorted(hours)


def _parse_pricing(form, customer_types):
    """Formdaki price_<tip_id> alanlarını oku.
    Boş bırakılan tip o sahayı rezerve edemez. → ({tip_id: fiyat}, hata)"""
    prices = {}
    for ct in customer_types:
        raw = (form.get(f'price_{ct.id}') or '').strip()
        if not raw:
            continue
        price = _parse_price(raw)
        if price is None:
            return None, f'"{ct.name}" için geçersiz ücret!'
        prices[ct.id] = price
    if not prices:
        return None, 'En az bir müşteri tipi için ücret girmelisiniz!'
    return prices, None


def _pricing_label(prices, customer_types):
    """{1: 500, 2: 800} → 'Öğrenci=500 TL, İdari Personel=800 TL'"""
    return ', '.join(f'{ct.name}={prices[ct.id]} TL'
                     for ct in customer_types if ct.id in prices)


def _fmt_price(price, empty='—'):
    return empty if price is None else f'{price} TL'


@admin_bp.route('/add_pitch', methods=['POST'])
@login_required
def add_pitch():
    """Yeni saha ekle — ad, tip bazlı ücretler ve saat aralıkları tek adımda kaydedilir."""
    customer_types = CustomerType.query.order_by(CustomerType.id).all()
    name       = request.form.get('name', '').strip()
    slot_hours = _parse_slot_hours(request.form.getlist('slot_hours'))
    if not name or not re.match(r'^[a-zA-Z0-9\s\-çÇğĞıİöÖşŞüÜ]+$', name) or len(name) > 100:
        flash('Saha adi sadece harf, rakam, bosluk ve tire icerebilir!', 'danger')
        return redirect(url_for('admin.admin_dashboard', tab='sahalar'))
    prices, error = _parse_pricing(request.form, customer_types)
    if error:
        flash(error, 'danger')
        return redirect(url_for('admin.admin_dashboard', tab='sahalar'))
    if not slot_hours:
        flash('En az bir saat aralığı seçmelisiniz!', 'danger')
        return redirect(url_for('admin.admin_dashboard', tab='sahalar'))

    pitch = Pitch(name=name)
    pitch.pricing    = [PitchPricing(customer_type_id=t, price=p) for t, p in prices.items()]
    pitch.time_slots = [PitchTimeSlot(start_hour=h, end_hour=h + 1) for h in slot_hours]
    db.session.add(pitch)
    db.session.commit()
    audit('saha_ekle',
          f'saha={name} | fiyatlar={_pricing_label(prices, customer_types)} '
          f'| saatler={", ".join(PitchTimeSlot.ranges(slot_hours))}')
    flash(f'"{name}" {len(slot_hours)} saat aralığıyla eklendi!', 'success')
    return redirect(url_for('admin.admin_dashboard', tab='sahalar'))


@admin_bp.route('/update_pitch/<int:pitch_id>', methods=['POST'])
@login_required
def update_pitch(pitch_id):
    """Saha ücretlerini (tip bazlı) ve saat aralıklarını güncelle."""
    pitch          = db.get_or_404(Pitch, pitch_id)
    customer_types = CustomerType.query.order_by(CustomerType.id).all()
    slot_hours     = _parse_slot_hours(request.form.getlist('slot_hours'))
    prices, error  = _parse_pricing(request.form, customer_types)
    if error:
        flash(error, 'danger')
        return redirect(url_for('admin.admin_dashboard', tab='sahalar'))
    if not slot_hours:
        flash('En az bir saat aralığı seçmelisiniz!', 'danger')
        return redirect(url_for('admin.admin_dashboard', tab='sahalar'))

    changes = []

    old_prices = pitch.price_map
    if old_prices != prices:
        kept = []
        for pp in pitch.pricing:
            if pp.customer_type_id in prices:
                pp.price = prices[pp.customer_type_id]
                kept.append(pp)
        kept += [PitchPricing(customer_type_id=t, price=p)
                 for t, p in prices.items() if t not in old_prices]
        # delete-orphan cascade: listeden çıkan fiyatlar silinir
        pitch.pricing = kept
        for ct in customer_types:
            old, new = old_prices.get(ct.id), prices.get(ct.id)
            if old != new:
                changes.append(f'{ct.name}: {_fmt_price(old)} → {_fmt_price(new, "kapalı")}')

    old_hours = set(pitch.slot_hours)
    new_hours = set(slot_hours)
    added     = sorted(new_hours - old_hours)
    removed   = sorted(old_hours - new_hours)
    if added or removed:
        pitch.time_slots = (
            [ts for ts in pitch.time_slots if ts.start_hour in new_hours]
            + [PitchTimeSlot(start_hour=h, end_hour=h + 1) for h in added]
        )
        if added:
            changes.append(f'eklenen saatler: {", ".join(PitchTimeSlot.ranges(added))}')
        if removed:
            changes.append(f'kaldırılan saatler: {", ".join(PitchTimeSlot.ranges(removed))}')

    if not changes:
        flash('Herhangi bir değişiklik yapılmadı.', 'info')
        return redirect(url_for('admin.admin_dashboard', tab='sahalar'))

    db.session.commit()
    audit('saha_guncelle', f'saha={pitch.name} | ' + ' | '.join(changes))
    flash(f'"{pitch.name}" güncellendi.', 'success')
    return redirect(url_for('admin.admin_dashboard', tab='sahalar'))


# ── Müşteri tipi yönetimi ─────────────────────────────────────────

_CTYPE_NAME_RE = re.compile(r'^[a-zA-Z0-9\s\-/().çÇğĞıİöÖşŞüÜ]+$')


def _validate_ctype_name(name, exclude_id=None):
    """Müşteri tipi adını doğrula; hata mesajı ya da None döner."""
    if len(name) < 2 or len(name) > 60 or not _CTYPE_NAME_RE.match(name):
        return 'Tip adı 2-60 karakter olmalı; harf, rakam, boşluk ve - / ( ) . içerebilir!'
    # Büyük/küçük harf duyarsız karşılaştırma Python'da (SQLite lower() Türkçe harfleri küçültmez)
    key = _tr_lower(name)
    for ct in CustomerType.query.all():
        if ct.id != exclude_id and _tr_lower(ct.name) == key:
            return f'"{name}" adında bir müşteri tipi zaten var!'
    return None


def _tr_lower(text):
    """Türkçe kurallarıyla küçük harf: 'İ' → 'i', 'I' → 'ı'."""
    return text.replace('İ', 'i').replace('I', 'ı').lower()


def _ctype_redirect():
    return redirect(url_for('admin.admin_dashboard', tab='musteri-tipleri'))


@admin_bp.route('/customer_types/add', methods=['POST'])
@login_required
def add_customer_type():
    """Yeni müşteri tipi ekle; isteğe bağlı varsayılan ücret tüm sahalara uygulanır."""
    name  = ' '.join(request.form.get('name', '').split())
    error = _validate_ctype_name(name)
    if error:
        flash(error, 'danger')
        return _ctype_redirect()

    raw_price     = request.form.get('default_price', '').strip()
    default_price = _parse_price(raw_price) if raw_price else None
    if raw_price and default_price is None:
        flash('Geçersiz varsayılan ücret!', 'danger')
        return _ctype_redirect()

    ctype = CustomerType(name=name)
    if default_price is not None:
        ctype.pricing = [PitchPricing(pitch_id=p.id, price=default_price)
                         for p in Pitch.query.all()]
    db.session.add(ctype)
    db.session.commit()

    detail = f'tip={name}'
    if default_price is not None:
        detail += f' | varsayılan ücret={default_price} TL ({len(ctype.pricing)} sahaya uygulandı)'
    audit('musteri_tipi_ekle', detail)
    if default_price is None:
        flash(f'"{name}" eklendi. Sahalar sekmesinden bu tip için ücret belirleyin.', 'success')
    else:
        flash(f'"{name}" eklendi ve tüm sahalara {default_price} TL olarak tanımlandı.', 'success')
    return _ctype_redirect()


@admin_bp.route('/customer_types/<int:ctype_id>/update', methods=['POST'])
@login_required
def update_customer_type(ctype_id):
    """Müşteri tipini yeniden adlandır."""
    ctype = db.get_or_404(CustomerType, ctype_id)
    name  = ' '.join(request.form.get('name', '').split())
    error = _validate_ctype_name(name, exclude_id=ctype.id)
    if error:
        flash(error, 'danger')
        return _ctype_redirect()
    if name == ctype.name:
        flash('Herhangi bir değişiklik yapılmadı.', 'info')
        return _ctype_redirect()

    old_name   = ctype.name
    ctype.name = name
    db.session.commit()
    audit('musteri_tipi_guncelle', f'{old_name} → {name}')
    flash(f'"{old_name}" artık "{name}" olarak görünecek.', 'success')
    return _ctype_redirect()


@admin_bp.route('/customer_types/<int:ctype_id>/delete', methods=['POST'])
@login_required
def delete_customer_type(ctype_id):
    """Müşteri tipini sil — rezervasyonu olan tip silinemez (raporlar bozulmasın)."""
    ctype = db.get_or_404(CustomerType, ctype_id)
    if ctype.reservations:
        flash(f'"{ctype.name}" tipine ait {len(ctype.reservations)} rezervasyon var, silinemez. '
              f'Yeni rezervasyonları durdurmak için sahalardaki ücretini boş bırakın.', 'danger')
        return _ctype_redirect()

    name = ctype.name
    db.session.delete(ctype)
    db.session.commit()
    audit('musteri_tipi_sil', f'tip={name}')
    flash(f'"{name}" müşteri tipi silindi.', 'success')
    return _ctype_redirect()


@admin_bp.route('/delete_pitch/<int:pitch_id>', methods=['POST'])
@login_required
def delete_pitch(pitch_id):
    """Sahayı sil (cascade ile rezervasyonları da siler)."""
    pitch      = db.get_or_404(Pitch, pitch_id)
    pitch_name = pitch.name
    try:
        db.session.delete(pitch)
        db.session.commit()
        audit('saha_sil', f'saha={pitch_name}')
        flash(f'"{pitch_name}" silindi.', 'success')
    except Exception:
        db.session.rollback()
        flash('Bu sahaya ait rezervasyonlar var! Once onlari silin.', 'danger')
    return redirect(url_for('admin.admin_dashboard', tab='sahalar'))


# ── Rezervasyon durum değiştirme ──────────────────────────────────

@admin_bp.route('/status/<res_id>/<action>', methods=['POST'])
@login_required
def change_status(res_id, action):
    """Rezervasyonu onayla veya reddet."""
    if action not in ('approve', 'reject'):
        flash('Gecersiz islem!', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    # Race condition önlemi — FOR UPDATE
    reservation = Reservation.query.filter_by(id=res_id).with_for_update().first_or_404()

    if reservation.status == 'Expired':
        flash('Bu rezervasyonun suresi dolmus, islem yapilamaz.', 'warning')
        return redirect(url_for('admin.admin_dashboard'))

    if reservation.status != 'Pending':
        flash('Bu rezervasyon zaten islenmis.', 'warning')
        return redirect(url_for('admin.admin_dashboard'))

    if action == 'approve':
        reservation.status = 'Approved'
        send_customer_approval_email(
            reservation.customer_email, reservation.customer_name,
            reservation.pitch.name, reservation.date, reservation.time_slot
        )
        audit('rezervasyon_onayla',
              f'res_id={res_id} | musteri={reservation.customer_name} '
              f'| saha={reservation.pitch.name} | tarih={reservation.date} '
              f'| saat={reservation.time_slot}')
        flash('Rezervasyon ONAYLANDI.', 'success')
    elif action == 'reject':
        reservation.status = 'Rejected'
        audit('rezervasyon_reddet',
              f'res_id={res_id} | musteri={reservation.customer_name} '
              f'| saha={reservation.pitch.name} | tarih={reservation.date} '
              f'| saat={reservation.time_slot}')
        flash('Rezervasyon REDDEDILDI.', 'danger')

    db.session.commit()
    return redirect(url_for('admin.admin_dashboard'))


# ── Saha resmi ekleme ──────────────────────────────────────────────

@admin_bp.route('/pitch/<int:pitch_id>/add_image', methods=['POST'])
@login_required
def add_pitch_image(pitch_id):
    """Sahaya resim ekle."""
    pitch = db.get_or_404(Pitch, pitch_id)
    saved_filename = save_secure_pitch_image(request.files.get('image'))
    if not saved_filename:
        flash('Gecersiz resim!', 'danger')
        return redirect(url_for('admin.admin_dashboard'))
    db.session.add(PitchImage(pitch_id=pitch_id, image_filename=saved_filename))
    db.session.commit()
    flash(f'"{pitch.name}" icin resim eklendi.', 'success')
    return redirect(url_for('admin.admin_dashboard'))


# ── Logo güncelleme ────────────────────────────────────────────────

@admin_bp.route('/update_logo', methods=['POST'])
@login_required
def update_logo():
    """Site logosunu güncelle."""
    logo_file = request.files.get('logo')
    if not logo_file:
        flash('Lutfen bir resim secin.', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    file_content = logo_file.read(2048)
    logo_file.seek(0)
    mime_type = detect_mime(file_content)

    if mime_type not in {'image/jpeg', 'image/png'} or not allowed_file(logo_file.filename):
        flash('Gecersiz dosya!', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    # Logo dosyası her zaman static/uploads/site_logo.png olarak kaydedilir
    save_path = os.path.join(current_app.root_path, 'static', 'uploads', 'site_logo.png')

    try:
        with Image.open(logo_file) as img:
            img = img.convert("RGBA")
            img.thumbnail((200, 200))
            img.save(save_path, format="PNG", optimize=True)
    except Exception:
        flash('Resim isleme hatasi!', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    audit('logo_guncelle', 'Site logosu degistirildi')
    flash('Logo guncellendi!', 'success')
    return redirect(url_for('admin.admin_dashboard'))


# ── Dekont görüntüleme ─────────────────────────────────────────────

@admin_bp.route('/receipt/<filename>')
@login_required
def view_receipt(filename):
    """Rezervasyon dekontunu güvenli şekilde görüntüle."""
    safe_name = os.path.basename(filename)
    if not re.match(r'^[a-f0-9]{32}\.(pdf|jpg|jpeg|png)$', safe_name):
        logger.warning("Gecersiz receipt istegi: %s — IP: %s", safe_name, get_real_ip())
        return ("Gecersiz dosya adi.", 400)
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        safe_name,
        as_attachment=False
    )


# ── PDF rapor üretimi ─────────────────────────────────────────────

@admin_bp.route('/report/pdf', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def generate_report_pdf():
    """Seçili tarih ve saha için günlük PDF rapor üret."""
    date_str = request.form.get('report_date', '').strip()
    try:
        pitch_id = int(request.form.get('report_pitch_id', 0))
    except (ValueError, TypeError):
        flash('Gecersiz saha secimi!', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        flash('Gecersiz tarih formati!', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    try:
        report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Gecersiz tarih!', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    max_date = (datetime.now() + timedelta(days=31)).date()
    if report_date > max_date:
        flash('En fazla 1 ay ilerisine rapor olusturulabilir!', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    pitch = db.session.get(Pitch, pitch_id)
    if not pitch:
        flash('Saha bulunamadi!', 'danger')
        return redirect(url_for('admin.admin_dashboard'))

    # Müşteri tipi filtresi (boş/all = tüm tipler)
    ctype = None
    ctype_raw = request.form.get('report_ctype_id', 'all')
    if ctype_raw and ctype_raw != 'all':
        try:
            ctype = db.session.get(CustomerType, int(ctype_raw))
        except (ValueError, TypeError):
            ctype = None
        if ctype is None:
            flash('Gecersiz musteri tipi!', 'danger')
            return redirect(url_for('admin.admin_dashboard', tab='rapor'))

    # Veri çekme
    query = Reservation.query.filter_by(pitch_id=pitch_id, date=report_date)
    if ctype:
        query = query.filter_by(customer_type_id=ctype.id)
    reservations = query.order_by(Reservation.time_slot.asc()).all()

    blocked_slots = BlockedSlot.query.filter_by(
        pitch_id=pitch_id, date=report_date
    ).all()
    blocked_dict = {b.time_slot: b.reason for b in blocked_slots}

    # PDF üret
    customer_types = CustomerType.query.order_by(CustomerType.id).all()
    pdf_bytes = generate_report(pitch, report_date, reservations, blocked_dict,
                                customer_types=customer_types, ctype=ctype)

    # Audit log
    formatted_date = report_date.strftime('%d.%m.%Y')
    total    = len(reservations)
    approved = sum(1 for r in reservations if r.status == 'Approved')
    pending  = sum(1 for r in reservations if r.status == 'Pending')
    audit('rapor_indir',
          f'saha={pitch.name} | tarih={formatted_date} | '
          f'tip={ctype.name if ctype else "tümü"} | '
          f'rezervasyon={total} | onay={approved} | bekleyen={pending}')

    # Response
    safe_filename = f"rapor_{pitch.name.replace(' ', '_')}_{date_str}.pdf"
    safe_filename = re.sub(r'[^a-zA-Z0-9_\-.]', '', safe_filename)

    response = make_response(pdf_bytes)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename="{safe_filename}"'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


# ── Saha saat dilimi API (kilit formu için) ─────────────────────────

@admin_bp.route('/api/pitch/<int:pitch_id>/time_slots')
@login_required
def get_pitch_time_slots(pitch_id):
    """Sahaya ait saat dilimlerini JSON olarak döndür (AJAX için)."""
    pitch = db.session.get(Pitch, pitch_id)
    if not pitch:
        return jsonify({'slots': []})

    slots = PitchTimeSlot.query.filter_by(pitch_id=pitch_id)\
        .order_by(PitchTimeSlot.start_hour).all()

    return jsonify({
        'slots': [{'label': s.label, 'start_hour': s.start_hour} for s in slots]
    })
