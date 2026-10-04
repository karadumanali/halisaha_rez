"""
scheduler.py — Zamanlanmış görevler (cron jobs).

APScheduler ile çalışan 3 otomatik iş:
  1. Aylık temizlik (login denemeleri + eski audit loglar)
  2. Süresi dolan rezervasyonları otomatik kapat
  3. Tarihi geçmiş slot kilitlerini temizle

Not: auto_expire_reservations ve auto_cleanup_blocked_slots
     hem cron ile hem de admin dashboard açılışında doğrudan çağrılır.
     Dashboard'dan çağrıldığında zaten request context var, bu yüzden
     try/except ile _app referansı üzerinden fallback yapılır.
"""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from extensions import db
from models import Reservation, BlockedSlot, LoginAttempt, AuditLog
from services.email import send_customer_expiry_email
from utils.timeutil import now_tr, today_tr

logger = logging.getLogger(__name__)

# Scheduler nesnesi — init_scheduler() ile başlatılır
scheduler = BackgroundScheduler(timezone="Europe/Istanbul")

# Flask app referansı — init_scheduler() tarafından set edilir
_app = None


def monthly_cleanup():
    """
    Her ayın 1'inde gece 03:00'te çalışır.
    30 günden eski login denemelerini ve 2 yıldan eski audit kayıtlarını siler.
    """
    with _app.app_context():
        login_cutoff  = now_tr() - timedelta(days=30)
        deleted_login = LoginAttempt.query.filter(
            LoginAttempt.attempted_at < login_cutoff
        ).delete()

        audit_cutoff  = now_tr() - timedelta(days=730)
        deleted_audit = AuditLog.query.filter(
            AuditLog.created_at < audit_cutoff
        ).delete()

        db.session.commit()
        logger.info(
            f"Aylik temizlik tamamlandi: "
            f"{deleted_login} login denemesi, "
            f"{deleted_audit} denetim kaydi silindi."
        )


def auto_expire_reservations():
    """
    Her saat başı (:05) çalışır + admin paneli her açıldığında tetiklenir.
    Tarihi geçmiş 'Pending' rezervasyonları 'Expired' olarak işaretler.

    Dashboard'dan çağrıldığında zaten request context içinde olduğundan
    doğrudan çalışır. Cron'dan çağrıldığında _app.app_context() kullanır.
    """
    from flask import has_app_context

    def _run():
        now   = now_tr()
        today = now.date()
        current_time = now.time()

        # Tarihi tamamen geçmiş
        expired_past_date = Reservation.query.filter(
            Reservation.status == 'Pending',
            Reservation.date < today
        ).all()

        # Bugüne ait ama saati geçmiş
        expired_past_time = []
        today_pending = Reservation.query.filter(
            Reservation.status == 'Pending',
            Reservation.date == today
        ).all()

        for res in today_pending:
            try:
                end_time_str = res.time_slot.split(' - ')[1].strip()
                end_time = datetime.strptime(end_time_str, '%H:%M').time()
                if end_time <= current_time:
                    expired_past_time.append(res)
            except (IndexError, ValueError):
                continue

        all_expired = expired_past_date + expired_past_time
        count = 0

        for res in all_expired:
            res.status = 'Expired'
            count += 1
            send_customer_expiry_email(
                res.customer_email,
                res.customer_name,
                res.pitch.name if res.pitch else 'Bilinmeyen Saha',
                res.date,
                res.time_slot
            )

        if count > 0:
            db.session.add(AuditLog(
                admin='sistem',
                ip_address='127.0.0.1',
                action='otomatik_suresi_doldu',
                detail=f'{count} adet bekleyen rezervasyonun suresi doldu — otomatik kapatildi.'
            ))
            db.session.commit()
            logger.info(f"Otomatik sure dolumu: {count} rezervasyon 'Expired' olarak isaretlendi.")

    if has_app_context():
        _run()
    else:
        with _app.app_context():
            _run()


def auto_cleanup_blocked_slots():
    """
    Her saat başı (:05) çalışır + admin paneli her açıldığında tetiklenir.
    Tarihi geçmiş slot kilitlerini otomatik kaldırır.
    """
    from flask import has_app_context

    def _run():
        today = today_tr()
        expired_blocks = BlockedSlot.query.filter(BlockedSlot.date < today).all()
        count = len(expired_blocks)

        for block in expired_blocks:
            db.session.delete(block)

        if count > 0:
            db.session.add(AuditLog(
                admin='sistem',
                ip_address='127.0.0.1',
                action='otomatik_kilit_temizlik',
                detail=f'{count} adet tarihi gecmis slot kilidi otomatik kaldirildi.'
            ))
            db.session.commit()
            logger.info(f"Otomatik temizlik: {count} tarihi gecmis slot kilidi kaldirildi.")

    if has_app_context():
        _run()
    else:
        with _app.app_context():
            _run()


def init_scheduler(app):
    """Scheduler'ı yapılandır ve başlat."""
    global _app
    _app = app

    scheduler.add_job(
        monthly_cleanup,
        trigger='cron',
        day=1, hour=3, minute=0,
        id='monthly_login_cleanup',
        replace_existing=True
    )
    scheduler.add_job(
        auto_expire_reservations,
        trigger='cron',
        hour='*', minute=5,
        id='auto_expire_reservations',
        replace_existing=True
    )
    scheduler.add_job(
        auto_cleanup_blocked_slots,
        trigger='cron',
        hour='*', minute=5,
        id='auto_cleanup_blocked_slots',
        replace_existing=True
    )
    scheduler.start()
    logger.info("APScheduler baslatildi: 3 zamanlayici gorevi aktif.")
