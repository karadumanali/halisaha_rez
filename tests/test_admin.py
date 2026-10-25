"""Slot kilitleme, çakışma uyarısı, dekont, denetim kaydı."""
from conftest import reserve, future_weekday, flashes, PDF_BYTES


def _lock(client, pitch, date, reason):
    return client.post('/admin/block_slot', data={
        'pitch_ids': [str(pitch['id'])], 'dates': [date.isoformat()],
        'time_slots': ['17:00 - 18:00'], 'reason': reason})


def test_lock_requires_reason(app, admin_client, pitch):
    from models import BlockedSlot
    _lock(admin_client, pitch, future_weekday(), '   ')
    with app.app_context():
        assert BlockedSlot.query.count() == 0
    assert any('sebebi' in m for m in flashes(admin_client))


def test_lock_with_reason(app, admin_client, pitch):
    from models import BlockedSlot
    _lock(admin_client, pitch, future_weekday(), '  Bakım   çalışması ')
    with app.app_context():
        assert BlockedSlot.query.one().reason == 'Bakım çalışması'


def test_lock_over_active_reservation_warns(app, admin_client, pitch):
    d = future_weekday()
    reserve(app, pitch, date=d)
    rv = admin_client.get('/admin/api/block_conflicts', query_string={
        'pitch_ids': pitch['id'], 'dates': d.isoformat(), 'time_slots': '17:00 - 18:00'})
    assert len(rv.get_json()['conflicts']) == 1
    _lock(admin_client, pitch, d, 'Turnuva')
    assert any('DIKKAT' in m for m in flashes(admin_client))


def test_pdf_receipt_is_downloaded_not_rendered(app, admin_client, pitch):
    from models import Reservation
    reserve(app, pitch)
    with app.app_context():
        fn = Reservation.query.one().receipt_filename
    rv = admin_client.get(f'/admin/receipt/{fn}')
    assert rv.status_code == 200
    assert rv.headers['Content-Disposition'].startswith('attachment')


def test_audit_log_shows_admin_and_filter(app, admin_client, pitch):
    _lock(admin_client, pitch, future_weekday(), 'Bakım')
    page = admin_client.get('/admin/').get_data(as_text=True)
    assert 'id="auditAdminFilter"' in page
    assert '<option value="yonetici1">' in page


def test_pitch_without_reservations_is_deleted(app, admin_client, pitch):
    from models import Pitch
    admin_client.post(f"/admin/delete_pitch/{pitch['id']}")
    with app.app_context():
        assert Pitch.query.count() == 0


def test_pitch_with_reservations_becomes_passive(app, admin_client, pitch):
    from extensions import db
    from models import Pitch, Reservation
    reserve(app, pitch)
    admin_client.post(f"/admin/delete_pitch/{pitch['id']}")
    with app.app_context():
        assert db.session.get(Pitch, pitch['id']).is_active is False
        assert Reservation.query.count() == 1            # geçmiş korunur
    assert any('pasife' in m for m in flashes(admin_client))
    assert 'Saha 1' not in app.test_client().get('/').get_data(as_text=True)
    loc, _ = reserve(app, pitch, date=future_weekday(5), phone='05559998877', email='v@x.com')
    assert loc == '/'                                     # pasif sahaya rezervasyon yok
    page = admin_client.get('/admin/').get_data(as_text=True)
    assert 'Pasif Sahalar (1)' in page
    admin_client.post(f"/admin/activate_pitch/{pitch['id']}")
    with app.app_context():
        assert db.session.get(Pitch, pitch['id']).is_active is True
