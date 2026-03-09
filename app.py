import os
import smtplib
from email.message import EmailMessage
from PIL import Image
from urllib.parse import urlparse

base_dir = os.path.dirname(os.path.abspath(__file__))

if hasattr(os, 'add_dll_directory'):
    os.add_dll_directory(base_dir)

os.environ['PATH'] = base_dir + os.pathsep + os.environ['PATH']
# python-magic artık kullanılmıyor — saf Python ile MIME tespiti yapılıyor

import logging
import requests as http_requests

logger = logging.getLogger(__name__)

import uuid
import re
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, Admin, Pitch, Reservation, BlockedSlot, LoginAttempt
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler

# .env yükle
dotenv_path = os.path.join(base_dir, '.env')
load_dotenv(dotenv_path)

app = Flask(__name__)

# ── GÜVENLİK: SECRET_KEY zorunludur, fallback/hardcoded değer YOK ──
_secret = os.getenv('SECRET_KEY')
if not _secret:
    raise RuntimeError(
        "SECRET_KEY ortam değişkeni ZORUNLUDUR! "
        ".env dosyanızı kontrol edin. "
        "Üretmek için: python3 -c \"import secrets; print(secrets.token_hex(32))\""
    )

app.config['SECRET_KEY']                     = _secret
app.config['SQLALCHEMY_DATABASE_URI']        = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_PERMANENT']              = False
app.config['SESSION_COOKIE_HTTPONLY']        = True
app.config['SESSION_COOKIE_SAMESITE']        = 'Lax'
app.config['SESSION_COOKIE_SECURE']          = os.getenv('FLASK_ENV') == 'production'
app.config['MAX_CONTENT_LENGTH']             = 5 * 1024 * 1024

# ── GÜVENLİK: Production ortamında DEBUG kesinlikle False ──
if os.getenv('FLASK_ENV') == 'production':
    app.config['DEBUG']   = False
    app.config['TESTING'] = False

UPLOAD_FOLDER       = os.path.join(base_dir, 'static', 'uploads', 'receipts')
PITCH_IMAGES_FOLDER = os.path.join(base_dir, 'static', 'uploads', 'pitches')
app.config['UPLOAD_FOLDER']       = UPLOAD_FOLDER
app.config['PITCH_IMAGES_FOLDER'] = PITCH_IMAGES_FOLDER
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

for folder in [UPLOAD_FOLDER, PITCH_IMAGES_FOLDER]:
    os.makedirs(folder, exist_ok=True)

db.init_app(app)
csrf = CSRFProtect(app)

# ── GÜVENLİK: Rate limiter — Redis varsa kullan, yoksa memory ──
_redis_url = os.getenv('REDIS_URL', 'memory://')
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=_redis_url,
    default_limits=["500 per day", "100 per hour"]
)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view             = 'admin_login'
login_manager.login_message          = 'Bu sayfaya erisim icin giris yapmaniz gerekiyor.'
login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))


# ─── AYLIK OTOMATİK TEMİZLİK (APScheduler) ───────────────────────

def monthly_cleanup():
    with app.app_context():
        cutoff = datetime.utcnow() - timedelta(days=30)
        deleted = LoginAttempt.query.filter(
            LoginAttempt.attempted_at < cutoff
        ).delete()
        db.session.commit()
        logger.info(f"Aylık temizlik: {deleted} eski kayıt silindi.")


scheduler = BackgroundScheduler(timezone="Europe/Istanbul")
scheduler.add_job(
    monthly_cleanup,
    trigger='cron',
    day=1, hour=3, minute=0,
    id='monthly_login_cleanup',
    replace_existing=True
)
scheduler.start()


# ─── BRUTE-FORCE KORUMA ────────────────────────────────────────────

LOCKOUT_ATTEMPTS = 5
LOCKOUT_MINUTES  = 15


def is_account_locked(username, ip):
    cutoff = datetime.utcnow() - timedelta(minutes=LOCKOUT_MINUTES)
    fails_by_username = LoginAttempt.query.filter(
        LoginAttempt.username     == username,
        LoginAttempt.attempted_at  > cutoff,
        LoginAttempt.success      == False  # noqa: E712
    ).count()
    fails_by_ip = LoginAttempt.query.filter(
        LoginAttempt.ip_address   == ip,
        LoginAttempt.attempted_at  > cutoff,
        LoginAttempt.success      == False  # noqa: E712
    ).count()
    return fails_by_username >= LOCKOUT_ATTEMPTS or fails_by_ip >= LOCKOUT_ATTEMPTS


def record_attempt(username, ip, success):
    db.session.add(LoginAttempt(
        ip_address=ip, username=username,
        attempted_at=datetime.utcnow(), success=success
    ))
    db.session.commit()


# ─── GÜVENLİ YÖNLENDİRME ─────────────────────────────────────────

def safe_redirect(next_url, fallback):
    if next_url:
        parsed = urlparse(next_url)
        if not parsed.netloc and not parsed.scheme and next_url.startswith('/'):
            return redirect(next_url)
    return redirect(fallback)


# ─── IP KISITLAMA (Kampüs / İzinli IP'ler) ───────────────────────

def _load_allowed_ips() -> list:
    """
    .env'deki ALLOWED_ADMIN_IPS değişkenini okur.
    Birden fazla IP virgülle ayrılır:
        ALLOWED_ADMIN_IPS=193.140.x.x,10.0.0.1,127.0.0.1
    Boşsa kısıtlama KAPALI (geliştirme kolaylığı).
    """
    raw = os.getenv('ALLOWED_ADMIN_IPS', '')
    return [ip.strip() for ip in raw.split(',') if ip.strip()]


def get_real_ip() -> str:
    """
    Proxy/load-balancer arkasında gerçek IP'yi döner.
    X-Forwarded-For başlığı varsa ilk IP'yi alır.
    """
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or ''


def is_ip_allowed(ip: str, allowed: list) -> bool:
    """
    Tam IP eşleşmesi VEYA CIDR blok kontrolü.
    Örnek: 193.140.0.0/16 tüm kampüs bloğunu kapsar.
    """
    import ipaddress
    if not allowed:
        return True   # Liste boşsa herkese açık (geliştirme modu)
    try:
        client = ipaddress.ip_address(ip)
        for entry in allowed:
            try:
                if '/' in entry:
                    if client in ipaddress.ip_network(entry, strict=False):
                        return True
                else:
                    if client == ipaddress.ip_address(entry):
                        return True
            except ValueError:
                continue
    except ValueError:
        pass
    return False


@app.before_request
def restrict_admin_by_ip():
    """
    /login ve /admin/* path'lerine sadece izinli IP'lerden erişim.
    ALLOWED_ADMIN_IPS boşsa kısıtlama devrede değil.
    """
    allowed_ips = _load_allowed_ips()
    if not allowed_ips:
        return   # Kısıtlama kapalı

    admin_paths = ('/login', '/admin')
    if not any(request.path.startswith(p) for p in admin_paths):
        return   # Admin dışı sayfalara dokunma

    client_ip = get_real_ip()
    if not is_ip_allowed(client_ip, allowed_ips):
        logger.warning(
            f"Engellendi — yetkisiz IP: {client_ip} → {request.path}"
        )
        return (
            "<h2>Erişim Engellendi</h2>"
            "<p>Bu sayfaya yalnızca yetkili ağdan erişilebilir.</p>",
            403
        )


# ─── reCAPTCHA v3 DOĞRULAMA ──────────────────────────────────────

RECAPTCHA_SECRET    = os.getenv('RECAPTCHA_SECRET_KEY', '')
RECAPTCHA_SITE      = os.getenv('RECAPTCHA_SITE_KEY', '')
RECAPTCHA_MIN_SCORE = 0.5

def verify_recaptcha(token, action='submit'):
    if not RECAPTCHA_SECRET:
        return True
    if not token:
        return False
    try:
        resp = http_requests.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data={'secret': RECAPTCHA_SECRET, 'response': token},
            timeout=5
        )
        data = resp.json()
        return (
            data.get('success') is True
            and data.get('score', 0) >= RECAPTCHA_MIN_SCORE
            and data.get('action', '') == action
        )
    except Exception:
        logger.warning("reCAPTCHA doğrulama isteği başarısız.")
        return True


# ─── MIME TESPİTİ (saf Python — DLL/libmagic gerektirmez) ────────

_MAGIC_BYTES = {
    b'\xff\xd8\xff':       'image/jpeg',
    b'\x89PNG\r\n\x1a\n': 'image/png',
    b'%PDF':               'application/pdf',
}

def detect_mime(file_bytes: bytes) -> str:
    for sig, mime in _MAGIC_BYTES.items():
        if file_bytes.startswith(sig):
            return mime
    return ''


# ─── YARDIMCI FONKSİYONLAR ────────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_secure_receipt(file):
    if not file or not file.filename:
        return None
    file_content = file.read(2048)
    file.seek(0)
    mime_type = detect_mime(file_content)
    if not mime_type:
        logger.warning("MIME tespit edilemedi, uzantıya göre devam ediliyor.")
        ext_guess = secure_filename(file.filename).rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        mime_map  = {'pdf': 'application/pdf', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png'}
        mime_type = mime_map.get(ext_guess, '')

    ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png'}
    ALLOWED_PDF         = {'application/pdf'}
    if mime_type not in (ALLOWED_IMAGE_TYPES | ALLOWED_PDF) or not allowed_file(file.filename):
        return None
    ext           = secure_filename(file.filename).rsplit('.', 1)[1].lower()
    safe_filename = f"{uuid.uuid4().hex}.{ext}"
    save_path     = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
    if mime_type in ALLOWED_IMAGE_TYPES:
        try:
            with Image.open(file) as img:
                if img.mode in ("RGBA", "P") and ext in ['jpg', 'jpeg']:
                    img = img.convert("RGB")
                elif img.mode != "RGB" and ext not in ['png']:
                    img = img.convert("RGB")
                img.thumbnail((1920, 1920))
                img.save(save_path, optimize=True, quality=85)
        except Exception as e:
            logger.warning(f"Resim işleme hatası: {e}")
            return None
    elif mime_type in ALLOWED_PDF:
        try:
            file.save(save_path)
        except Exception as e:
            logger.warning(f"PDF kaydetme hatası: {e}")
            return None
    return safe_filename


def save_secure_pitch_image(file):
    if not file:
        return None
    file_content = file.read(2048)
    file.seek(0)
    mime_type = detect_mime(file_content)
    ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png'}
    if mime_type not in ALLOWED_IMAGE_TYPES or not allowed_file(file.filename):
        return None
    ext = secure_filename(file.filename).rsplit('.', 1)[1].lower()
    safe_filename = f"pitch_{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(app.config['PITCH_IMAGES_FOLDER'], safe_filename)
    try:
        with Image.open(file) as img:
            if img.mode in ("RGBA", "P") and ext in ['jpg', 'jpeg']:
                img = img.convert("RGB")
            elif img.mode != "RGB" and ext not in ['png']:
                img = img.convert("RGB")
            img.thumbnail((1920, 1080))
            img.save(save_path, optimize=True, quality=85)
    except Exception:
        return None
    return safe_filename


def send_admin_notification(customer_name, date, time_slot):
    sender_email    = os.getenv('MAIL_USERNAME')
    sender_password = os.getenv('MAIL_PASSWORD')
    admin_email     = os.getenv('ADMIN_EMAIL')
    if not sender_email or not sender_password:
        return
    msg = EmailMessage()
    msg['Subject'] = 'Yeni Rezervasyon Talebi!'
    msg['From']    = sender_email
    msg['To']      = admin_email
    msg.set_content(f"Yeni rezervasyon:\n{customer_name}\n{date}\n{time_slot}")
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls(); s.login(sender_email, sender_password); s.send_message(msg)
    except Exception as e:
        logger.warning(f"Mail hatasi: {e}")


def send_customer_approval_email(customer_email, customer_name, pitch_name, date, time_slot):
    sender_email    = os.getenv('MAIL_USERNAME')
    sender_password = os.getenv('MAIL_PASSWORD')
    if not sender_email or not sender_password:
        return
    msg = EmailMessage()
    msg['Subject'] = 'Rezervasyonunuz Onaylandi!'
    msg['From']    = sender_email
    msg['To']      = customer_email
    msg.set_content(f"Merhaba {customer_name},\n\nRezervasyon onaylandi.\nSaha: {pitch_name}\nTarih: {date.strftime('%d.%m.%Y')}\nSaat: {time_slot}")
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls(); s.login(sender_email, sender_password); s.send_message(msg)
    except Exception as e:
        logger.warning(f"Mail hatasi: {e}")


# ─── SABİTLER ────────────────────────────────────────────────────

VALID_SLOTS = [
    '16:00 - 17:00', '17:00 - 18:00', '18:00 - 19:00',
    '19:00 - 20:00', '20:00 - 21:00', '21:00 - 22:00', '22:00 - 23:00'
]

# ─── ROTALAR ─────────────────────────────────────────────────────

@app.route('/')
def index():
    pitches    = Pitch.query.all()
    today_date = datetime.now().date().isoformat()
    return render_template('index.html', pitches=pitches, today_date=today_date,
                           recaptcha_site_key=RECAPTCHA_SITE)


@app.route('/busy_slots')
def busy_slots():
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
    busy_dict    = {r.time_slot: r.status for r in busy_records}

    blocked      = BlockedSlot.query.filter_by(pitch_id=pitch_id, date=date_obj).all()
    blocked_dict = {b.time_slot: b.reason for b in blocked}

    return jsonify({'busy': busy_dict, 'blocked': blocked_dict})


@app.route('/reserve', methods=['POST'])
@limiter.limit("3 per minute")
def reserve():
    # ── 1. Honeypot: bot tespiti ──
    if request.form.get('website', ''):
        logger.warning(f"Honeypot tetiklendi — IP: {request.remote_addr}")
        flash('Rezervasyon talebiniz alindi! Yonetici onayindan sonra kesinlesecektir.', 'success')
        return redirect(url_for('index'))

    # ── 2. reCAPTCHA v3 kontrolü ──
    if not verify_recaptcha(request.form.get('g-recaptcha-response', ''), action='reserve'):
        flash('Bot doğrulaması başarısız. Lütfen tekrar deneyin.', 'danger')
        return redirect(url_for('index'))

    pitch_id      = request.form.get('pitch_id')
    date_str      = request.form.get('date')
    time_slot     = request.form.get('time_slot')
    customer_name = request.form.get('customer_name', '').strip()

    # ── Saat dilimi whitelist kontrolü ──
    if time_slot not in VALID_SLOTS:
        flash('Gecersiz saat dilimi!', 'danger')
        return redirect(url_for('index'))

    # ── pitch_id integer kontrolü ──
    try:
        pitch_id = int(pitch_id)
    except (ValueError, TypeError):
        flash('Gecersiz saha!', 'danger')
        return redirect(url_for('index'))

    # ── customer_name uzunluk kontrolü ──
    if not customer_name or len(customer_name) < 2 or len(customer_name) > 100:
        flash('Gecersiz isim! En az 2, en fazla 100 karakter olmalıdır.', 'danger')
        return redirect(url_for('index'))

    raw_phone   = request.form.get('customer_phone', '')
    clean_phone = raw_phone.replace(" ", "")
    if not re.match(r"^05\d{9}$", clean_phone):
        flash('Gecersiz telefon! 05XX XXX XX XX formatinda 11 haneli girin.', 'danger')
        return redirect(url_for('index'))

    customer_email = request.form.get('customer_email', '').strip()
    if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", customer_email):
        flash('Gecersiz e-posta!', 'danger')
        return redirect(url_for('index'))

    try:
        date_obj     = datetime.strptime(date_str, '%Y-%m-%d').date()
        current_date = datetime.now().date()
        current_time = datetime.now().time()
        if date_obj < current_date:
            flash('Gecmis bir tarihe rezervasyon yapilamaz!', 'danger')
            return redirect(url_for('index'))
        if date_obj == current_date:
            start_time_str = time_slot.split(' - ')[0].strip()
            if datetime.strptime(start_time_str, '%H:%M').time() <= current_time:
                flash('Sectiginiz saat dilimi gecmistir!', 'danger')
                return redirect(url_for('index'))
    except (ValueError, IndexError, AttributeError):
        flash('Gecersiz tarih veya saat!', 'danger')
        return redirect(url_for('index'))

    blocked = BlockedSlot.query.filter_by(
        pitch_id=pitch_id, date=date_obj, time_slot=time_slot
    ).first()
    if blocked:
        flash(f'Bu saat dilimi kilitli: {blocked.reason}', 'danger')
        return redirect(url_for('index'))

    existing = Reservation.query.filter_by(
        pitch_id=pitch_id, date=date_obj, time_slot=time_slot
    ).filter(Reservation.status.in_(['Pending', 'Approved'])).first()
    if existing:
        flash('Bu saat dilimi dolu veya onay bekliyor!', 'danger')
        return redirect(url_for('index'))

    saved_filename = save_secure_receipt(request.files.get('receipt'))
    if not saved_filename:
        flash('Gecersiz dosya! PDF, JPG veya PNG yukleyin.', 'danger')
        return redirect(url_for('index'))

    new_res = Reservation(
        pitch_id=pitch_id, date=date_obj, time_slot=time_slot,
        customer_name=customer_name, customer_phone=clean_phone,
        customer_email=customer_email, receipt_filename=saved_filename
    )
    db.session.add(new_res)
    db.session.commit()
    send_admin_notification(customer_name, date_obj, time_slot)
    flash('Rezervasyon talebiniz alindi! Yonetici onayindan sonra kesinlesecektir.', 'success')
    return redirect(url_for('index'))


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("3 per minute, 10 per hour, 20 per day")
def admin_login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        # ── reCAPTCHA v3 kontrolü ──
        if not verify_recaptcha(request.form.get('g-recaptcha-response', ''), action='login'):
            flash('Bot doğrulaması başarısız. Lütfen tekrar deneyin.', 'danger')
            return render_template('login.html', recaptcha_site_key=RECAPTCHA_SITE)

        username   = request.form.get('username', '').strip()
        password   = request.form.get('password', '')
        ip_address = request.remote_addr

        if is_account_locked(username, ip_address):
            flash(
                f'Çok fazla başarısız deneme. {LOCKOUT_MINUTES} dakika sonra tekrar deneyin.',
                'danger'
            )
            return render_template('login.html', recaptcha_site_key=RECAPTCHA_SITE)

        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            record_attempt(username, ip_address, success=True)
            login_user(admin, remember=False)
            
            return safe_redirect(request.args.get('next'), url_for('admin_dashboard'))
        else:
            record_attempt(username, ip_address, success=False)
            flash('Kullanici adi veya sifre hatali!', 'danger')

    return render_template('login.html', recaptcha_site_key=RECAPTCHA_SITE)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash('Guvenli cikis yapildi.', 'info')
    return redirect(url_for('admin_login'))


@app.route('/admin/change_password', methods=['POST'])
@login_required
def change_password():
    current_pw = request.form.get('current_password', '')
    new_pw     = request.form.get('new_password', '')
    confirm_pw = request.form.get('confirm_password', '')

    if not check_password_hash(current_user.password_hash, current_pw):
        flash('Mevcut şifreniz yanlış!', 'danger')
        return redirect(url_for('admin_dashboard'))

    if len(new_pw) < 8:
        flash('Yeni şifre en az 8 karakter olmalıdır!', 'danger')
        return redirect(url_for('admin_dashboard'))

    if new_pw != confirm_pw:
        flash('Yeni şifreler eşleşmiyor!', 'danger')
        return redirect(url_for('admin_dashboard'))

    if current_pw == new_pw:
        flash('Yeni şifre mevcut şifreden farklı olmalıdır!', 'danger')
        return redirect(url_for('admin_dashboard'))

    from werkzeug.security import generate_password_hash
    current_user.password_hash = generate_password_hash(new_pw, method='pbkdf2:sha256')
    db.session.commit()

    logout_user()
    session.clear()
    flash('Şifreniz başarıyla değiştirildi. Lütfen yeni şifrenizle giriş yapın.', 'success')
    return redirect(url_for('admin_login'))


@app.route('/admin')
@login_required
def admin_dashboard():
    pitches       = Pitch.query.all()
    reservations  = Reservation.query.order_by(Reservation.created_at.desc()).all()
    blocked_slots = BlockedSlot.query.order_by(BlockedSlot.date.asc(), BlockedSlot.time_slot.asc()).all()
    return render_template('admin.html',
                           pitches=pitches,
                           reservations=reservations,
                           blocked_slots=blocked_slots,
                           now=datetime.now())


# ─── KİLİT ROUTE'LARI ─────────────────────────────────────────────

@app.route('/admin/block_slot', methods=['POST'])
@login_required
def block_slot():
    pitch_ids  = request.form.getlist('pitch_ids')
    dates      = request.form.getlist('dates')
    time_slots = request.form.getlist('time_slots')
    reason     = request.form.get('reason', 'Bakim / Rezerve').strip()[:200]

    if not pitch_ids or not dates or not time_slots:
        flash('Saha, tarih ve saat dilimi secmelisiniz!', 'danger')
        return redirect(url_for('admin_dashboard'))

    added = 0; skipped = 0
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
                    skipped += 1; continue
                db.session.add(BlockedSlot(
                    pitch_id=pitch_id, date=date_obj,
                    time_slot=time_slot, reason=reason
                ))
                added += 1

    db.session.commit()
    msg = f'{added} slot basariyla kilitlendi.'
    if skipped > 0:
        msg += f' ({skipped} slot zaten kilitliydi, atlandi.)'
    flash(msg, 'success' if added > 0 else 'warning')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/unblock_slot/<int:block_id>', methods=['POST'])
@login_required
def unblock_slot(block_id):
    block = BlockedSlot.query.get_or_404(block_id)
    db.session.delete(block)
    db.session.commit()
    flash('Slot kilidi kaldirildi.', 'success')
    return redirect(url_for('admin_dashboard'))


# ─── SAHA ROUTE'LARI ──────────────────────────────────────────────

@app.route('/admin/add_pitch', methods=['POST'])
@login_required
def add_pitch():
    name  = request.form.get('name', '').strip()
    price = request.form.get('price', '')
    if not name or not price.isdigit():
        flash('Gecersiz saha adi veya ucret!', 'danger')
        return redirect(url_for('admin_dashboard'))
    db.session.add(Pitch(name=name, price=int(price)))
    db.session.commit()
    flash(f'"{name}" basariyla eklendi!', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/update_pitch/<int:pitch_id>', methods=['POST'])
@login_required
def update_pitch(pitch_id):
    pitch     = Pitch.query.get_or_404(pitch_id)
    new_price = request.form.get('new_price', '')
    if new_price and new_price.isdigit():
        pitch.price = int(new_price)
        db.session.commit()
        flash(f'"{pitch.name}" fiyati guncellendi: {pitch.price} TL', 'success')
    else:
        flash('Gecersiz ucret!', 'danger')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete_pitch/<int:pitch_id>', methods=['POST'])
@login_required
def delete_pitch(pitch_id):
    pitch = Pitch.query.get_or_404(pitch_id)
    try:
        db.session.delete(pitch)
        db.session.commit()
        flash(f'"{pitch.name}" silindi.', 'success')
    except Exception:
        db.session.rollback()
        flash('Bu sahaya ait rezervasyonlar var! Once onlari silin.', 'danger')
    return redirect(url_for('admin_dashboard'))


# ─── REZERVASYON ROUTE'LARI ───────────────────────────────────────

@app.route('/admin/status/<res_id>/<action>', methods=['POST'])
@login_required
def change_status(res_id, action):
    reservation = Reservation.query.get_or_404(res_id)
    if action == 'approve':
        reservation.status = 'Approved'
        send_customer_approval_email(
            reservation.customer_email, reservation.customer_name,
            reservation.pitch.name, reservation.date, reservation.time_slot
        )
        flash('Rezervasyon ONAYLANDI.', 'success')
    elif action == 'reject':
        reservation.status = 'Rejected'
        flash('Rezervasyon REDDEDILDI.', 'danger')
    db.session.commit()
    return redirect(url_for('admin_dashboard'))


# ─── GÖRSEL ROUTE'LAR ────────────────────────────────────────────

@app.route('/admin/pitch/<int:pitch_id>/add_image', methods=['POST'])
@login_required
def add_pitch_image(pitch_id):
    pitch = Pitch.query.get_or_404(pitch_id)
    from models import PitchImage
    saved_filename = save_secure_pitch_image(request.files.get('image'))
    if not saved_filename:
        flash('Gecersiz resim!', 'danger')
        return redirect(url_for('admin_dashboard'))
    db.session.add(PitchImage(pitch_id=pitch_id, image_filename=saved_filename))
    db.session.commit()
    flash(f'"{pitch.name}" icin resim eklendi.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/update_logo', methods=['POST'])
@login_required
def update_logo():
    logo_file = request.files.get('logo')
    if not logo_file:
        flash('Lutfen bir resim secin.', 'danger')
        return redirect(url_for('admin_dashboard'))
    file_content = logo_file.read(2048)
    logo_file.seek(0)
    mime_type = detect_mime(file_content)
    if mime_type not in {'image/jpeg', 'image/png'} or not allowed_file(logo_file.filename):
        flash('Gecersiz dosya!', 'danger')
        return redirect(url_for('admin_dashboard'))
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], 'site_logo.png')
    try:
        with Image.open(logo_file) as img:
            img = img.convert("RGBA")
            img.thumbnail((200, 200))
            img.save(save_path, format="PNG", optimize=True)
    except Exception:
        flash('Resim isleme hatasi!', 'danger')
        return redirect(url_for('admin_dashboard'))
    flash('Logo guncellendi!', 'success')
    return redirect(url_for('admin_dashboard'))


# ─── DEKONT ERİŞİM KORUMASI ──────────────────────────────────────

@app.route('/admin/receipt/<filename>')
@login_required
def view_receipt(filename):
    safe_name = os.path.basename(filename)
    return send_from_directory(app.config['UPLOAD_FOLDER'], safe_name)


# ─── AFTER REQUEST: Cache + Güvenlik Header'ları ─────────────────

@app.after_request
def apply_security_headers(response):
    if response.status_code == 200 and response.content_type and \
       response.content_type.startswith('text/html'):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"]        = "no-cache"
        response.headers["Expires"]       = "0"

    response.headers['X-Frame-Options']        = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection']       = '1; mode=block'
    response.headers['Referrer-Policy']        = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy']     = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net https://www.google.com "
        "https://www.gstatic.com 'unsafe-inline'; "
        "style-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com "
        "https://fonts.googleapis.com 'unsafe-inline'; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-src https://www.google.com"
    )

    if not app.debug:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    response.headers.pop('Server', None)
    return response


with app.app_context():
    db.create_all()
    logger.info("Veritabani tablolari kontrol edildi.")

    admin_var_mi = Admin.query.filter_by(username='yonetici').first()
    if not admin_var_mi:
        from werkzeug.security import generate_password_hash
        hashed_password = generate_password_hash("halisaha123", method='pbkdf2:sha256')
        yeni_admin = Admin(username='yonetici', password_hash=hashed_password)
        db.session.add(yeni_admin)
        db.session.commit()
        logger.info("Ilk yonetici hesabi olusturuldu.")
    else:
        logger.info("Yonetici zaten mevcut.")


if __name__ == '__main__':
    is_debug = os.getenv('FLASK_DEBUG', 'False').lower() in ['true', '1', 't']
    if os.getenv('FLASK_ENV') == 'production':
        is_debug = False
    app.run(debug=is_debug, use_reloader=True)