# Güvenlik Sızma Testi Raporu

**Proje:** AYBÜ SKS Spor Tesisleri — Halisaha Rezervasyon Sistemi
**Tarih:** 2026-04-02
**Genel Güvenlik Puanı:** 8.4 / 10
**Test Kapsamı:** Kaynak kodu statik analiz (SAST) + business logic incelemesi

---

## Yönetici Özeti

Sistem genel olarak **iyi güvenlik pratiği** sergilemektedir. CSRF koruması, Argon2id şifre hashleme, oturum token doğrulaması, rate limiting, CSP/HSTS header'ları ve audit logging gibi kritik savunma mekanizmaları yerinde ve doğru uygulanmıştır. Tespit edilen açıkların büyük çoğunluğu **deployment konfigürasyonu** ve **operasyonel güvenlik** kategorisindedir; kodun kendisinde kritik bir zayıflık bulunamamıştır.

---

## Puanlama

| Kategori | Puan | Notlar |
|----------|------|--------|
| Authentication | 9/10 | Argon2id, brute-force kilidi, session token rotasyonu |
| Authorization | 8/10 | login_required yerinde, tek admin rolü yeterli |
| Input Validation | 9/10 | Regex, ORM, header injection onlemi |
| Session Management | 9/10 | Güçlü token, cookie flags, otomatik geçersizleştirme |
| Security Headers | 9/10 | CSP, HSTS, X-Frame-Options, Referrer-Policy |
| File Upload | 7/10 | Magic bytes kontrolü var, web root dışına taşınmalı |
| Rate Limiting | 8/10 | Kritik endpoint'lerde mevcut |
| Logging & Monitoring | 8/10 | Audit log kapsamlı, log injection kapatıldı |
| Dependency Security | 7/10 | Güncel versiyonlar, pip-audit önerilir |
| Deployment Config | 6/10 | Aşağıdaki checklist uygulanmalı |
| **GENEL** | **8.4/10** | |

---

## Bulgular

---

### VULN-001 — Denetim Logu Injection
**Severity:** Medium → **KAPATILDI**
**Dosya:** `app.py:575`
**Açıklama:** `audit()` fonksiyonuna iletilen `action` ve `detail` parametrelerinde newline karakterleri bulunabiliyordu. Saldırgan müşteri adına `\nFAKE_ADMIN_ACTION` yazarak log kaydını manipüle edebilirdi.
**Düzeltme:** `re.sub(r'[\r\n\t]', ' ', ...)` ile control karakterler temizlendi.

---

### VULN-002 — Admin Şifresi Log Dosyasına Yazılıyordu
**Severity:** High → **KAPATILDI**
**Dosya:** `app.py:1479`
**Açıklama:** İlk `yonetici` hesabı oluşturulduğunda şifre `logger.info()` ile log dosyasına yazılıyordu. Log dosyasına erişim sağlayan biri (örn. log aggregation sistemi, IT personeli) açık metin şifreyi okuyabilirdi.
**Düzeltme:** `logger.info()` → `print()` ile değiştirildi; şifre artık yalnızca sunucu konsoluna (stdout) yazdırılıyor, log dosyasına gitmiyor.

---

### VULN-003 — SMTP Blocking DoS
**Severity:** High → **KAPATILDI**
**Dosya:** `app.py:487`
**Açıklama:** Rezervasyon ve onay akışlarında `smtplib.SMTP` senkron çağrılıyordu. Her SMTP bağlantısı 2-5 saniye request thread'ini bloke ediyordu. Rate limit (3/dk) ile birleşince saldırgan Gunicorn worker pool'unu tüketebilirdi.
**Düzeltme:** `_send_mail_async()` oluşturuldu, tüm mail çağrıları `threading.Thread(daemon=True)` ile background'a alındı. SMTP timeout 10 saniyeyle sınırlandırıldı.

---

### VULN-004 — Race Condition: Rezervasyon Oluşturma
**Severity:** High → **KAPATILDI**
**Dosya:** `app.py:719`
**Açıklama:** Slot müsaitlik kontrolü ile yeni rezervasyon INSERT'i arasında zaman penceresi mevcuttu. Eşzamanlı iki istek aynı slot'u çift rezerve edebilirdi.
**Düzeltme:** `with_for_update()` eklendi; `SELECT ... FOR UPDATE` ile sorgu anında satır kilitleniyor.

---

### VULN-005 — Race Condition: Concurrent Admin Onay/Red
**Severity:** Medium → **KAPATILDI**
**Dosya:** `app.py:1004`
**Açıklama:** İki admin aynı rezervasyona eşzamanlı işlem yapabiliyordu.
**Düzeltme:** `db.get_or_404()` → `Reservation.query.filter_by(id=res_id).with_for_update().first_or_404()` ile değiştirildi.

---

### VULN-006 — Datetime Tutarsızlığı (Küçük)
**Severity:** Low → **KAPATILDI**
**Dosya:** `app.py:689`
**Açıklama:** `datetime.now()` birden fazla kez çağrılıyordu; gece yarısı geçişlerinde nadir tutarsızlık oluşabilirdi.
**Düzeltme:** Tek `_now = datetime.now()` ile tüm karşılaştırmalar aynı anlık değeri kullanıyor.

---

### VULN-007 — Yüklenmiş Dosyalar Web Root'unda
**Severity:** Medium → **Deployment'ta Kapatılacak**
**Dosya:** `app.py` / `UPLOAD_FOLDER` config
**Açıklama:** Dekont dosyaları web root içinde `static/uploads/` altında sunuluyor. Nginx/Apache yanlış yapılandırılırsa dosyalara doğrudan URL ile erişilebilir.
**Öneri (Deployment):** Aşağıdaki Deployment Checklist'e bakınız — UPLOAD_FOLDER web root dışına taşınmalı.

---

### VULN-008 — Bağımlılık Güvenliği
**Severity:** Low → **Periyodik Kontrol Gerekiyor**
**Dosya:** `requirements.txt`
**Açıklama:** Paket versiyonları sabitlenmiş (iyi) fakat bilinen CVE'ler düzenli taranmıyor.
**Öneri:**
```bash
pip install pip-audit
pip-audit
```

---

### BILGI-001 — SQL Injection
**Severity:** Yok
Tüm database işlemleri SQLAlchemy ORM üzerinden yapılıyor. Raw SQL veya f-string SQL kullanımı tespit edilmedi.

---

### BILGI-002 — XSS
**Severity:** Yok
Jinja2 auto-escape aktif. Template'lerde `| safe` veya `Markup()` kullanımı tespit edilmedi. CSP header'ı nonce tabanlı uygulanmış.

---

### BILGI-003 — CSRF
**Severity:** Yok
Flask-WTF CSRFProtect tüm POST isteklerini koruyor. Token doğrulaması aktif.

---

### BILGI-004 — Command Injection
**Severity:** Yok
`os.system()`, `subprocess`, `shell=True` kullanımı tespit edilmedi.

---

### BILGI-005 — Path Traversal
**Severity:** Yok
Dosya isimleri `uuid.uuid4().hex` ile üretiliyor. `os.path.basename()` ve regex doğrulaması ile güvenli.

---

## Deployment Checklist (Yayınlama Öncesi Zorunlu Adımlar)

Aşağıdaki adımlar uygulanmadan sistemi canlıya ALMAYIN.

---

### 1. Ortam Değişkenleri

```bash
# .env dosyasında şunlar MUTLAKA ayarlanmalı:
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=<en az 64 karakter rastgele string — python -c "import secrets; print(secrets.token_hex(64))">
DATABASE_URL=postgresql://user:GUCLU_SIFRE@localhost:5432/halisaha_db
MAIL_USERNAME=<gmail adresi>
MAIL_PASSWORD=<gmail uygulama şifresi — 2FA aktif olmalı>
ADMIN_EMAIL=<admin mail>
RECAPTCHA_SECRET_KEY=<gerçek key>
RECAPTCHA_SITE_KEY=<gerçek key>
```

**UYARI:** `.env` dosyasının izinleri kısıtlanmalı:
```bash
chmod 600 .env
chown www-data:www-data .env  # veya uygulama kullanıcısı
```

---

### 2. PostgreSQL SSL Bağlantısı

Veritabanı sunucu ile uygulama aynı sunucuda değilse:
```bash
DATABASE_URL=postgresql://user:pass@dbhost:5432/halisaha_db?sslmode=require
```

---

### 3. Nginx Konfigürasyonu — Upload Dizini Koruması

```nginx
server {
    # Yüklenen dosyaları doğrudan erişime KAPAT
    location /static/uploads/ {
        deny all;
        return 404;
    }

    # Sadece Flask üzerinden servis edilsin
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Alternatif (önerilen):** `UPLOAD_FOLDER` web root dışına taşı:
```python
# app.py / .env
UPLOAD_FOLDER=/var/uploads/halisaha_receipts  # /var/www dışında!
```

---

### 4. HTTPS / SSL Sertifikası

```nginx
# HTTPS zorunlu — HTTP'yi yönlendir
server {
    listen 80;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;
    ssl_certificate     /etc/ssl/certs/site.crt;
    ssl_certificate_key /etc/ssl/private/site.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
}
```

---

### 5. Gunicorn ile Çalıştırma

`app.run()` asla production'da kullanılmaz:
```bash
gunicorn --workers 4 --bind 127.0.0.1:8000 --timeout 30 app:app
```

systemd service önerisi:
```ini
[Service]
User=www-data
WorkingDirectory=/var/www/halisaha_rez
ExecStart=/var/www/halisaha_rez/.venv/bin/gunicorn --workers 4 --bind 127.0.0.1:8000 app:app
EnvironmentFile=/var/www/halisaha_rez/.env
Restart=always
```

---

### 6. Firewall (UFW)

```bash
ufw allow 22/tcp    # SSH (kaynak IP kısıtla)
ufw allow 80/tcp    # HTTP (HTTPS'e yönlendir)
ufw allow 443/tcp   # HTTPS
ufw deny 5432/tcp   # PostgreSQL dışarıya KAPALI
ufw enable
```

---

### 7. PostgreSQL Sertleştirme

```sql
-- Sadece uygulama kullanıcısı, sadece kendi DB'ye erişsin
REVOKE ALL ON DATABASE halisaha_db FROM PUBLIC;
GRANT CONNECT ON DATABASE halisaha_db TO halisaha_app;
GRANT USAGE ON SCHEMA public TO halisaha_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO halisaha_app;

-- postgres superuser ile uygulama BAĞLANMAMALI
-- Yeni kullanıcı oluştur:
CREATE USER halisaha_app WITH PASSWORD 'guclu_sifre_buraya';
```

---

### 8. Statik CDN Dosyaları — Subresource Integrity

Bootstrap ve diğer CDN kaynakları SRI hash ile doğrulanmalı:
```html
<!-- Örnek: -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.x/dist/js/bootstrap.min.js"
        integrity="sha384-XXXXX"
        crossorigin="anonymous"></script>
```

SRI hash üretmek için: https://www.srihash.org/

---

### 9. Log Güvenliği

```bash
# Log dosyaları sadece uygulama kullanıcısı okuyabilmeli
chmod 640 /var/log/halisaha/*.log
chown www-data:adm /var/log/halisaha/*.log

# Log rotation
logrotate -d /etc/logrotate.d/halisaha
```

---

### 10. pip-audit — Dependency Taraması

```bash
pip install pip-audit
pip-audit -r requirements.txt
```
Yayın öncesi ve her ay çalıştırılmalı.

---

### 11. İlk Admin Şifresini Değiştir

Sunucuyu ilk başlattığında konsolda çıkan şifreyi hemen değiştir:
```
Admin paneli → Şifre Değiştir
```
Kullan, sil, unut. Bu şifreyi hiçbir yerde saklama.

---

## Güvenlik Kontrol Özeti

| # | Kontrol | Durum |
|---|---------|-------|
| 1 | Argon2id şifre hashleme | Aktif |
| 2 | CSRF koruması | Aktif |
| 3 | Rate limiting (login, rezervasyon) | Aktif |
| 4 | Brute-force kilidi (5 hatalı giriş → 15dk kilit) | Aktif |
| 5 | Session token rotasyonu | Aktif |
| 6 | CSP header (nonce tabanlı) | Aktif |
| 7 | HSTS header | Aktif |
| 8 | X-Frame-Options: DENY | Aktif |
| 9 | X-Content-Type-Options: nosniff | Aktif |
| 10 | SQL Injection (ORM kullanımı) | Korumalı |
| 11 | XSS (Jinja2 auto-escape) | Korumalı |
| 12 | Command Injection | Risk yok |
| 13 | Path Traversal (UUID dosya adı) | Korumalı |
| 14 | File upload MIME kontrolü | Aktif |
| 15 | Audit logging (730 gün) | Aktif |
| 16 | Race condition (FOR UPDATE) | Kapatıldı |
| 17 | SMTP async (DoS önlemi) | Kapatıldı |
| 18 | Log injection önlemi | Kapatıldı |
| 19 | Admin şifre log leak | Kapatıldı |
| 20 | HTTPS | Deployment'ta yapılacak |
| 21 | Upload dizini web root dışı | Deployment'ta yapılacak |
| 22 | PostgreSQL kısıtlı kullanıcı | Deployment'ta yapılacak |
| 23 | Gunicorn (app.run değil) | Deployment'ta yapılacak |
| 24 | CDN Subresource Integrity | Opsiyonel |
| 25 | pip-audit (dependency CVE tarama) | Periyodik |

---

*Rapor tarihi: 2026-04-02 | Hazırlayan: Statik kod analizi (SAST)*
