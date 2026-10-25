"""Kullanıcıya yalnızca 'talebiniz alındı' maili gider."""
import smtplib
import time

from conftest import reserve


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def starttls(self):
        pass

    def login(self, u, p):
        pass

    def send_message(self, m):
        FakeSMTP.sent.append(m)


def _wait(n):
    for _ in range(50):
        if len(FakeSMTP.sent) >= n:
            return
        time.sleep(0.02)


def test_received_mail_only(app, admin_client, pitch, monkeypatch):
    from models import Reservation
    FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, 'SMTP', FakeSMTP)
    monkeypatch.setenv('MAIL_USERNAME', 'halisaha@aybu.edu.tr')
    monkeypatch.setenv('MAIL_PASSWORD', 'x')
    monkeypatch.delenv('ADMIN_EMAIL', raising=False)

    reserve(app, pitch, email='ayse@ogr.aybu.edu.tr')
    _wait(1)
    with app.app_context():
        r = Reservation.query.one()
    assert len(FakeSMTP.sent) == 1
    msg = FakeSMTP.sent[0]
    assert msg['To'] == 'ayse@ogr.aybu.edu.tr'
    assert r.tracking_code in msg['Subject']
    assert r.tracking_code in msg.get_content()
    assert 'yönetici onayından sonra kesinleşecektir' in msg.get_content()

    admin_client.post(f'/admin/status/{r.id}/approve')
    time.sleep(0.2)
    assert len(FakeSMTP.sent) == 1   # onayda mail yok


def test_bad_mail_settings_do_not_break_reservation(app, pitch, monkeypatch):
    """.env'de MAIL_USERNAME yanlış yazılmışsa (ör. açıklama metni) rezervasyon yine kaydedilir."""
    from models import Reservation
    FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, 'SMTP', FakeSMTP)
    monkeypatch.setenv('MAIL_USERNAME', '(gonderim hesabinin adresi)')
    monkeypatch.setenv('MAIL_PASSWORD', '(sifre)')
    monkeypatch.setenv('ADMIN_EMAIL', '(bildirim adresi)')
    loc, _ = reserve(app, pitch)
    assert loc == '/rezervasyon-basarili'
    with app.app_context():
        assert Reservation.query.count() == 1
    assert FakeSMTP.sent == []


def test_bad_admin_email_does_not_break_reservation(app, pitch, monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, 'SMTP', FakeSMTP)
    monkeypatch.setenv('MAIL_USERNAME', 'halisaha@aybu.edu.tr')
    monkeypatch.setenv('MAIL_PASSWORD', 'x')
    monkeypatch.setenv('ADMIN_EMAIL', '(bildirim adresi)')
    loc, _ = reserve(app, pitch, email='ayse@ogr.aybu.edu.tr')
    assert loc == '/rezervasyon-basarili'
    _wait(1)
    assert [m['To'] for m in FakeSMTP.sent] == ['ayse@ogr.aybu.edu.tr']
