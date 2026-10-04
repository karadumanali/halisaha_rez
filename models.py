"""
models.py — Veritabanı modelleri.

7 tablo: admins, pitches, pitch_images, reservations,
         blocked_slots, login_attempts, audit_logs

Önemli: db nesnesi extensions.py'den import edilir (circular import önlemi).
"""

from flask_login import UserMixin
from datetime import datetime, timezone
import uuid
import secrets
import string

from extensions import db


def generate_tracking_code():
    """Benzersiz takip kodu uret: REZ-XXXX-XXXX formatinda."""
    chars = string.ascii_uppercase + string.digits
    part1 = ''.join(secrets.choice(chars) for _ in range(4))
    part2 = ''.join(secrets.choice(chars) for _ in range(4))
    return f"REZ-{part1}-{part2}"


# Timezone-aware UTC yardımcı fonksiyon
def utcnow():
    return datetime.now(timezone.utc)


# ── 1. ADMIN TABLOSU ──────────────────────────────────────────────

class Admin(UserMixin, db.Model):
    __tablename__ = 'admins'

    id            = db.Column(db.Integer,     primary_key=True)
    username      = db.Column(db.String(50),  unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    session_token = db.Column(db.String(64),  nullable=True)
    # session_token: her girişte yeni token üretilir
    # Farklı cihazdan giriş yapılınca eski token değişir → eski oturum geçersiz olur

    def __repr__(self):
        return f'<Admin {self.username}>'


# ── 2. HALI SAHA TABLOSU ──────────────────────────────────────────

class Pitch(db.Model):
    __tablename__ = 'pitches'

    id    = db.Column(db.Integer,     primary_key=True)
    name  = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer,     nullable=False)

    reservations  = db.relationship('Reservation',  backref='pitch', lazy=True, cascade='all, delete-orphan')
    images        = db.relationship('PitchImage',   backref='pitch', lazy=True, cascade='all, delete-orphan')
    blocked_slots = db.relationship('BlockedSlot',  backref='pitch', lazy=True, cascade='all, delete-orphan')
    time_slots    = db.relationship('PitchTimeSlot', backref='pitch', lazy=True, cascade='all, delete-orphan',
                                     order_by='PitchTimeSlot.start_hour')

    @property
    def slot_hours(self):
        """Tanımlı slotların başlangıç saatleri: [9, 10, 11, ...]"""
        return [ts.start_hour for ts in self.time_slots]

    @property
    def slot_ranges(self):
        """Ardışık slotları birleştirir: ['09:00–12:00', '17:00–22:00']"""
        return PitchTimeSlot.ranges(self.slot_hours)

    def __repr__(self):
        return f'<Pitch {self.name}>'


# ── 3. SAHA RESİMLERİ TABLOSU ────────────────────────────────────

class PitchImage(db.Model):
    __tablename__ = 'pitch_images'

    id             = db.Column(db.Integer,     primary_key=True)
    pitch_id       = db.Column(db.Integer,     db.ForeignKey('pitches.id'), nullable=False)
    image_filename = db.Column(db.String(255), nullable=False)
    created_at     = db.Column(db.DateTime,    default=utcnow)


# ── 4. REZERVASYON TABLOSU ────────────────────────────────────────

class Reservation(db.Model):
    __tablename__ = 'reservations'

    # V-06: UNIQUE constraint — aynı saha + tarih + saat için çift rezervasyon engeli
    __table_args__ = (
        db.UniqueConstraint('pitch_id', 'date', 'time_slot',
                            name='uq_reservation_active_slot'),
    )

    id               = db.Column(db.String(36),  primary_key=True, default=lambda: str(uuid.uuid4()))
    tracking_code    = db.Column(db.String(13),  unique=True, nullable=False, default=generate_tracking_code)
    pitch_id         = db.Column(db.Integer,     db.ForeignKey('pitches.id'), nullable=False)
    date             = db.Column(db.Date,        nullable=False)
    time_slot        = db.Column(db.String(20),  nullable=False)
    customer_name    = db.Column(db.String(100), nullable=False)
    customer_phone   = db.Column(db.String(15),  nullable=False)
    customer_email   = db.Column(db.String(120), nullable=False)
    receipt_filename = db.Column(db.String(255), nullable=False)
    status           = db.Column(db.String(20),  default='Pending', nullable=False)
    created_at       = db.Column(db.DateTime,    default=utcnow)

    def __repr__(self):
        return f'<Reservation {self.date} {self.time_slot} - {self.status}>'


# ── 5. KİLİTLİ SLOT TABLOSU ──────────────────────────────────────

class BlockedSlot(db.Model):
    __tablename__ = 'blocked_slots'

    id        = db.Column(db.Integer,     primary_key=True)
    pitch_id  = db.Column(db.Integer,     db.ForeignKey('pitches.id'), nullable=False)
    date      = db.Column(db.Date,        nullable=False)
    time_slot = db.Column(db.String(20),  nullable=False)
    reason    = db.Column(db.String(200), nullable=False,
                          default='Bahar Şenlikleri Sebebiyle Sahamız kullanılamamaktadır.')
    created_at = db.Column(db.DateTime,   default=utcnow)

    def __repr__(self):
        return f'<BlockedSlot {self.date} {self.time_slot} pitch={self.pitch_id}>'


# ── 6. GİRİŞ DENEMELERİ TABLOSU (Brute-Force koruması) ──────────

class LoginAttempt(db.Model):
    __tablename__ = 'login_attempts'

    id           = db.Column(db.Integer,    primary_key=True)
    ip_address   = db.Column(db.String(45), nullable=False)
    username     = db.Column(db.String(50))
    attempted_at = db.Column(db.DateTime,   default=utcnow)
    success      = db.Column(db.Boolean,    default=False)

    def __repr__(self):
        return f'<LoginAttempt {self.ip_address} {self.attempted_at} success={self.success}>'


# ── 7. DENETİM KAYITLARI TABLOSU (Audit Log) ─────────────────────

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id         = db.Column(db.Integer,     primary_key=True)
    admin      = db.Column(db.String(50),  nullable=False)           # kim yaptı
    ip_address = db.Column(db.String(45),  nullable=False)           # hangi IP'den
    action     = db.Column(db.String(100), nullable=False)           # ne yaptı
    detail     = db.Column(db.String(500), nullable=True)            # detay
    created_at = db.Column(db.DateTime,    default=utcnow, nullable=False)  # ne zaman

    def __repr__(self):
        return f'<AuditLog {self.admin} | {self.action} | {self.created_at}>'


# ── 8. SAHA SAAT DİLİMLERİ TABLOSU ──────────────────────────────

class PitchTimeSlot(db.Model):
    __tablename__ = 'pitch_time_slots'

    __table_args__ = (
        db.UniqueConstraint('pitch_id', 'start_hour',
                            name='uq_pitch_time_slot'),
    )

    id         = db.Column(db.Integer, primary_key=True)
    pitch_id   = db.Column(db.Integer, db.ForeignKey('pitches.id'), nullable=False)
    start_hour = db.Column(db.Integer, nullable=False)  # 0-23
    end_hour   = db.Column(db.Integer, nullable=False)   # 1-24

    @property
    def label(self):
        """'09:00 - 10:00' formatında etiket döndürür."""
        return f'{self.start_hour:02d}:00 - {self.end_hour:02d}:00'

    @staticmethod
    def ranges(hours):
        """Başlangıç saatlerini ardışık aralıklara birleştirir.
        [9, 10, 11, 17, 18] → ['09:00–12:00', '17:00–19:00']"""
        result = []
        start = prev = None
        for h in sorted(hours):
            if start is not None and h == prev + 1:
                prev = h
                continue
            if start is not None:
                result.append(f'{start:02d}:00–{prev + 1:02d}:00')
            start = prev = h
        if start is not None:
            result.append(f'{start:02d}:00–{prev + 1:02d}:00')
        return result

    def __repr__(self):
        return f'<PitchTimeSlot {self.label} pitch={self.pitch_id}>'
