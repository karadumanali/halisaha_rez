"""Admin girişi, 429 düzeltmesi, oturum süresi, çıkış."""
from conftest import make_admin, login


def test_login_page_can_be_opened_many_times(app):
    c = app.test_client()
    codes = {c.get('/login').status_code for _ in range(30)}
    assert codes == {200}


def test_one_admins_wrong_passwords_do_not_lock_others(app, db):
    for u in ('yonetici1', 'yonetici2'):
        make_admin(app, db, u)
    c = app.test_client()
    for _ in range(5):
        c.post('/login', data={'username': 'yonetici1', 'password': 'yanlis'})
    other = app.test_client()
    assert login(other, 'yonetici2').headers['Location'].endswith('/admin/')


def test_session_cookie_expires(app, db):
    make_admin(app, db)
    rv = login(app.test_client())
    cookie = [h for h in rv.headers.getlist('Set-Cookie') if h.startswith('sks_sid=')][0]
    assert 'Expires=' in cookie   # 30 dk hareketsizlik süresi uygulanıyor


def test_logout_requires_post(admin_client):
    assert admin_client.get('/logout').status_code == 405
    rv = admin_client.post('/logout')
    assert rv.status_code == 302
    assert admin_client.get('/admin/').status_code == 302   # tekrar girişe yönlenir


def test_expired_csrf_redirects_to_login(app, admin_client):
    app.config['WTF_CSRF_ENABLED'] = True
    rv = admin_client.post('/admin/block_slot', data={'reason': 'x'})
    assert rv.status_code == 302 and '/login' in rv.headers['Location']


def test_admins_have_separate_sessions(app, db):
    for u in ('yonetici1', 'yonetici2'):
        make_admin(app, db, u)
    a, b = app.test_client(), app.test_client()
    login(a, 'yonetici1')
    login(b, 'yonetici2')
    assert a.get('/admin/').status_code == 200
    assert b.get('/admin/').status_code == 200
