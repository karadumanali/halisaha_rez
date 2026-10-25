"""
email.py — E-posta gönderim servisi.

Gönderilen mailler:
  - Müşteriye: "Rezervasyon talebiniz alındı" (sorgulama koduyla) — rezervasyon anında.
    Onay / red / süre dolumu için müşteriye mail GÖNDERİLMEZ; kullanıcı durumu
    /rezervasyon-sorgula sayfasından sorgulama koduyla takip eder.
  - Yöneticiye: yeni rezervasyon talebi bildirimi (ADMIN_EMAIL).

SMTP sunucusu .env'den okunur (MAIL_SERVER, MAIL_PORT); boş bırakılırsa Gmail kullanılır.
MAIL_USERNAME / MAIL_PASSWORD boşsa mail gönderimi devre dışıdır, sistem çalışmaya devam eder.
Gönderim threading ile async yapılır, SMTP blocking DoS'u önlenir.
"""

import os
import smtplib
import logging
import threading
from email.message import EmailMessage
from email.headerregistry import Address

logger = logging.getLogger(__name__)

SENDER_NAME = 'AYBÜ SKS Spor Tesisleri'


def _smtp_settings():
    """(sunucu, port) — .env'de yoksa Gmail varsayılanı."""
    server = (os.getenv('MAIL_SERVER') or '').strip() or 'smtp.gmail.com'
    try:
        port = int((os.getenv('MAIL_PORT') or '').strip() or 587)
    except ValueError:
        port = 587
    return server, port


def _send_mail_async(msg: EmailMessage):
    """Mail gönderimini background thread'de çalıştır."""
    server, port    = _smtp_settings()
    sender_email    = os.getenv('MAIL_USERNAME')
    sender_password = os.getenv('MAIL_PASSWORD')
    try:
        if port == 465:   # doğrudan SSL kullanan sunucular
            with smtplib.SMTP_SSL(server, port, timeout=10) as s:
                s.login(sender_email, sender_password)
                s.send_message(msg)
        else:             # 587: STARTTLS
            with smtplib.SMTP(server, port, timeout=10) as s:
                s.starttls()
                s.login(sender_email, sender_password)
                s.send_message(msg)
    except Exception as e:
        logger.warning("Mail hatasi (%s:%s): %s", server, port, e)


def _is_mail_configured() -> bool:
    """Mail ayarlarının yapılıp yapılmadığını kontrol et."""
    return bool(os.getenv('MAIL_USERNAME')) and bool(os.getenv('MAIL_PASSWORD'))


def _sanitize_header(value: str) -> str:
    """Header injection önlemi — newline karakterlerini temizle."""
    return str(value).replace('\n', '').replace('\r', '')


def _new_message(to: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg['Subject'] = _sanitize_header(subject)
    msg['From']    = Address(display_name=SENDER_NAME,
                             addr_spec=os.getenv('MAIL_USERNAME', ''))
    msg['To']      = _sanitize_header(to)
    msg.set_content(body)
    return msg


def _send(msg: EmailMessage):
    threading.Thread(target=_send_mail_async, args=(msg,), daemon=True).start()


# ── Admin bildirim maili ────────────────────────────────────────────

def send_admin_notification(customer_name: str, date, time_slot: str):
    """Yeni rezervasyon geldiğinde admin'e bildirim maili gönder."""
    admin_email = os.getenv('ADMIN_EMAIL')
    if not _is_mail_configured() or not admin_email:
        return
    customer_name = _sanitize_header(customer_name)
    _send(_new_message(
        admin_email,
        'Yeni Rezervasyon Talebi!',
        f"Yeni rezervasyon:\n{customer_name}\n{date}\n{time_slot}"
    ))


# ── Müşteri "talep alındı" maili ───────────────────────────────────

def send_customer_received_email(customer_email: str, customer_name: str,
                                  tracking_code: str, pitch_name: str, date_str: str,
                                  time_slot: str, ctype_name: str, price, track_url: str):
    """Rezervasyon talebi kaydedilince müşteriye sorgulama kodunu içeren mail gönder."""
    if not _is_mail_configured():
        return
    customer_name = _sanitize_header(customer_name)
    price_line    = f"Ücret        : {price} TL\n" if price is not None else ''

    body = (
        f"Merhaba {customer_name},\n\n"
        f"Rezervasyon talebiniz alınmıştır. "
        f"Talebiniz yönetici onayından sonra kesinleşecektir.\n\n"
        f"Rezervasyon Sorgulama Kodunuz: {tracking_code}\n\n"
        f"Saha         : {pitch_name}\n"
        f"Tarih        : {date_str}\n"
        f"Saat         : {time_slot}\n"
        f"Müşteri tipi : {ctype_name}\n"
        f"{price_line}\n"
        f"Rezervasyonunuzun durumunu (onaylandı / reddedildi) sorgulama kodunuzla "
        f"aşağıdaki sayfadan takip edebilirsiniz:\n"
        f"{track_url}\n\n"
        f"Bu e-posta otomatik olarak gönderilmiştir, lütfen yanıtlamayınız.\n\n"
        f"{SENDER_NAME}"
    )
    _send(_new_message(
        customer_email,
        f'Rezervasyon Talebiniz Alındı - {tracking_code}',
        body
    ))
