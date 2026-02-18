import os
import uuid
from flask import Flask
from werkzeug.utils import secure_filename
from models import db, Admin, Pitch, Reservation
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- GÜVENLİK VE VERİTABANI KONFİGÜRASYONLARI ---
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'gelistirme-icin-gecici-anahtar')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://localhost/halisaha')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- DOSYA YÜKLEME GÜVENLİĞİ (Anti-DoS ve Anti-RCE) ---
# 1. Boyut Sınırı: Maksimum 5 MB. (Sunucu diskini doldurma saldırılarına karşı)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  

UPLOAD_FOLDER = 'static/uploads/receipts'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 2. Whitelist (Beyaz Liste) Yaklaşımı: Sadece bu uzantılara izin veriyoruz.
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

db.init_app(app)

# Yükleme klasörü yoksa otomatik oluştur
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- GÜVENLİK YARDIMCI FONKSİYONLARI ---

def allowed_file(filename):
    """Dosya uzantısının beyaz listede olup olmadığını kontrol eder."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_secure_receipt(file):
    """
    Kullanıcıdan gelen dosyayı RCE ve Path Traversal zafiyetlerinden 
    arındırarak sunucuya kaydeder.
    """
    if not file or not allowed_file(file.filename):
        return None
        
    # Aşama 1: Dosya adındaki tehlikeli karakterleri (../, ./ vs) temizle
    original_filename = secure_filename(file.filename)
    
    # Aşama 2: Kriptografik İsımlendirme (Zorunlu)
    # Orijinal dosya adını TAMAMEN siliyoruz. Yerine tahmin edilemez bir UUID veriyoruz.
    # Neden? Çünkü saldırgan "dekont.php.jpg" gibi çift uzantılı dosyalarla filtreyi aşmaya çalışabilir.
    ext = original_filename.rsplit('.', 1)[1].lower()
    safe_filename = f"{uuid.uuid4().hex}.{ext}"
    
    # Güvenli yolu oluştur ve kaydet
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
    file.save(save_path)
    
    return safe_filename

# Uygulama başlarken tabloları oluştur
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)