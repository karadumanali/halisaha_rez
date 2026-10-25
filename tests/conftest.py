"""
Test altyapısı — geçici SQLite veritabanı üzerinde tüm migration'lar çalıştırılır.

Çalıştırma (proje klasöründe, sanal ortam açıkken):
    pip install -r requirements-dev.txt
    python -m pytest
"""

import io
import os
import sys
import tempfile
import datetime as dt

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_TMP = tempfile.mkdtemp(prefix='halisaha_test_')
os.environ.update({
    'SECRET_KEY': 'test-' + 'x' * 40,
    'DATABASE_URL': 'sqlite:///' + os.path.join(_TMP, 'test.db'),
    'FLASK_ENV': 'development',
    'RECAPTCHA_SECRET_KEY': '',
    'RECAPTCHA_SITE_KEY': '',
    'UPLOAD_PATH': os.path.join(_TMP, 'receipts'),
    'MAIL_USERNAME': '',
    'MAIL_PASSWORD': '',
    'REDIS_URL': 'memory://',
    'PROXY_COUNT': '0',
})

ADMIN_PW = 'Abcdef123!x'
PDF_BYTES = b'%PDF-1.4\n' + b'0' * 200


@pytest.fixture(scope='session')
def app():
    from app import create_app
    from flask_migrate import upgrade
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with application.app_context():
        upgrade(directory=os.path.join(ROOT, 'migrations'))
    yield application
    from services.scheduler import scheduler
    if scheduler.running:
        scheduler.shutdown(wait=False)


@pytest.fixture(autouse=True)
def clean_state(app):
    """Her testten önce tabloları ve rate-limit sayaçlarını temizle."""
    from extensions import db, limiter
    from models import (Reservation, BlockedSlot, AuditLog, LoginAttempt, Admin,
                        PitchPricing, PitchTimeSlot, PitchImage, Pitch)
    with app.app_context():
        for model in (Reservation, BlockedSlot, AuditLog, LoginAttempt, Admin,
                      PitchPricing, PitchTimeSlot, PitchImage, Pitch):
            model.query.delete()
        db.session.commit()
        limiter.reset()
    app.config['WTF_CSRF_ENABLED'] = False
    yield


@pytest.fixture
def db(app):
    from extensions import db as _db
    return _db


@pytest.fixture
def pitch(app, db):
    """17:00-19:00 arası iki slotu olan, ilk müşteri tipine 500 TL fiyatlı saha."""
    from models import Pitch, PitchTimeSlot, PitchPricing, CustomerType
    with app.app_context():
        ct = CustomerType.query.order_by(CustomerType.id).first()
        p = Pitch(name='Saha 1')
        p.time_slots = [PitchTimeSlot(start_hour=17, end_hour=18),
                        PitchTimeSlot(start_hour=18, end_hour=19)]
        p.pricing = [PitchPricing(customer_type_id=ct.id, price=500)]
        db.session.add(p)
        db.session.commit()
        return {'id': p.id, 'ctype_id': ct.id}


def make_admin(app, db, username='yonetici1', password=ADMIN_PW):
    from models import Admin
    from utils.helpers import ph_hash
    with app.app_context():
        db.session.add(Admin(username=username, password_hash=ph_hash(password)))
        db.session.commit()


def login(client, username='yonetici1', password=ADMIN_PW):
    return client.post('/login', data={'username': username, 'password': password})


@pytest.fixture
def admin_client(app, db):
    make_admin(app, db)
    c = app.test_client()
    assert login(c).status_code == 302
    return c


def future_weekday(days=3):
    d = dt.date.today() + dt.timedelta(days=days)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def reserve(app, pitch, date=None, slot='17:00 - 18:00', phone='05551112233',
            email='ali@ogr.aybu.edu.tr', ip='10.0.0.1'):
    """Rezervasyon formunu gönder; yönlendirilen adresi döndür."""
    c = app.test_client()
    rv = c.post('/reserve', data={
        'pitch_id': pitch['id'], 'customer_type_id': pitch['ctype_id'],
        'date': (date or future_weekday()).isoformat(), 'time_slot': slot,
        'customer_name': 'Ali Veli', 'customer_phone': phone, 'customer_email': email,
        'receipt': (io.BytesIO(PDF_BYTES), 'dekont.pdf'),
    }, content_type='multipart/form-data', environ_base={'REMOTE_ADDR': ip})
    return rv.headers.get('Location'), c


def flashes(client):
    with client.session_transaction() as s:
        return [m for _, m in s.get('_flashes', [])]
