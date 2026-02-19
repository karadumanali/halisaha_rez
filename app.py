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

# --- UYGULAMAYI BAŞLAT ---
if __name__ == '__main__':
    app.run(debug=True)