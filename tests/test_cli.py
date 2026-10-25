"""Admin hesap komutları."""
import re


def test_admin_commands(app):
    from models import Admin
    r = app.test_cli_runner()
    assert 'yonetici' in r.invoke(args=['create-admin']).output
    r.invoke(args=['rename-admin', 'yonetici', 'yonetici1'])
    out = r.invoke(args=['create-admin', 'yonetici2']).output
    assert re.search(r'Sifre\s+: \S{20}', out)
    assert 'zaten mevcut' in r.invoke(args=['create-admin', 'yonetici2']).output
    assert r.invoke(args=['create-admin', 'yönetici']).exit_code != 0
    with app.app_context():
        assert sorted(a.username for a in Admin.query.all()) == ['yonetici1', 'yonetici2']
