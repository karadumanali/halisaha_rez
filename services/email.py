"""
email.py — E-posta gönderim servisi.

Tüm mail fonksiyonları burada. Gönderim threading ile async yapılır,
SMTP blocking DoS'u önlenir.
"""

import os
import smtplib
import logging
import threading
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def _send_mail_async(msg: EmailMessage):
    """Mail gönderimini background thread'de çalıştır."""
    sender_email    = os.getenv('MAIL_USERNAME')
    sender_password = os.getenv('MAIL_PASSWORD')
    try:
        with smtplib.SMTP('smtp.gmail.com', 587, timeout=10) as s:
            s.starttls()
            s.login(sender_email, sender_password)
            s.send_message(msg)
    except Exception as e:
        logger.warning(f"Mail hatasi: {e}")


def _is_mail_configured() -> bool:
    """Mail ayarlarının yapılıp yapılmadığını kontrol et."""
    return bool(os.getenv('MAIL_USERNAME')) and bool(os.getenv('MAIL_PASSWORD'))


def _sanitize_header(value: str) -> str:
    """Header injection önlemi — newline karakterlerini temizle."""
    return value.replace('\n', '').replace('\r', '')


# ── Admin bildirim maili ────────────────────────────────────────────

def send_admin_notification(customer_name: str, date, time_slot: str):
    """Yeni rezervasyon geldiğinde admin'e bildirim maili gönder."""
    if not _is_mail_configured():
        return
    sender_email = os.getenv('MAIL_USERNAME')
    admin_email  = os.getenv('ADMIN_EMAIL')

    customer_name = _sanitize_header(customer_name)
    msg = EmailMessage()
    msg['Subject'] = 'Yeni Rezervasyon Talebi!'
    msg['From']    = sender_email
    msg['To']      = admin_email
    msg.set_content(f"Yeni rezervasyon:\n{customer_name}\n{date}\n{time_slot}")

    threading.Thread(target=_send_mail_async, args=(msg,), daemon=True).start()


# ── Müşteri onay maili ─────────────────────────────────────────────

def send_customer_approval_email(customer_email: str, customer_name: str,
                                  pitch_name: str, date, time_slot: str):
    """Rezervasyon onaylandığında müşteriye bilgilendirme maili gönder."""
    if not _is_mail_configured():
        return
    sender_email   = os.getenv('MAIL_USERNAME')
    customer_email = _sanitize_header(customer_email)
    customer_name  = _sanitize_header(customer_name)

    msg = EmailMessage()
    msg['Subject'] = 'Rezervasyonunuz Onaylandi!'
    msg['From']    = sender_email
    msg['To']      = customer_email
    msg.set_content(
        f"Merhaba {customer_name},\n\n"
        f"Rezervasyon onaylandi.\n"
        f"Saha: {pitch_name}\n"
        f"Tarih: {date.strftime('%d.%m.%Y')}\n"
        f"Saat: {time_slot}"
    )

    threading.Thread(target=_send_mail_async, args=(msg,), daemon=True).start()


# ── Müşteri süre dolum maili ───────────────────────────────────────

def send_customer_expiry_email(customer_email: str, customer_name: str,
                                pitch_name: str, date, time_slot: str):
    """Süresi dolan rezervasyon için müşteriye bilgilendirme maili gönder."""
    if not _is_mail_configured():
        return
    sender_email   = os.getenv('MAIL_USERNAME')
    customer_email = _sanitize_header(customer_email)
    customer_name  = _sanitize_header(customer_name)

    msg = EmailMessage()
    msg['Subject'] = 'Rezervasyon Talebiniz Zaman Asimina Ugradi'
    msg['From']    = sender_email
    msg['To']      = customer_email
    msg.set_content(
        f"Merhaba {customer_name},\n\n"
        f"Asagidaki rezervasyon talebiniz belirtilen tarihte onaylanmadigi icin "
        f"otomatik olarak kapatilmistir.\n\n"
        f"Saha: {pitch_name}\n"
        f"Tarih: {date.strftime('%d.%m.%Y')}\n"
        f"Saat: {time_slot}\n\n"
        f"Yeni bir rezervasyon talebi olusturabilirsiniz.\n\n"
        f"Iyi gunler dileriz.\n"
        f"AYBU SKS Spor Tesisleri"
    )

    threading.Thread(target=_send_mail_async, args=(msg,), daemon=True).start()
