import os
import uuid
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

    # 1. Önce dosyanın ilk birkaç baytını okuyup gerçek türünü öğrenelim
    file_content = file.read(2048) # İlk 2048 baytı okumak yeterlidir
    file.seek(0) # Okuduktan sonra imleci tekrar başa sarıyoruz ki dosyayı diske eksiksiz kaydedebilelim

    # python-magic ile GERÇEK dosya türünü (MIME Type) bul
    mime_type = magic.from_buffer(file_content, mime=True)

    # İzin verdiğimiz GERÇEK dosya türleri (Siber güvenlik el kitabındaki "Whitelist" mantığı)
    ALLOWED_MIME_TYPES = {'application/pdf', 'image/jpeg', 'image/png'}

    # 2. Hem MIME türü beyaz listede mi, hem de uzantısı doğru mu kontrol et
    if mime_type not in ALLOWED_MIME_TYPES or not allowed_file(file.filename):
        return None # Sahte veya desteklenmeyen bir dosya, hemen reddet!

    # 3. Güvenli isim oluştur ve kaydet (Mevcut UUID mantığın burada devreye giriyor)
    original_filename = secure_filename(file.filename)
    ext = original_filename.rsplit('.', 1)[1].lower()
    safe_filename = f"{uuid.uuid4().hex}.{ext}" 
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
    file.save(save_path)
    
    return safe_filename

# ==========================================
#               WEB ROTALARI
# ==========================================

# 1. ANA SAYFA (Müşteri Ekranı)
@app.route('/')
def index():
    pitches = Pitch.query.all()
    # Sadece bugünün tarihini al ve saat farkı riskini ortadan kaldır
    today_date = datetime.now().date().isoformat() 
    return render_template('index.html', pitches=pitches, today_date=today_date)

# 2. REZERVASYON YAPMA İŞLEMİ (Müşteri Formu Gönderdiğinde)
@app.route('/reserve', methods=['POST'])
@limiter.limit("3 per minute") # Aynı IP'den dakikada en fazla 3 rezervasyon yapılabilir
def reserve():
    pitch_id = request.form.get('pitch_id')
    date_str = request.form.get('date') # Format: YYYY-MM-DD
    time_slot = request.form.get('time_slot')
    customer_name = request.form.get('customer_name')
    customer_phone = request.form.get('customer_phone')
    receipt_file = request.files.get('receipt')

    # a. Çakışma Kontrolü (Aynı saha, aynı tarih ve saate başka onaylı/bekleyen var mı?)
    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()

    #Geçmiş tarihe rezervasyon yapılmasını arkadan da engelle
    if date_obj < datetime.today().date():
        flash('Geçmiş bir tarihe rezervasyon yapamazsınız!', 'danger')
        return redirect(url_for('index'))
    
    existing_reservation = Reservation.query.filter_by(
        pitch_id=pitch_id, 
        date=date_obj, 
        time_slot=time_slot
    ).filter(Reservation.status.in_(['Pending', 'Approved'])).first()

    if existing_reservation:
        flash('Bu saat dilimi maalesef dolu veya onay bekliyor!', 'danger')
        return redirect(url_for('index'))

    # b. Dekontu Güvenle Kaydet
    saved_filename = save_secure_receipt(receipt_file)
    if not saved_filename:
        flash('Geçersiz dosya formatı veya dosya yüklenmedi!', 'danger')
        return redirect(url_for('index'))

    # c. Veritabanına Yaz (Durum varsayılan olarak 'Pending' olur)
    new_res = Reservation(
        pitch_id=pitch_id,
        date=date_obj,
        time_slot=time_slot,
        customer_name=customer_name,
        customer_phone=customer_phone,
        receipt_filename=saved_filename
    )
    db.session.add(new_res)
    db.session.commit()

    flash('Rezervasyon talebiniz alındı! Yönetici onayından sonra kesinleşecektir.', 'success')
    return redirect(url_for('index'))



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
        flash('Rezervasyon ONAYLANDI. Artık o saat dilimi sistemde dolu görünecek.', 'success')
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


