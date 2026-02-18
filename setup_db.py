from app import app
from models import db, Admin, Pitch
from werkzeug.security import generate_password_hash

with app.app_context():
    # 1. Tabloları veritabanında fiziksel olarak oluştur
    db.create_all()
    print("✅ Tablolar PostgreSQL'e başarıyla basıldı!")

    # 2. Sistemde hiç Admin var mı kontrol et
    if not Admin.query.filter_by(username='yonetici').first():
        print("⚙️ İlk admin hesabı oluşturuluyor...")
        
        # Şifreyi DÜZ METİN OLARAK ASLA kaydetmiyoruz! Güvenli bir şekilde hash'liyoruz.
        hashed_password = generate_password_hash("halisaha123", method='pbkdf2:sha256')
        
        yeni_admin = Admin(username='yonetici', password_hash=hashed_password)
        db.session.add(yeni_admin)
        db.session.commit()
        print("✅ Admin hesabı eklendi! (Kullanıcı adı: yonetici, Şifre: halisaha123)")
    else:
        print("ℹ️ Admin hesabı zaten mevcut.")