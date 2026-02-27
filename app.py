import os
import smtplib
from email.message import EmailMessage
from PIL import Image
base_dir = os.path.dirname(os.path.abspath(__file__))

# Python 3.13'te Windows'un yanındaki DLL'leri okuyabilmesi için bu şart!
if hasattr(os, 'add_dll_directory'):
    os.add_dll_directory(base_dir)

# Sistemin DLL'leri ve magic.mgc veritabanını bulması için ortam değişkenlerini zorluyoruz
os.environ['PATH'] = base_dir + os.pathsep + os.environ['PATH']
os.environ['MAGIC'] = os.path.join(base_dir, 'magic.mgc')
import uuid
import re  # <--- BUNU EKLE (Düzenli ifadeler için) örneğin telefon numarasının formatı
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, Admin, Pitch, Reservation
from dotenv import load_dotenv

from flask_wtf.csrf import CSRFProtect


from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import magic  #zararli dosya engellemek icin

load_dotenv()

app = Flask(__name__)

# --- KONFİGÜRASYONLAR ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_PERMANENT'] = False #tarayici kapattiği an hesabi unut

# Dosya Yükleme Güvenliği
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # Maksimum 5 MB
UPLOAD_FOLDER = 'static/uploads/receipts'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

db.init_app(app)

csrf = CSRFProtect(app) #csrf icin

# ---RATE LIMITING ---
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri="memory://", # Sınırlandırma verilerini geçici bellekte tutar
    default_limits=["500 per day", "100 per hour"] # Tüm site için genel bir üst sınır
)

# Klasör yoksa oluştur
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- LOGIN MANAGER KURULUMU (Admin İçin) ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))

# --- GÜVENLİK YARDIMCI FONKSİYONLARI ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_secure_receipt(file):
    if not file:
        return None

    # 1. Önce dosyanın ilk birkaç baytını okuyup GERÇEK türünü öğrenelim
    file_content = file.read(2048) 
    file.seek(0) 

    # python-magic ile doğrulama
    mime_type = magic.from_buffer(file_content, mime=True)

    ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png'}
    ALLOWED_PDF = {'application/pdf'}

    # Eğer gelen dosya izin verilen listelerde değilse veya uzantısı sahteyse anında reddet!
    if mime_type not in (ALLOWED_IMAGE_TYPES | ALLOWED_PDF) or not allowed_file(file.filename):
        return None 

    # 2. Güvenli ve tahmin edilemez dosya adı oluşturma
    original_filename = secure_filename(file.filename)
    ext = original_filename.rsplit('.', 1)[1].lower()
    safe_filename = f"{uuid.uuid4().hex}.{ext}" 
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)

    # ==========================================
    # GÜVENLİK FİLTRESİ 1: GÖRÜNTÜ STERİLİZASYONU
    # ==========================================
    if mime_type in ALLOWED_IMAGE_TYPES:
        try:
            # Resmi arka planda açıyoruz
            with Image.open(file) as img:
                # A. Formatı standartlaştır (Gizli katmanları ve şeffaflık açıklarını kapatır)
                if img.mode in ("RGBA", "P") and ext in ['jpg', 'jpeg']:
                    img = img.convert("RGB")
                elif img.mode != "RGB" and ext not in ['png']:
                    img = img.convert("RGB")

                # B. Pixel Bomb Koruması (En-boy oranını bozmadan max 1920x1920 yapar)
                img.thumbnail((1920, 1920))

                # C. Kaydetme İşlemi (optimize=True ile EXIF silinir, resim yeniden çizilir)
                img.save(save_path, optimize=True, quality=85)
                
        except Exception as e:
            # Eğer resim bozuksa, açılamıyorsa veya pikselleri manipüle edilmişse kaydetmeyi reddet
            return None

    # ==========================================
    # GÜVENLİK FİLTRESİ 2: PDF İŞLEMİ
    # ==========================================
    elif mime_type in ALLOWED_PDF:
        # PDF'ler görüntü olmadığı için yeniden çizilemez. 
        # Ancak magic ile DNA'sını doğruladığımız ve 5MB sınırımız olduğu için güvenle kaydediyoruz.
        file.save(save_path)
    
    return safe_filename

# ==========================================
#               WEB ROTALARI
# ==========================================
# --- GÜVENLİ MAİL BİLDİRİM SİSTEMİ ---
def send_admin_notification(customer_name, date, time_slot):
    sender_email = os.getenv('MAIL_USERNAME')
    sender_password = os.getenv('MAIL_PASSWORD')
    admin_email = os.getenv('ADMIN_EMAIL')

    if not sender_email or not sender_password:
        return # Eğer .env ayarlanmamışsa sistem çökmesin, sessizce iptal etsin

    msg = EmailMessage()
    msg['Subject'] = '🔔 Yeni Rezervasyon Talebi Geldi!'
    msg['From'] = sender_email
    msg['To'] = admin_email
    
    # Düz metin (Plain text) kullanıyoruz ki HTML Injection zafiyeti oluşmasın
    msg.set_content(f"""
Merhaba Yönetici,

Sisteme yeni bir onay bekleyen rezervasyon düştü!

👤 Müşteri: {customer_name}
📅 Tarih: {date}
⏰ Saat: {time_slot}

Lütfen en kısa sürede yönetici paneline girerek dekontu kontrol edip onaylayın veya reddedin.

İyi çalışmalar!
(Bu otomatik bir güvenlik bilgilendirme mesajıdır)
    """)

    try:
        # GÜVENLİK: Bağlantıyı TLS ile şifreliyoruz (MitM saldırılarına karşı)
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls() 
            server.login(sender_email, sender_password)
            server.send_message(msg)
    except Exception as e:
        # Eğer internet koparsa veya Google maili engellerse, müşterinin rezervasyonu yarım kalmasın!
        # Hata yakalama (try-except) ile hatayı yutuyoruz.
        print(f"Mail gönderme hatası (Sistem çalışmaya devam ediyor): {e}")

# 1. ANA SAYFA (Müşteri Ekranı)
@app.route('/')
def index():
    pitches = Pitch.query.all()
    # Sadece bugünün tarihini al ve saat farkı riskini ortadan kaldır
    today_date = datetime.now().date().isoformat() 
    return render_template('index.html', pitches=pitches, today_date=today_date)

# 2. REZERVASYON YAPMA İŞLEMİ (Müşteri Formu Gönderdiğinde)
@app.route('/reserve', methods=['POST'])
@limiter.limit("3 per minute")
def reserve():
    pitch_id = request.form.get('pitch_id')
    date_str = request.form.get('date') # Format: YYYY-MM-DD
    time_slot = request.form.get('time_slot')
    customer_name = request.form.get('customer_name')
    
    # 1. GÜVENLİK: TELEFON NUMARASI TEMİZLEME VE FORMAT KONTROLÜ
    raw_phone = request.form.get('customer_phone', '')
    # Kullanıcının girdiği boşlukları temizle (Örn: "0555 555 55 55" -> "05555555555")
    clean_phone = raw_phone.replace(" ", "") 
    
    # Sadece 05 ile başlayan ve tam 11 haneli rakamları kabul eden katı Regex filtresi
    if not re.match(r"^05\d{9}$", clean_phone):
        flash('Güvenlik ihlali veya geçersiz format! Telefon numarası 05XX XXX XX XX formatında 11 haneli olmalıdır.', 'danger')
        return redirect(url_for('index'))
    # GÜVENLİK FİLTRESİ: Katı E-Posta Regex Kontrolü
    customer_email = request.form.get('customer_email', '').strip()
    email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(email_regex, customer_email):
        flash('Güvenlik ihlali: Geçersiz e-posta formatı!', 'danger')
        return redirect(url_for('index'))
    # ==========================================

    # 2. GÜVENLİK: ZAMAN MANİPÜLASYONU VE GEÇMİŞ SAAT KONTROLÜ
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        current_date = datetime.now().date()
        current_time = datetime.now().time()

        # a) Tarih geçmiş mi?
        if date_obj < current_date:
            flash('Geçmiş bir tarihe rezervasyon yapılamaz!', 'danger')
            return redirect(url_for('index'))

        # b) Tarih bugünse, saat geçmiş mi?
        if date_obj == current_date:
            # Gelen veriyi güvenle parçala (Örn: "18:00 - 19:00" -> "18:00")
            start_time_str = time_slot.split(' - ')[0].strip()
            start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()
            
            if start_time_obj <= current_time:
                flash('Seçtiğiniz saat dilimi geçmiştir, lütfen ileri bir saat seçiniz!', 'danger')
                return redirect(url_for('index'))
                
    except (ValueError, IndexError, AttributeError):
        # Eğer birisi Postman ile "time_slot" kısmına "hack_saati" gibi saçma bir veri yollarsa
        # sistemin 500 hatası verip çökmesini engelleriz.
        flash('Geçersiz tarih veya saat verisi tespit edildi!', 'danger')
        return redirect(url_for('index'))

    receipt_file = request.files.get('receipt')

    # c. Çakışma Kontrolü (Aynı saha, aynı tarih ve saate başka onaylı/bekleyen var mı?)
    existing_reservation = Reservation.query.filter_by(
        pitch_id=pitch_id, 
        date=date_obj, 
        time_slot=time_slot
    ).filter(Reservation.status.in_(['Pending', 'Approved'])).first()

    if existing_reservation:
        flash('Bu saat dilimi maalesef dolu veya onay bekliyor!', 'danger')
        return redirect(url_for('index'))

    # d. Dekontu Güvenle Kaydet
    saved_filename = save_secure_receipt(receipt_file)
    if not saved_filename:
        flash('Geçersiz dosya formatı veya dosya yüklenmedi!', 'danger')
        return redirect(url_for('index'))

    # e. Veritabanına Yaz 
    new_res = Reservation(
        pitch_id=pitch_id,
        date=date_obj,
        time_slot=time_slot,
        customer_name=customer_name,
        customer_phone=clean_phone, # Temizlenmiş ve onaylanmış numarayı kaydediyoruz
        customer_email=customer_email,
        receipt_filename=saved_filename
    )
    db.session.add(new_res)
    db.session.commit()
# YENİ EKLENEN SATIR: Veritabanına kayıt KESİNLEŞTİKTEN sonra mail at
    send_admin_notification(customer_name, date_obj, time_slot)
    flash('Rezervasyon talebiniz alındı! Yönetici onayından sonra kesinleşecektir.', 'success')
    return redirect(url_for('index'))
def send_customer_approval_email(customer_email, customer_name, pitch_name, date, time_slot):
    sender_email = os.getenv('MAIL_USERNAME')
    sender_password = os.getenv('MAIL_PASSWORD')

    if not sender_email or not sender_password:
        return

    msg = EmailMessage()
    msg['Subject'] = '✅ Halı Saha Rezervasyonunuz Onaylandı!'
    msg['From'] = sender_email
    msg['To'] = customer_email
    
    # Düz metin (Plain Text) kullanılarak HTML Injection zafiyeti engellendi
    msg.set_content(f"""
Merhaba {customer_name},

Harika bir haberimiz var! Rezervasyon talebiniz yöneticimiz tarafından onaylanmıştır.

🏟️ Saha: {pitch_name}
📅 Tarih: {date.strftime('%d.%m.%Y')}
⏰ Saat: {time_slot}

Ödemeniz alınmış ve sahanız adınıza ayırtılmıştır. Bizi tercih ettiğiniz için teşekkür ederiz. 
Maçta başarılar dileriz!

(Bu otomatik bir bilgilendirme mesajıdır, lütfen cevaplamayınız.)
    """)

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
    except Exception as e:
        print(f"Müşteriye mail gönderme hatası: {e}")


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute") # Brute-force şifre kırma saldırılarını engeller
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        admin = Admin.query.filter_by(username=username).first()
        
        # Güvenlik: Kullanıcı var mı ve şifre hash'i eşleşiyor mu?
        if admin and check_password_hash(admin.password_hash, password):
            login_user(admin)
            flash('Yönetici paneline hoş geldiniz.', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            # OSINT Önlemi: Kötü niyetli kişilere "Kullanıcı adı yanlış" veya "Şifre yanlış" 
            # diyerek bilgi sızdırmıyoruz. İkisini de reddediyoruz.
            flash('Kullanıcı adı veya şifre hatalı!', 'danger')
            
    return render_template('login.html')

# 2. Admin Çıkış İşlemi
@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear() # Tüm çerez izlerini sunucudan da sil
    flash('Güvenli çıkış yapıldı. Oturum tamamen kapatıldı.', 'info')
    return redirect(url_for('admin_login')) # Çıkış yapınca ana sayfaya değil, login'e atsın

# 3. Yönetici Paneli Ana Sayfası (Dekontları ve Sahaları Gördüğümüz Yer)
@app.route('/admin')
@login_required
def admin_dashboard():
    # Sistemdeki tüm sahaları çek
    pitches = Pitch.query.all()
    # Tüm rezervasyonları en yeniden en eskiye (created_at) göre sıralayarak çek
    reservations = Reservation.query.order_by(Reservation.created_at.desc()).all()
    
    return render_template('admin.html', pitches=pitches, reservations=reservations)

# 4. Yeni Halı Saha Ekleme Rotası
@app.route('/admin/add_pitch', methods=['POST'])
@login_required
def add_pitch():
    name = request.form.get('name')
    price = request.form.get('price')
    
    yeni_saha = Pitch(name=name, price=int(price))
    db.session.add(yeni_saha)
    db.session.commit()
    
    flash(f'"{name}" başarıyla sisteme eklendi!', 'success')
    return redirect(url_for('admin_dashboard'))

# 5. Rezervasyon Onaylama / Reddetme Rotası (Sistemin Yöneticisi Konuşuyor)
@app.route('/admin/status/<res_id>/<action>', methods=['POST'])
@login_required
def change_status(res_id, action):
    # UUID ile güvenli arama (IDOR korumalı)
    reservation = Reservation.query.get_or_404(res_id)
    
    if action == 'approve':
        reservation.status = 'Approved'
        # YENİ: Müşteriye onay maili at!
        send_customer_approval_email(
            reservation.customer_email, 
            reservation.customer_name, 
            reservation.pitch.name, 
            reservation.date, 
            reservation.time_slot
        )
        flash('Rezervasyon ONAYLANDI ve müşteriye e-posta ile bildirildi.', 'success')
        
    elif action == 'reject':
        reservation.status = 'Rejected'
        flash('Rezervasyon REDDEDİLDİ. O saat dilimi tekrar boşa çıktı.', 'danger')
        
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

# 7. Halı Saha Fiyat Güncelleme Rotası
@app.route('/admin/update_pitch/<int:pitch_id>', methods=['POST'])
@login_required
def update_pitch(pitch_id):
    pitch = Pitch.query.get_or_404(pitch_id)
    new_price = request.form.get('new_price')
    
    if new_price and new_price.isdigit():
        pitch.price = int(new_price)
        db.session.commit()
        flash(f'"{pitch.name}" sahasının ücreti {pitch.price} ₺ olarak güncellendi.', 'success')
    else:
        flash('Geçersiz bir ücret girdiniz.', 'danger')
        
    return redirect(url_for('admin_dashboard'))



# 6. Halı Saha Silme Rotası
@app.route('/admin/delete_pitch/<int:pitch_id>', methods=['POST'])
@login_required
def delete_pitch(pitch_id):
    pitch = Pitch.query.get_or_404(pitch_id)
    
    try:
        db.session.delete(pitch)
        db.session.commit()
        flash(f'"{pitch.name}" başarıyla silindi.', 'success')
    except Exception as e:
        # Eğer bu sahaya ait rezervasyonlar varsa veritabanı silmeye izin vermez (Bütünlük koruması)
        db.session.rollback()
        flash('Bu sahaya ait rezervasyonlar var! Önce o rezervasyonları temizlemelisiniz.', 'danger')
        
    return redirect(url_for('admin_dashboard'))


# --- GÜVENLİK: GERİ TUŞU ZAFİYETİ (DÜZELTİLDİ) ---
@app.after_request
def anti_cache(response):
    # Sadece HTML sayfalarında cache engelle ki login olurken çerezlerimiz silinmesin!
    if response.status_code == 200 and response.content_type and response.content_type.startswith('text/html'):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response



# --- UYGULAMAYI BAŞLAT ---
if __name__ == '__main__':
    # Debug modunu .env dosyasından güvenle alıyoruz. 
    # Eğer .env dosyasında belirtilmemişse varsayılan olarak False (Güvenli) kabul eder.
    is_debug = os.getenv('FLASK_DEBUG', 'False').lower() in ['true', '1', 't']
    
    # Canlı ortamda asla Flask'ın kendi sunucusu (app.run) tek başına kullanılmamalıdır,
    # ancak testler için debug modunu kontrollü hale getirdik.
    app.run(debug=is_debug)


