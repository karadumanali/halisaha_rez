import os
import uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from models import db, Admin, Pitch, Reservation
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- KONFİGÜRASYONLAR ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Dosya Yükleme Güvenliği
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # Maksimum 5 MB
UPLOAD_FOLDER = 'static/uploads/receipts'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

db.init_app(app)

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
    if not file or not allowed_file(file.filename):
        return None
    original_filename = secure_filename(file.filename)
    ext = original_filename.rsplit('.', 1)[1].lower()
    safe_filename = f"{uuid.uuid4().hex}.{ext}" # Zararlı dosya ismini yok et, UUID ver
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
    file.save(save_path)
    return safe_filename

# ==========================================
#               WEB ROTALARI
# ==========================================

# 1. ANA SAYFA (Müşteri Ekranı)
@app.route('/')
def index():
    # Veritabanındaki tüm sahaları çekip ön yüze göndereceğiz
    pitches = Pitch.query.all()
    return render_template('index.html', pitches=pitches)

# 2. REZERVASYON YAPMA İŞLEMİ (Müşteri Formu Gönderdiğinde)
@app.route('/reserve', methods=['POST'])
def reserve():
    pitch_id = request.form.get('pitch_id')
    date_str = request.form.get('date') # Format: YYYY-MM-DD
    time_slot = request.form.get('time_slot')
    customer_name = request.form.get('customer_name')
    customer_phone = request.form.get('customer_phone')
    receipt_file = request.files.get('receipt')

    # a. Çakışma Kontrolü (Aynı saha, aynı tarih ve saate başka onaylı/bekleyen var mı?)
    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
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
    flash('Güvenli çıkış yapıldı.', 'info')
    return redirect(url_for('index'))

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
@app.route('/admin/status/<res_id>/<action>')
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





# 6. Halı Saha Silme Rotası
@app.route('/admin/delete_pitch/<int:pitch_id>')
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



# --- TARAYICI ÖNBELLEK KONTROLÜ (Güvenlik İçin) ---
@app.after_request
def add_header(response):
    """
    Tarayıcıya sayfaları önbelleğe almaması gerektiğini söyler.
    Böylece çıkış yaptıktan sonra geri tuşuna basıldığında sayfa tekrar yüklenmeye
    çalışılır ve @login_required engeline takılarak login sayfasına atılır.
    """
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# --- UYGULAMAYI BAŞLAT ---
if __name__ == '__main__':
    app.run(debug=True)