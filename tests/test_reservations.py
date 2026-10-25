"""Rezervasyon kuralları: reddedilen slot, kişi başı sınır, iptal, zaman aşımı."""
import os
import datetime as dt

from conftest import reserve, future_weekday, flashes


def _res(app):
    from models import Reservation
    with app.app_context():
        return Reservation.query.order_by(Reservation.created_at.desc()).first()


def test_rejected_slot_can_be_booked_again(app, admin_client, pitch):
    d = future_weekday()
    assert reserve(app, pitch, date=d)[0] == '/rezervasyon-basarili'
    admin_client.post(f'/admin/status/{_res(app).id}/reject')
    loc, _ = reserve(app, pitch, date=d, phone='05559998877', email='veli@x.com')
    assert loc == '/rezervasyon-basarili'


def test_active_slot_cannot_be_double_booked(app, pitch):
    d = future_weekday()
    reserve(app, pitch, date=d)
    loc, c = reserve(app, pitch, date=d, phone='05559998877', email='veli@x.com')
    assert loc == '/'


def test_person_can_make_two_reservations_per_day(app, pitch):
    d1 = future_weekday(3)
    d2 = d1 + dt.timedelta(days=1)
    while d2.weekday() >= 5:
        d2 += dt.timedelta(days=1)
    assert reserve(app, pitch, date=d1)[0] == '/rezervasyon-basarili'
    assert reserve(app, pitch, date=d2)[0] == '/rezervasyon-basarili'
    # Bugünkü 3. talep: aynı telefon, farklı e-posta ve farklı IP → yine engellenir
    loc, c = reserve(app, pitch, date=d1, slot='18:00 - 19:00', email='baska@x.com', ip='10.0.0.99')
    assert loc == '/'
    assert any('en fazla 2' in m for m in flashes(c))
    # Aynı IP'den (kampüs ağı) başka bir kişi etkilenmez
    loc, _ = reserve(app, pitch, date=d1, slot='18:00 - 19:00',
                     phone='05559998877', email='veli@x.com')
    assert loc == '/rezervasyon-basarili'


def test_cancelled_request_gives_daily_right_back(app, pitch):
    reserve(app, pitch, date=future_weekday(3))
    reserve(app, pitch, date=future_weekday(3), slot='18:00 - 19:00')
    code = _res(app).tracking_code
    app.test_client().post('/rezervasyon-iptal', data={'tracking_code': code, 'customer_phone': '05551112233'})
    assert reserve(app, pitch, date=future_weekday(3), slot='18:00 - 19:00')[0] == '/rezervasyon-basarili'


def test_user_can_cancel_with_correct_phone(app, pitch):
    d = future_weekday()
    reserve(app, pitch, date=d)
    code = _res(app).tracking_code
    c = app.test_client()
    c.post('/rezervasyon-iptal', data={'tracking_code': code, 'customer_phone': '05000000000'})
    assert _res(app).status == 'Pending'
    c.post('/rezervasyon-iptal', data={'tracking_code': code, 'customer_phone': '0555 111 22 33'})
    assert _res(app).status == 'Cancelled'
    # iptal edilen saat tekrar kiralanabilir
    assert reserve(app, pitch, date=d, phone='05559998877', email='v@x.com')[0] == '/rezervasyon-basarili'


def test_cannot_cancel_past_reservation(app, pitch):
    from extensions import db
    reserve(app, pitch)
    r = _res(app)
    with app.app_context():
        from models import Reservation
        res = db.session.get(Reservation, r.id)
        res.date = dt.date.today() - dt.timedelta(days=1)
        db.session.commit()
    app.test_client().post('/rezervasyon-iptal', data={
        'tracking_code': r.tracking_code, 'customer_phone': '05551112233'})
    assert _res(app).status == 'Pending'


def test_long_pending_request_expires(app, pitch):
    from extensions import db
    from models import Reservation
    from services.scheduler import auto_expire_reservations
    from utils.timeutil import now_tr
    reserve(app, pitch, date=future_weekday(days=10))
    with app.app_context():
        r = Reservation.query.one()
        r.created_at = now_tr() - dt.timedelta(hours=49)
        db.session.commit()
        auto_expire_reservations()
        assert Reservation.query.one().status == 'Expired'


def test_receipt_removed_when_reservation_fails(app, pitch, db, monkeypatch):
    folder = app.config['UPLOAD_FOLDER']
    before = set(os.listdir(folder))

    def boom():
        raise RuntimeError('db hatasi')
    monkeypatch.setattr(db.session, 'commit', boom)
    loc, _ = reserve(app, pitch)
    monkeypatch.undo()
    assert loc == '/'
    assert set(os.listdir(folder)) == before


def test_public_pages_not_limited_for_campus_network(app):
    c = app.test_client()
    codes = {c.get('/').status_code for _ in range(150)}
    assert codes == {200}
