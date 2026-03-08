import os
import smtplib
from email.message import EmailMessage
from PIL import Image
from urllib.parse import urlparse

base_dir = os.path.dirname(os.path.abspath(__file__))

if hasattr(os, 'add_dll_directory'):
    os.add_dll_directory(base_dir)

os.environ['PATH']  = base_dir + os.pathsep + os.environ['PATH']
os.environ['MAGIC'] = os.path.join(base_dir, 'magic.mgc')

import uuid
import re
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, Admin, Pitch, Reservation, BlockedSlot, LoginAttempt
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler
import magic

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
app.config['MAX_CONTENT_LENGTH']             = 5 * 1024 * 1024

# ── GÜVENLİK: Production ortamında DEBUG kesinlikle False ──
if os.getenv('FLASK_ENV') == 'production':
    app.config['DEBUG']   = False
    app.config['TESTING'] = False

UPLOAD_FOLDER       = 'static/uploads/receipts'
PITCH_IMAGES_FOLDER = 'static/uploads/pitches'
app.config['UPLOAD_FOLDER']       = UPLOAD_FOLDER
app.config['PITCH_IMAGES_FOLDER'] = PITCH_IMAGES_FOLDER
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

for folder in [UPLOAD_FOLDER, PITCH_IMAGES_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

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
    """Her ayın 1'inde gece 03:00'te çalışır.
    1 aydan eski LoginAttempt kayıtlarını siler."""
    with app.app_context():
        cutoff = datetime.utcnow() - timedelta(days=30)
        deleted = LoginAttempt.query.filter(
            LoginAttempt.attempted_at < cutoff
        ).delete()
        db.session.commit()
        print(f"[Scheduler] Aylık temizlik tamamlandı — {deleted} eski kayıt silindi. ({datetime.utcnow().isoformat()})")


scheduler = BackgroundScheduler(timezone="Europe/Istanbul")
scheduler.add_job(
    monthly_cleanup,
    trigger='cron',
    day=1,        # Her ayın 1'i
    hour=3,       # Gece 03:00
    minute=0,
    id='monthly_login_cleanup',
    replace_existing=True
)
scheduler.start()


# ─── BRUTE-FORCE KORUMA ────────────────────────────────────────────

LOCKOUT_ATTEMPTS = 5   # Bu kadar başarısız denemeden sonra kilitle
LOCKOUT_MINUTES  = 15  # Bu kadar dakika kilitli kal


def is_account_locked(username, ip):
    """Kullanıcı adı VEYA IP bazında kilitlenme kontrolü."""
    cutoff = datetime.utcnow() - timedelta(minutes=LOCKOUT_MINUTES)

    fails_by_username = LoginAttempt.query.filter(
        LoginAttempt.username    == username,
        LoginAttempt.attempted_at > cutoff,
        LoginAttempt.success     == False   # noqa: E712
    ).count()

    fails_by_ip = LoginAttempt.query.filter(
        LoginAttempt.ip_address   == ip,
        LoginAttempt.attempted_at  > cutoff,
        LoginAttempt.success      == False   # noqa: E712
    ).count()

    return fails_by_username >= LOCKOUT_ATTEMPTS or fails_by_ip >= LOCKOUT_ATTEMPTS


def record_attempt(username, ip, success):
    """Giriş denemesini veritabanına kaydet."""
    db.session.add(LoginAttempt(
        ip_address=ip,
        username=username,
        attempted_at=datetime.utcnow(),
        success=success
    ))
    db.session.commit()


# ─── GÜVENLİ YÖNLENDİRME ─────────────────────────────────────────

def safe_redirect(next_url, fallback):
    """Open Redirect koruması: sadece relative path kabul et.
    //evil.com gibi şemesiz harici URL'leri reddeder."""
    if next_url:
        parsed = urlparse(next_url)
        # netloc veya scheme varsa dışarıya açılan bir URL demektir → reddet
        if not parsed.netloc and not parsed.scheme and next_url.startswith('/'):
            return redirect(next_url)
    return redirect(fallback)


# ─── YARDIMCI FONKSİYONLAR ────────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_secure_receipt(file):
    if not file:
        return None
    file_content = file.read(2048); file.seek(0)
    mime_type = magic.from_buffer(file_content, mime=True)
    ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png'}
    ALLOWED_PDF = {'application/pdf'}
    if mime_type not in (ALLOWED_IMAGE_TYPES | ALLOWED_PDF) or not allowed_file(file.filename):
        return None
    ext = secure_filename(file.filename).rsplit('.', 1)[1].lower()
    safe_filename = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
    if mime_type in ALLOWED_IMAGE_TYPES:
        try:
            with Image.open(file) as img:
                if img.mode in ("RGBA", "P") and ext in ['jpg', 'jpeg']:
                    img = img.convert("RGB")
                elif img.mode != "RGB" and ext not in ['png']:
                    img = img.convert("RGB")
                img.thumbnail((1920, 1920))
                img.save(save_path, optimize=True, quality=85)
        except Exception:
            return None
    elif mime_type in ALLOWED_PDF:
        file.save(save_path)
    return safe_filename


def save_secure_pitch_image(file):
    if not file:
        return None
    file_content = file.read(2048); file.seek(0)
    mime_type = magic.from_buffer(file_content, mime=True)
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
    sender_email = os.getenv('MAIL_USERNAME')
    sender_password = os.getenv('MAIL_PASSWORD')
    admin_email = os.getenv('ADMIN_EMAIL')
    if not sender_email or not sender_password:
        return
    msg = EmailMessage()
    msg['Subject'] = 'Yeni Rezervasyon Talebi!'
    msg['From'] = sender_email
    msg['To'] = admin_email
    msg.set_content(f"Yeni rezervasyon:\n{customer_name}\n{date}\n{time_slot}")
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls(); s.login(sender_email, sender_password); s.send_message(msg)
    except Exception as e:
        print(f"Mail hatasi: {e}")


def send_customer_approval_email(customer_email, customer_name, pitch_name, date, time_slot):
    sender_email = os.getenv('MAIL_USERNAME')
    sender_password = os.getenv('MAIL_PASSWORD')
    if not sender_email or not sender_password:
        return
    msg = EmailMessage()
    msg['Subject'] = 'Rezervasyonunuz Onaylandi!'
    msg['From'] = sender_email
    msg['To'] = customer_email
    msg.set_content(f"Merhaba {customer_name},\n\nRezervasyon onaylandi.\nSaha: {pitch_name}\nTarih: {date.strftime('%d.%m.%Y')}\nSaat: {time_slot}")
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls(); s.login(sender_email, sender_password); s.send_message(msg)
    except Exception as e:
        print(f"Mail hatasi: {e}")


# ─── ROTALAR ─────────────────────────────────────────────────────

@app.route('/')
def index():
    pitches    = Pitch.query.all()
    today_date = datetime.now().date().isoformat()
    return render_template('index.html', pitches=pitches, today_date=today_date)


@app.route('/busy_slots')
def busy_slots():
    pitch_id = request.args.get('pitch_id')
    date_str  = request.args.get('date')
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


@app.route('/reserve', methods=['POST'])
@limiter.limit("3 per minute")
def reserve():
    pitch_id  = request.form.get('pitch_id')
    date_str  = request.form.get('date')
    time_slot = request.form.get('time_slot')
    customer_name = request.form.get('customer_name')

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
        username   = request.form.get('username', '').strip()
        password   = request.form.get('password', '')
        ip_address = request.remote_addr

        # ── DB tabanlı brute-force kontrolü (curl ile atlatılamaz) ──
        if is_account_locked(username, ip_address):
            flash(
                f'Çok fazla başarısız deneme. {LOCKOUT_MINUTES} dakika sonra tekrar deneyin.',
                'danger'
            )
            return render_template('login.html')

        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            record_attempt(username, ip_address, success=True)
            login_user(admin, remember=False)
            flash('Yonetici paneline hos geldiniz.', 'success')
            # ── GÜVENLİ YÖNLENDİRME: Open Redirect koruması ──
            return safe_redirect(request.args.get('next'), url_for('admin_dashboard'))
        else:
            record_attempt(username, ip_address, success=False)
            flash('Kullanici adi veya sifre hatali!', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash('Guvenli cikis yapildi.', 'info')
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
    file_content = logo_file.read(2048); logo_file.seek(0)
    mime_type = magic.from_buffer(file_content, mime=True)
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


@app.after_request
def anti_cache(response):
    if response.status_code == 200 and response.content_type and \
       response.content_type.startswith('text/html'):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"]  = "no-cache"
        response.headers["Expires"] = "0"
    return response


with app.app_context():
    db.create_all()
    print("✅ Veritabani tablolari kontrol edildi (Eksikler olusturuldu).")

    admin_var_mi = Admin.query.filter_by(username='yonetici').first()
    if not admin_var_mi:
        from werkzeug.security import generate_password_hash
        hashed_password = generate_password_hash("halisaha123", method='pbkdf2:sha256')
        yeni_admin = Admin(username='yonetici', password_hash=hashed_password)
        db.session.add(yeni_admin)
        db.session.commit()
        print("👑 Ilk yonetici hesabi basariyla eklendi!")
    else:
        print("⚡ Yonetici zaten mevcut, yeni admin olusturulmadi.")


if __name__ == '__main__':
    is_debug = os.getenv('FLASK_DEBUG', 'False').lower() in ['true', '1', 't']
    if os.getenv('FLASK_ENV') == 'production':
        is_debug = False
    app.run(debug=is_debug)