from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
import uuid

db = SQLAlchemy()

# 1. ADMIN TABLOSU
class Admin(UserMixin, db.Model):
    __tablename__ = 'admins'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False) 
    password_hash = db.Column(db.String(256), nullable=False)

    def __repr__(self):
        return f'<Admin {self.username}>'

# 2. HALI SAHA TABLOSU
class Pitch(db.Model):
    __tablename__ = 'pitches'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    
    # İlişkilerin hepsi tek bir yerde toplandı
    reservations = db.relationship('Reservation', backref='pitch', lazy=True, cascade='all, delete-orphan')
    images = db.relationship('PitchImage', backref='pitch', lazy=True, cascade='all, delete-orphan')
    blocked_slots = db.relationship('BlockedSlot', backref='pitch', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Pitch {self.name}>'

# SAHA RESİMLERİ TABLOSU
class PitchImage(db.Model):
    __tablename__ = 'pitch_images'
    
    id = db.Column(db.Integer, primary_key=True)
    pitch_id = db.Column(db.Integer, db.ForeignKey('pitches.id'), nullable=False)
    image_filename = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# 3. REZERVASYON TABLOSU
class Reservation(db.Model):
    __tablename__ = 'reservations'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pitch_id = db.Column(db.Integer, db.ForeignKey('pitches.id'), nullable=False)
    
    date = db.Column(db.Date, nullable=False)
    time_slot = db.Column(db.String(20), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(15), nullable=False)
    customer_email = db.Column(db.String(120), nullable=False)
    receipt_filename = db.Column(db.String(255), nullable=False)
    
    status = db.Column(db.String(20), default='Pending', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Reservation {self.date} {self.time_slot} - {self.status}>'

# 4. KİLİTLİ SLOT TABLOSU
class BlockedSlot(db.Model):
    __tablename__ = 'blocked_slots'
    
    id = db.Column(db.Integer, primary_key=True)
    pitch_id = db.Column(db.Integer, db.ForeignKey('pitches.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time_slot = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.String(200), nullable=False, default='Bahar Şenlikleri Sebebiyle Sahamız kullanılamamaktadır.')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<BlockedSlot {self.date} {self.time_slot} pitch={self.pitch_id}>'