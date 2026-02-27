from app import app
from models import db, Admin
from werkzeug.security import generate_password_hash

with app.app_context():
    # 1. ESKİYİ YIK: Eski tabloları (ve içindeki çakışan verileri) acımasızca siler
    db.drop_all()
    print("🗑️ Eski tablolar PostgreSQL'den tamamen silindi.")

    # 2. YENİYİ İNŞA ET: Modellerdeki en GÜNCEL hale göre tabloları baştan yaratır (customer_email dahil)
    db.create_all()
    print("✅ Yeni tablolar (customer_email sütunuyla birlikte) başarıyla oluşturuldu!")

    # 3. YÖNETİCİYİ ATA: İlk yöneticiyi tekrar ekle
    hashed_password = generate_password_hash("halisaha123", method='pbkdf2:sha256')
    yeni_admin = Admin(username='yonetici', password_hash=hashed_password)
    db.session.add(yeni_admin)
    db.session.commit()
    print("👑 Yönetici hesabı eklendi! (Kullanıcı adı: yonetici, Şifre: halisaha123)")