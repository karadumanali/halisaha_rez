from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import uuid

db = SQLAlchemy()

# 1. ADMIN TABLOSU
class Admin(UserMixin, db.Model):
    __tablename__ = 'admins'
    
    id = db.Column(db.Integer, primary_key=True)
    # Maksimum 50 karakter sınırı (Buffer/Payload kısıtlaması)
    username = db.Column(db.String(50), unique=True, nullable=False) 
    # Şifreler kesinlikle düz metin tutulmaz, her zaman hashlenmiş olmalı.
    password_hash = db.Column(db.String(256), nullable=False)

    def __repr__(self):
        return f'<Admin {self.username}>'

# 2. HALI SAHA TABLOSU
class Pitch(db.Model):
    __tablename__ = 'pitches'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False) # Ücret (TL cinsinden tam sayı)
    
    # Bir sahanın birden fazla rezervasyonu olabilir
    reservations = db.relationship('Reservation', backref='pitch', lazy=True)

    def __repr__(self):
        return f'<Pitch {self.name}>'

# 3. REZERVASYON TABLOSU (Sistemin Kalbi ve En Güvenli Olması Gereken Yer)
class Reservation(db.Model):
    __tablename__ = 'reservations'
    
    # IDOR ZAFİYETİNE KARŞI ÖNLEM: Sıralı ID yerine tahmin edilemez UUID kullanıyoruz.
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    pitch_id = db.Column(db.Integer, db.ForeignKey('pitches.id'), nullable=False)
    
    date = db.Column(db.Date, nullable=False) # Sadece tarih: 2026-02-20
    time_slot = db.Column(db.String(20), nullable=False) # "20:00 - 21:00"
    
    # Veri bütünlüğü için kısıtlamalar
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(15), nullable=False) # İletişim için şart
    # YENİ EKLENEN SATIR: Müşteri E-Posta adresi
    customer_email = db.Column(db.String(120), nullable=False)
    # Dekont dosyasının sunucudaki güvenli adı (Path Traversal engellenecek)
    receipt_filename = db.Column(db.String(255), nullable=False)
    
    # Durum: Pending (Bekliyor), Approved (Onaylandı), Rejected (Reddedildi)
    status = db.Column(db.String(20), default='Pending', nullable=False)
    
    # Loglama ve denetim (Audit) için kayıt zamanı
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Reservation {self.date} {self.time_slot} - {self.status}>'