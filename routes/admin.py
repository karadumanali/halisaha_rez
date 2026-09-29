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
    current_app
)
from flask_login import login_required, current_user
from sqlalchemy import func
from PIL import Image

from extensions import db, limiter
from models import (
    Pitch, PitchImage, Reservation, BlockedSlot,
    AuditLog
)
from utils.constants import VALID_SLOTS
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

    pitches = Pitch.query.all()

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
        reservations=reservations,
        pagination=pagination,
        status_counts=status_counts,
        total_count=total_count,
        filtered_count=filtered_count,
        blocked_slots=blocked_slots,
        audit_logs=audit_logs,
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

@admin_bp.route('/add_pitch', methods=['POST'])
@login_required
def add_pitch():
    """Yeni saha ekle."""
    name  = request.form.get('name', '').strip()
    price = request.form.get('price', '')
    if not name or not price.isdigit():
        flash('Gecersiz saha adi veya ucret!', 'danger')
        return redirect(url_for('admin.admin_dashboard'))
    if not re.match(r'^[a-zA-Z0-9\s\-çÇğĞıİöÖşŞüÜ]+$', name) or len(name) > 100:
        flash('Saha adi sadece harf, rakam, bosluk ve tire icerebilir!', 'danger')
        return redirect(url_for('admin.admin_dashboard'))
    db.session.add(Pitch(name=name, price=int(price)))
    db.session.commit()
    audit('saha_ekle', f'saha={name} | fiyat={price} TL/sa')
    flash(f'"{name}" basariyla eklendi!', 'success')
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/update_pitch/<int:pitch_id>', methods=['POST'])
@login_required
def update_pitch(pitch_id):
    """Saha fiyatını güncelle."""
    pitch     = db.get_or_404(Pitch, pitch_id)
    new_price = request.form.get('new_price', '')
    if new_price and new_price.isdigit():
        old_price   = pitch.price
        pitch.price = int(new_price)
        db.session.commit()
        audit('saha_fiyat_guncelle',
              f'saha={pitch.name} | eski={old_price} TL → yeni={new_price} TL')
        flash(f'"{pitch.name}" fiyati guncellendi: {pitch.price} TL', 'success')
    else:
        flash('Gecersiz ucret!', 'danger')
    return redirect(url_for('admin.admin_dashboard'))


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
    return redirect(url_for('admin.admin_dashboard'))


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

    # Veri çekme
    reservations = Reservation.query.filter_by(
        pitch_id=pitch_id, date=report_date
    ).order_by(Reservation.time_slot.asc()).all()

    blocked_slots = BlockedSlot.query.filter_by(
        pitch_id=pitch_id, date=report_date
    ).all()
    blocked_dict = {b.time_slot: b.reason for b in blocked_slots}

    # PDF üret
    pdf_bytes = generate_report(pitch, report_date, reservations, blocked_dict)

    # Audit log
    formatted_date = report_date.strftime('%d.%m.%Y')
    total    = len(reservations)
    approved = sum(1 for r in reservations if r.status == 'Approved')
    pending  = sum(1 for r in reservations if r.status == 'Pending')
    audit('rapor_indir',
          f'saha={pitch.name} | tarih={formatted_date} | '
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


