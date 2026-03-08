# AYBÜ Halı Saha Rezervasyon Sistemi — Aksiyon Planı

**Tarih:** 2026-03-08
**Hazırlayan:** Güvenlik Analiz Ekibi
**Amaç:** Üniversiteye teslim öncesi güvenlik sertleştirme, deployment stratejisi ve yapılacaklar listesi

---

## İÇİNDEKİLER

1. [Güvenlik Düzeltmeleri (Öncelik Sırasına Göre)](#1-güvenlik-düzeltmeleri)
2. [Deployment Analizi — Vercel / Render / Railway](#2-deployment-analizi)
3. [Dosya Yükleme Sorunu ve Çözümü](#3-dosya-yükleme-sorunu-ve-çözümü)
4. [Üniversite Ortamı İçin Sertleştirme](#4-üniversite-ortamı-için-sertleştirme)
5. [Yapılacaklar Kontrol Listesi](#5-yapılacaklar-kontrol-listesi)

---

## 1. GÜVENLİK DÜZELTMELERİ

### 1.1 KRİTİK — Hemen Yapılmalı

#### A) FLASK_DEBUG Kapatılmalı

**Sorun:** Debug mode açıkken Werkzeug interaktif debugger etkin. Herkes `/console` üzerinden sunucuda Python kodu çalıştırabilir (RCE).

**Çözüm:**
```python
# .env dosyasında
FLASK_DEBUG=False
```
Production ortamında **kesinlikle** `False` olmalı. Ayrıca app.py'de ekstra güvence:
```python
if os.getenv('FLASK_ENV') == 'production':
    app.config['DEBUG'] = False
    app.config['TESTING'] = False
```

---

#### B) SECRET_KEY Hardcoded Fallback Kaldırılmalı

**Sorun:** `.env` yoksa bilinen bir sabit anahtar kullanılıyor.

**Çözüm:**
```python
# Eski (TEHLİKELİ):
_secret = os.getenv('SECRET_KEY') or 'GECICI-DEV-KEY-...'

# Yeni (GÜVENLİ):
_secret = os.getenv('SECRET_KEY')
if not _secret:
    raise RuntimeError("SECRET_KEY ortam degiskeni ZORUNLUDUR! .env dosyasini kontrol edin.")
```

Güçlü bir SECRET_KEY üretmek için:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

#### C) Varsayılan Şifre Değiştirilmeli + Şifre Değiştirme Ekranı

**Sorun:** `yonetici / halisaha123` kaynak kodda açık yazılı, değiştirme mekanizması yok.

**Çözüm:**
1. İlk kurulumda şifreyi ortam değişkeninden al:
```python
default_password = os.getenv('ADMIN_DEFAULT_PASSWORD')
if not default_password:
    raise RuntimeError("ADMIN_DEFAULT_PASSWORD ortam degiskeni zorunludur!")
```
2. Admin paneline şifre değiştirme ekranı ekle
3. İlk girişte şifre değiştirmeye zorla (force password change)

---

#### D) Brute Force Koruması Sunucu Tarafına Taşınmalı

**Sorun:** Client-side `sessionStorage` koruması curl ile atlanır. Sunucu rate limit'i dakikada 5 — hala yüksek.

**Çözüm:**
```python
# 1. Rate limit'i sıkılaştır
@limiter.limit("3 per minute, 10 per hour, 20 per day")
def admin_login():
    ...

# 2. Başarısız giriş sayacı (DB tabanlı)
class LoginAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False)
    username = db.Column(db.String(50))
    attempted_at = db.Column(db.DateTime, default=datetime.utcnow)
    success = db.Column(db.Boolean, default=False)

# 3. 5 başarısız denemeden sonra 15 dakika kilitle
def is_account_locked(username, ip):
    cutoff = datetime.utcnow() - timedelta(minutes=15)
    fails = LoginAttempt.query.filter(
        LoginAttempt.username == username,
        LoginAttempt.attempted_at > cutoff,
        LoginAttempt.success == False
    ).count()
    return fails >= 5

# 4. Rate limiter storage: Redis kullan (in-memory değil)
limiter = Limiter(
    get_remote_address, app=app,
    storage_uri="redis://localhost:6379"  # veya REDIS_URL env
)
```

---

### 1.2 YÜKSEK — Deploy Öncesi Yapılmalı

#### E) Open Redirect Düzeltilmeli

**Sorun:** `//evil.com` → `startswith('/')` kontrolünü geçer.

**Çözüm:**
```python
from urllib.parse import urlparse

next_page = request.args.get('next')
if next_page:
    parsed = urlparse(next_page)
    # Sadece relative path kabul et, host/scheme olmamalı
    if not parsed.netloc and not parsed.scheme and next_page.startswith('/'):
        return redirect(next_page)
return redirect(url_for('admin_dashboard'))
```

---

#### F) Güvenlik Header'ları Eklenmeli

**Çözüm:** `@app.after_request` içine:
```python
@app.after_request
def security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com "
        "https://fonts.googleapis.com 'unsafe-inline'; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data:; "
        "connect-src 'self'"
    )
    if not app.debug:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    # Sunucu versiyon bilgisini gizle
    response.headers.pop('Server', None)
    return response
```

---

#### G) SESSION_COOKIE_SECURE Eklenmeli

```python
app.config['SESSION_COOKIE_SECURE'] = True   # Sadece HTTPS üzerinden
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
```

---

### 1.3 ORTA — Planlı Sprint İçinde

#### H) Input Doğrulama Eksikleri

```python
VALID_SLOTS = [
    '16:00 - 17:00', '17:00 - 18:00', '18:00 - 19:00',
    '19:00 - 20:00', '20:00 - 21:00', '21:00 - 22:00', '22:00 - 23:00'
]

# /reserve route'unda:
if time_slot not in VALID_SLOTS:
    flash('Gecersiz saat dilimi!', 'danger')
    return redirect(url_for('index'))

try:
    pitch_id = int(pitch_id)
except (ValueError, TypeError):
    flash('Gecersiz saha!', 'danger')
    return redirect(url_for('index'))

if not customer_name or len(customer_name.strip()) < 2 or len(customer_name) > 100:
    flash('Gecersiz isim!', 'danger')
    return redirect(url_for('index'))

# /busy_slots route'unda:
try:
    pitch_id = int(request.args.get('pitch_id', 0))
except (ValueError, TypeError):
    return jsonify({'busy': {}, 'blocked': {}})
```

---

#### I) Konsol Bilgi Sızıntıları Temizlenmeli

```python
# SİLİNMELİ veya logging modülüne taşınmalı:
# print("TEST - SECRET_KEY:", ...)
# print("Yönetici hesabı eklendi! (Kullanıcı adı: yonetici, Şifre: halisaha123)")

import logging
logger = logging.getLogger(__name__)
logger.info("Veritabani tablolari kontrol edildi.")
# Şifre ASLA loglanmamalı
```

---

#### J) Dekontlara Erişim Koruması

Dekontlar `static/` altında olduğu için herkes erişebilir.

**Çözüm:** Dosyaları `static/` dışına taşı ve Flask route ile sun:
```python
UPLOAD_FOLDER = 'uploads/receipts'  # static/ dışında

@app.route('/admin/receipt/<filename>')
@login_required
def view_receipt(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
```

---

#### K) Duplicate Kod Temizliği

- `anti_cache` fonksiyonu 2 kez tanımlı (satır 475 ve 484) → Birini sil
- `if __name__ == '__main__'` bloğu 2 kez (satır 515 ve 520) → Birini sil

---

## 2. DEPLOYMENT ANALİZİ

### Platform Karşılaştırması

| Özellik | Vercel | Render | Railway |
|---------|--------|--------|---------|
| Flask Desteği | Kısıtlı (serverless) | Tam destek | Tam destek |
| PostgreSQL | Yok (harici gerekir) | Dahili (ücretsiz) | Dahili |
| Dosya Sistemi | Ephemeral (read-only) | Ephemeral | Ephemeral |
| Dosya Yükleme | ÇALIŞMAZ | ÇALIŞMAZ (restart'ta silinir) | ÇALIŞMAZ (restart'ta silinir) |
| Websocket | Yok | Var | Var |
| Ücretsiz Plan | Var (sınırlı) | Var (750 saat/ay) | Var ($5 kredi/ay) |
| Custom Domain | Var | Var | Var |
| SSL | Otomatik | Otomatik | Otomatik |
| Gunicorn | Kullanılamaz | Kullanılır | Kullanılır |

### Tavsiye: Render (En Uygun)

**Neden Render?**
- Flask + Gunicorn tam destek
- Dahili PostgreSQL (ücretsiz tier mevcut)
- Basit deployment (GitHub'dan otomatik)
- SSL otomatik
- Üniversite projeleri için ideal fiyat/performans

**Neden Vercel DEĞİL?**
- Vercel serverless mimarisi kullanır → Flask'in `app.run()` modeli tam uyumlu değil
- Dosya yükleme **kesinlikle çalışmaz** (read-only filesystem)
- PostgreSQL yok, harici servis gerekir
- Python desteği deneysel ve sınırlı

---

## 3. DOSYA YÜKLEME SORUNU VE ÇÖZÜMÜ

### Sorun

Mevcut sistemde dosyalar yerel diske kaydediliyor:
```python
UPLOAD_FOLDER = 'static/uploads/receipts'
PITCH_IMAGES_FOLDER = 'static/uploads/pitches'
```

**Render, Railway, Vercel** gibi platformlarda dosya sistemi **ephemeral**'dir:
- Container/dyno restart olduğunda tüm dosyalar silinir
- Deploy yapıldığında dosyalar kaybolur
- Yani yüklenen dekontlar ve saha görselleri **kaybolacaktır**

### Çözüm: Cloudinary (Ücretsiz ve Kolay)

**Neden Cloudinary?**
- Ücretsiz plan: 25.000 dönüşüm/ay, 25 GB storage
- Python SDK mevcut, entegrasyon kolay
- Görsel optimizasyon dahili (thumbnail, resize)
- CDN ile hızlı erişim
- PDF desteği var

**Entegrasyon:**
```bash
pip install cloudinary
```

```python
import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

def save_secure_receipt(file):
    # ... mevcut MIME/extension doğrulaması aynı kalır ...

    # Yerel kayıt yerine Cloudinary'ye yükle
    result = cloudinary.uploader.upload(
        file,
        folder="halisaha/receipts",
        resource_type="auto",      # PDF ve görsel destekler
        allowed_formats=["pdf", "jpg", "jpeg", "png"],
        max_bytes=5*1024*1024
    )
    return result['secure_url']  # HTTPS URL döner
```

**Model değişikliği:**
```python
# receipt_filename yerine receipt_url
receipt_url = db.Column(db.String(500), nullable=False)
# image_filename yerine image_url
image_url = db.Column(db.String(500), nullable=False)
```

### Alternatif: AWS S3 (Daha profesyonel, karmaşık kurulum)

```bash
pip install boto3
```

Eğer üniversitenin AWS hesabı varsa S3 tercih edilebilir. Yoksa Cloudinary daha pratik.

### Alternatif: Supabase Storage (Ücretsiz, PostgreSQL ile birlikte)

Supabase hem PostgreSQL hem de dosya storage sunar. İki ihtiyacı tek platformda çözer.

---

## 4. ÜNİVERSİTE ORTAMI İÇİN SERTLEŞTİRME

Bu sistem üniversite öğrencilerine açık olacak ve hack denemeleri beklenmelidir. Aşağıdaki ek önlemler alınmalıdır:

### 4.1 Web Application Firewall (WAF)

**Cloudflare (Ücretsiz Plan):**
- DDoS koruması
- Bot engelleme
- Rate limiting (ek katman)
- SSL termination
- IP bazlı engelleme

**Kurulum:** Domain'i Cloudflare nameserver'larına yönlendir → Proxy modunu aç

### 4.2 Veritabanı Güvenliği

```python
# Veritabanı kullanıcısı minimum yetkide olmalı
# PostgreSQL'de:
CREATE USER halisaha_app WITH PASSWORD 'guclu_sifre';
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO halisaha_app;
-- DROP, ALTER, CREATE yetkisi VERİLMEMELİ
```

### 4.3 Loglama ve İzleme

```python
import logging
from logging.handlers import RotatingFileHandler

# Dosya bazlı log
handler = RotatingFileHandler('security.log', maxBytes=10*1024*1024, backupCount=5)
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s [%(remote_addr)s] %(message)s'
))

# Loglanması gerekenler:
# - Tüm başarısız giriş denemeleri (IP, username, zaman)
# - Rate limit ihlalleri
# - Geçersiz CSRF token denemeleri
# - 500 hataları
# - Şüpheli input pattern'leri
```

### 4.4 IP Bazlı Koruma (Opsiyonel)

Eğer sadece üniversite kampüsünden erişilecekse:
```python
ALLOWED_IP_RANGES = ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']

@app.before_request
def check_ip():
    # Admin paneli sadece kampüs IP'lerinden
    if request.path.startswith('/admin') or request.path == '/login':
        from ipaddress import ip_address, ip_network
        client_ip = ip_address(request.remote_addr)
        if not any(client_ip in ip_network(r) for r in ALLOWED_IP_RANGES):
            abort(403)
```

### 4.5 Honeypot Formu (Bot Tespiti)

Rezervasyon formuna görünmez bir alan ekle:
```html
<!-- CSS ile gizle, botlar dolduracak -->
<input type="text" name="website" style="display:none" tabindex="-1" autocomplete="off">
```

```python
# Sunucu tarafı:
if request.form.get('website'):  # Bot doldurdu
    abort(403)
```

### 4.6 CAPTCHA (Önerilen)

Yoğun saldırı durumunda Google reCAPTCHA veya hCaptcha:
- Login formuna ekle
- Rezervasyon formuna ekle
- Rate limit aşıldığında zorunlu kıl

### 4.7 Güvenli Deployment Kontrol Listesi

```
Production .env dosyası:
  SECRET_KEY=<64+ karakter random string>
  DATABASE_URL=postgresql://...
  FLASK_DEBUG=False          ← KESİNLİKLE False
  FLASK_ENV=production
  CLOUDINARY_CLOUD_NAME=...
  CLOUDINARY_API_KEY=...
  CLOUDINARY_API_SECRET=...
  ADMIN_DEFAULT_PASSWORD=<güçlü şifre>
```

---

## 5. YAPILACAKLAR KONTROL LİSTESİ

### Acil (Deploy Öncesi)

- [ ] `FLASK_DEBUG=False` yap (KRİTİK — RCE riski)
- [ ] SECRET_KEY fallback'i kaldır, zorunlu yap
- [ ] Varsayılan şifreyi env variable'dan al
- [ ] Open redirect düzelt (`urlparse` ile doğrula)
- [ ] Güvenlik header'larını ekle (X-Frame-Options, CSP, HSTS vb.)
- [ ] `SESSION_COOKIE_SECURE = True` ekle
- [ ] Duplicate `anti_cache` ve `if __name__` bloklarını sil
- [ ] Konsol print'lerinden şifre bilgisini kaldır

### Yüksek Öncelik (1. Sprint)

- [ ] Sunucu tarafı brute force koruması ekle (LoginAttempt tablosu)
- [ ] Rate limiter storage'ını Redis'e taşı
- [ ] Input doğrulama ekle (pitch_id, time_slot, customer_name)
- [ ] Dosya yükleme sistemini Cloudinary'ye geçir
- [ ] Dekont erişimini `@login_required` arkasına al
- [ ] Admin şifre değiştirme ekranı ekle

### Orta Öncelik (2. Sprint)

- [ ] Loglama sistemi kur (başarısız girişler, hatalar)
- [ ] Cloudflare WAF yapılandır
- [ ] Honeypot form alanı ekle
- [ ] CAPTCHA entegrasyonu (reCAPTCHA/hCaptcha)
- [ ] Veritabanı kullanıcı yetkilerini sınırla
- [ ] Procfile ve render.yaml oluştur

### Düşük Öncelik (3. Sprint)

- [ ] IP bazlı admin erişim kısıtlaması (kampüs IP)
- [ ] İlk giriş şifre değiştirme zorunluluğu
- [ ] Otomatik güvenlik taraması (CI/CD'ye entegre)
- [ ] Yedekleme stratejisi (DB + dosyalar)
- [ ] Penetrasyon testi tekrarı (düzeltmeler sonrası)

---

## RENDER DEPLOYMENT ADIMLARI

### 1. Gerekli Dosyalar

**Procfile** (proje kökünde):
```
web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2
```

**render.yaml** (proje kökünde):
```yaml
services:
  - type: web
    name: halisaha-rez
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2
    envVars:
      - key: SECRET_KEY
        generateValue: true
      - key: DATABASE_URL
        fromDatabase:
          name: halisaha-db
          property: connectionURI
      - key: FLASK_DEBUG
        value: "False"
      - key: FLASK_ENV
        value: "production"

databases:
  - name: halisaha-db
    plan: free
```

### 2. Deploy Süreci

1. GitHub'a push et
2. Render.com'da "New Web Service" oluştur
3. GitHub repo'sunu bağla
4. Environment variables'ları ayarla
5. Deploy et
6. Custom domain bağla
7. Cloudflare proxy aç

---

*Bu doküman, güvenlik zafiyet raporu ve penetrasyon testi sonuçlarına dayanarak hazırlanmıştır.*
*Tüm düzeltmeler tamamlandıktan sonra ikinci bir penetrasyon testi yapılması önerilir.*
