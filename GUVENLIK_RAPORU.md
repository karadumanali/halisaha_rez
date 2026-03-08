# Halı Saha Rezervasyon Sistemi - Güvenlik Zafiyet Raporu

**Tarih:** 2026-03-08
**Kapsam:** Tam kaynak kodu analizi (app.py, models.py, setup_db.py, templates)
**Yöntem:** Statik kod analizi (white-box)

---

## KRİTİK (Critical)

### 1. Brute Force Koruması Yalnızca Client-Side

**Risk:** KRİTİK
**Konum:** `templates/login.html` satır 194-219, `app.py` satır 274

Giriş denemesi sınırlaması `sessionStorage` ile yapılıyor. Bu tamamen istemci tarafında olup, `curl`, `Burp Suite` veya herhangi bir HTTP istemcisiyle kolayca atlanır.

```javascript
// Sadece sessionStorage'da tutuluyor - kolayca bypass edilir
function getN(){return parseInt(sessionStorage.getItem('_lt')||'0');}
```

Sunucu tarafında `@limiter.limit("5 per minute")` var ama:
- **Dakikada 5 deneme** hala çok yüksek (saatte 300, günde 7200 deneme)
- Rate limiter **in-memory** storage kullanıyor - sunucu restart'ında sıfırlanır
- Gunicorn ile birden fazla worker kullanılırsa her worker'ın kendi belleği olur, limit paylaşılmaz

**PoC:**
```bash
# Client-side koruma olmadan sonsuz deneme
for i in $(seq 1 1000); do
  curl -s -X POST http://target/login \
    -d "username=yonetici&password=deneme${i}&csrf_token=TOKEN"
done
```

---

### 2. Hardcoded Varsayılan Kimlik Bilgileri

**Risk:** KRİTİK
**Konum:** `app.py` satır 506, `setup_db.py` satır 15

```python
hashed_password = generate_password_hash("halisaha123", method='pbkdf2:sha256')
yeni_admin = Admin(username='yonetici', password_hash=hashed_password)
```

Varsayılan kullanıcı adı ve şifre kaynak kodda açık yazılı. Değiştirilmesi için UI'da bir mekanizma yok. Bu, GitHub'da public bir repoya push edilirse anında istismar edilebilir.

---

### 3. SECRET_KEY Hardcoded Fallback

**Risk:** KRİTİK
**Konum:** `app.py` satır 38

```python
_secret = os.getenv('SECRET_KEY') or 'GECICI-DEV-KEY-CANLI-ORTAMDA-DEGISTIR-99887766'
```

`.env` dosyası yoksa veya `SECRET_KEY` tanımlı değilse, bilinen bir sabit anahtar kullanılıyor. Bu anahtarla:
- Session cookie'leri taklit edilebilir (session forgery)
- CSRF token'ları üretilebilir
- Admin olarak giriş yapılabilir

---

## YÜKSEK (High)

### 4. Hesap Kilitleme Mekanizması Yok

**Risk:** YÜKSEK
**Konum:** `app.py` satır 273-291

Sunucu tarafında başarısız giriş denemelerini takip eden ve belirli bir eşikten sonra hesabı kilitleyen bir mekanizma yok. Rate limit atlandığında (örn. farklı IP'ler, sunucu restart) sınırsız deneme yapılabilir.

---

### 5. Open Redirect Zafiyeti

**Risk:** YÜKSEK
**Konum:** `app.py` satır 285-287

```python
next_page = request.args.get('next')
if next_page and next_page.startswith('/'):
    return redirect(next_page)
```

`startswith('/')` kontrolü `//evil.com` gibi protocol-relative URL'leri engellemez:

```
http://target/login?next=//evil.com/phishing
```

Başarılı girişten sonra kullanıcı saldırganın sitesine yönlendirilir.

---

### 6. Eksik Güvenlik Header'ları

**Risk:** YÜKSEK
**Konum:** `layout.html`, `app.py`

Aşağıdaki güvenlik header'ları eksik:
- `Content-Security-Policy` — XSS koruması
- `X-Frame-Options` / `frame-ancestors` — Clickjacking koruması
- `X-Content-Type-Options: nosniff` — MIME sniffing koruması
- `Strict-Transport-Security` — HTTPS zorlaması
- `Referrer-Policy` — Bilgi sızıntısı
- `Permissions-Policy` — Tarayıcı API kısıtlaması

---

### 7. SESSION_COOKIE_SECURE Eksik

**Risk:** YÜKSEK
**Konum:** `app.py` satır 42-47

```python
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# SESSION_COOKIE_SECURE = True YOK!
```

HTTPS kullanılsa bile cookie'ler HTTP üzerinden de gönderilebilir. Man-in-the-middle saldırısıyla session çalınabilir.

---

## ORTA (Medium)

### 8. time_slot Doğrulaması Eksik

**Risk:** ORTA
**Konum:** `app.py` satır 210

```python
time_slot = request.form.get('time_slot')
```

`time_slot` değeri sunucu tarafındaki `SLOTS` listesine karşı doğrulanmıyor. Saldırgan rastgele string gönderebilir ve veritabanına beklenmeyen veriler kaydedilir.

---

### 9. pitch_id Tür Doğrulaması Eksik

**Risk:** ORTA
**Konum:** `app.py` satır 208, 185

`pitch_id` integer olarak doğrulanmıyor. Geçersiz değerler veritabanı sorgularında hatalara neden olabilir.

---

### 10. Rate Limiter In-Memory Storage

**Risk:** ORTA
**Konum:** `app.py` satır 63-67

```python
limiter = Limiter(
    get_remote_address, app=app,
    storage_uri="memory://",
    ...
)
```

- Sunucu restart'ında tüm limitler sıfırlanır
- Birden fazla Gunicorn worker'da limitler paylaşılmaz
- Redis veya benzeri harici storage kullanılmalı

---

### 11. customer_name Sanitizasyonu Eksik

**Risk:** ORTA
**Konum:** `app.py` satır 211

`customer_name` yalnızca form'dan alınıp doğrudan veritabanına yazılıyor. Uzunluk kontrolü, özel karakter kontrolü yok. Model'de `String(100)` limiti DB seviyesinde var ama uygulama seviyesinde doğrulama eksik.

---

### 12. Bilgi Sızıntısı - Konsol Çıktıları

**Risk:** ORTA
**Konum:** `app.py` satır 32-34, `setup_db.py` satır 19

```python
print("TEST - SECRET_KEY:", "BULUNDU" if os.getenv('SECRET_KEY') else "BULUNAMADI!")
```

```python
print("Yönetici hesabı eklendi! (Kullanıcı adı: yonetici, Şifre: halisaha123)")
```

Üretim ortamında log dosyalarına kimlik bilgileri yazılıyor.

---

### 13. Yüklenen Dekontlara Doğrudan Erişim

**Risk:** ORTA
**Konum:** `app.py` satır 50

`static/uploads/receipts/` klasörü Flask'in statik dosya sunucusu tarafından doğrudan erişilebilir. Dosya adları UUID olsa da, bilinen bir UUID ile herhangi biri ödeme dekontuna erişebilir. Kimlik doğrulama kontrolü yok.

---

## DÜŞÜK (Low)

### 14. Duplicate Fonksiyon Tanımı

**Konum:** `app.py` satır 475-491

`anti_cache` fonksiyonu iki kez tanımlanmış. İkincisi birincisini ezer. İşlevsel sorun yok ama kod kalitesi sorunu.

---

### 15. Duplicate `if __name__` Bloğu

**Konum:** `app.py` satır 515-522

İki kez tanımlı. İkincisi ilkini ezer.

---

### 16. setup_db.py `drop_all()` Riski

**Konum:** `setup_db.py` satır 7

```python
db.drop_all()
```

Yanlışlıkla çalıştırılırsa tüm veriler silinir. Üretim ortamında bu dosya erişilebilir olmamalı.

---

### 17. Şifre Değiştirme Mekanizması Yok

Admin panelinde şifre değiştirme özelliği bulunmuyor. Varsayılan şifre sonsuza dek kullanılmaya devam eder.

---

### 18. Stored XSS Potansiyeli - blockReason

**Konum:** `templates/index.html` satır 540

```javascript
alert('Bu saat dilimi şu sebeple kilitlidir:\n\n' + blockReason);
```

`blockReason` admin tarafından giriliyor ve `alert()` içinde kullanılıyor. Admin hesabı ele geçirilirse zararlı içerik eklenebilir.

---

## ÖZET TABLOSU

| # | Zafiyet | Seviye | OWASP Kategori |
|---|---------|--------|----------------|
| 1 | Brute Force - Client-Side Koruma | KRİTİK | A07:2021 - Identification & Auth |
| 2 | Hardcoded Kimlik Bilgileri | KRİTİK | A07:2021 - Identification & Auth |
| 3 | SECRET_KEY Hardcoded Fallback | KRİTİK | A02:2021 - Cryptographic Failures |
| 4 | Hesap Kilitleme Yok | YÜKSEK | A07:2021 - Identification & Auth |
| 5 | Open Redirect | YÜKSEK | A01:2021 - Broken Access Control |
| 6 | Eksik Güvenlik Header'ları | YÜKSEK | A05:2021 - Security Misconfiguration |
| 7 | SESSION_COOKIE_SECURE Eksik | YÜKSEK | A05:2021 - Security Misconfiguration |
| 8 | time_slot Doğrulama Eksik | ORTA | A03:2021 - Injection |
| 9 | pitch_id Tür Doğrulama Eksik | ORTA | A03:2021 - Injection |
| 10 | Rate Limiter In-Memory | ORTA | A05:2021 - Security Misconfiguration |
| 11 | customer_name Sanitizasyonu | ORTA | A03:2021 - Injection |
| 12 | Konsol Bilgi Sızıntısı | ORTA | A09:2021 - Security Logging |
| 13 | Dekontlara Açık Erişim | ORTA | A01:2021 - Broken Access Control |
| 14-18 | Çeşitli düşük seviye bulgular | DÜŞÜK | Çeşitli |

---

## OLUMLU BULGULAR

Uygulamada doğru yapılmış güvenlik önlemleri:

- CSRF koruması aktif (Flask-WTF CSRFProtect)
- Şifreler pbkdf2:sha256 ile hashleniyor
- Dosya yüklemelerinde MIME type + extension çift doğrulama
- UUID ile dosya adı randomizasyonu (path traversal önlenir)
- SQLAlchemy ORM kullanımı (SQL injection koruması)
- Jinja2 auto-escaping (XSS koruması)
- SESSION_COOKIE_HTTPONLY aktif
- SESSION_COOKIE_SAMESITE = 'Lax'
- Pillow ile görsel yeniden işleme (image bomb koruması)
- MAX_CONTENT_LENGTH limiti (5MB)

---

---
---

# BÖLÜM 2: PENETRASYON TESTİ RAPORU

**Tarih:** 2026-03-08
**Hedef:** `http://127.0.0.1:5000`
**Yöntem:** Dinamik analiz (black-box / gray-box) — curl ile aktif test

---

## TEST 1: BRUTE FORCE / RATE LIMITING — /login

**Komut:**
```bash
# CSRF token al
curl -c jar GET /login → csrf_token parse
# 12 ardışık login denemesi
curl -b jar POST /login -d "csrf_token=...&username=yonetici&password=wrongN" (x12)
```

**Sonuç:**
- Deneme 1-2: HTTP 200 (hatalı giriş mesajı)
- Deneme 3-12: HTTP 429 (rate limit devreye girdi)
- GET isteği de sayaça dahil edildiğinden, beklenen 5 yerine ~2 POST'tan sonra kilitlendi

**Karar: PASS** — Sunucu tarafı rate limiting çalışıyor (ancak GET istekleri de sayılıyor).

---

## TEST 2: OPEN REDIRECT — /login?next=

**Komut:**
```bash
curl -D- POST "http://target/login?next=//evil.com" \
  -d "csrf_token=...&username=yonetici&password=halisaha123"
```

**Sonuç:**
- `next=//evil.com` → **HTTP 302, Location: //evil.com** — DOGRULANDI
- `next=/\evil.com` → HTTP 400 (engellendi)

**Kök neden** (app.py satır 288):
```python
if next_page and next_page.startswith('/'):
    return redirect(next_page)
```
`//evil.com` kontrolü geçer çünkü `/` ile başlar. Tarayıcılar bunu protocol-relative URL olarak yorumlar.

**Karar: FAIL — OPEN REDIRECT ZAFİYETİ DOĞRULANDI**

---

## TEST 3: CSRF TOKEN DOĞRULAMA

**Komut:**
```bash
curl POST /reserve (csrf_token yok)
curl POST /reserve -d "csrf_token=SAHTE_TOKEN_12345&..."
```

**Sonuç:**
- Token eksik: HTTP 400 — "The CSRF token is missing."
- Geçersiz token: HTTP 400 — "The CSRF session token is missing."

**Karar: PASS** — Flask-WTF CSRFProtect düzgün çalışıyor.

---

## TEST 4: INPUT VALIDATION — /reserve

| Girdi | Doğrulama | Durum |
|-------|-----------|-------|
| customer_phone | Regex `^05\d{9}$` | PASS |
| customer_email | Regex kontrolü | PASS |
| date | strptime + geçmiş tarih kontrolü | PASS |
| receipt dosyası | MIME type + uzantı + yeniden işleme | PASS |
| **pitch_id** | **YOK — doğrudan DB'ye gider** | **FAIL** |
| **time_slot** | **Format kontrolü yok** | **FAIL** |
| **customer_name** | **Uzunluk/sanitizasyon yok** | **FAIL** |

- `time_slot="99:99 - 100:00"` → HTTP 302 (kabul edildi, doğrulama hatası yok)
- `pitch_id="abc"` → HTTP 500 (DB hatası)
- `customer_name="<script>alert(1)</script>"` → Veritabanına ham olarak kaydedilir (Jinja2 auto-escape çıktıda korur)
- 250 karakterlik `customer_name` → Uzunluk kontrolü olmadan kabul edildi

**Karar: FAIL** — pitch_id, time_slot ve customer_name doğrulamaları eksik.

---

## TEST 5: DİZİN ERİŞİM TESTİ

**Komut:**
```bash
curl http://target/static/uploads/receipts/
curl http://target/static/uploads/pitches/
```

**Sonuç:** Her ikisi de HTTP 404 — dizin listeleme kapalı.

**Karar: PASS** — Dizin taraması engellenmiş. UUID dosya adları tahmin edilmeyi zorlaştırıyor.

---

## TEST 6: SESSION GÜVENLİĞİ

**Cookie analizi:**
```
Set-Cookie: session=...; HttpOnly; Path=/; SameSite=Lax
```

| Özellik | Mevcut | Durum |
|---------|--------|-------|
| HttpOnly | Evet | PASS |
| SameSite=Lax | Evet | PASS |
| **Secure** | **Hayır** | **FAIL** |
| Path=/ | Evet | OK |

**Karar: PARTIAL FAIL** — `Secure` flag eksik. Cookie HTTP üzerinden de gönderilir.

---

## TEST 7: GÜVENLİK HEADER'LARI

**GET / yanıt header'ları:**
```
Server: Werkzeug/3.0.4 Python/3.8.12
Cache-Control: no-cache, no-store, must-revalidate, max-age=0
```

| Header | Mevcut | Durum |
|--------|--------|-------|
| X-Frame-Options | **EKSİK** | **FAIL** (clickjacking riski) |
| X-Content-Type-Options | **EKSİK** | **FAIL** (MIME sniffing riski) |
| Content-Security-Policy | **EKSİK** | **FAIL** |
| Strict-Transport-Security | **EKSİK** | **FAIL** |
| Referrer-Policy | **EKSİK** | **FAIL** |
| Permissions-Policy | **EKSİK** | **FAIL** |
| Server (versiyon ifşası) | Var | **FAIL** (bilgi sızıntısı) |
| Cache-Control | Var | PASS |

**Karar: FAIL** — Tüm standart güvenlik header'ları eksik. Sunucu versiyonu ifşa ediliyor.

---

## TEST 8: BİLGİ İFŞASI (Information Disclosure)

| Test | Sonuç | Durum |
|------|-------|-------|
| GET /admin (auth yok) | 302 → /login | PASS |
| Var olmayan route | 404 genel sayfa | PASS |
| /busy_slots geçersiz pitch_id | **500 + TAM STACK TRACE** | **CRITICAL FAIL** |
| /console endpoint | **HTTP 200 — Etkileşimli Python konsolu** | **CRITICAL FAIL** |

**KRİTİK BULGU:** `FLASK_DEBUG=True` olduğunda Werkzeug interaktif debugger etkinleşir:
- Hata sayfalarında tam SQL sorguları, tablo/sütun adları, dosya yolları görünür
- **`/console` endpoint'inden kimlik doğrulaması olmadan Python kodu çalıştırılabilir (RCE)**
- Debugger secret'ı hata sayfasında açık: `SECRET = "ZKP1hLwtQC8ooI8Lz8sl"`

**Karar: CRITICAL FAIL** — Debug mode üretimde açık olmamalı. RCE riski var.

---

## TEST 9: RATE LIMITING — /reserve

**Yapılandırma:** `3 per minute` (app.py satır 208)

**Sonuç:** 3 istekten sonra HTTP 429 döndü.

**Karar: PASS** — Rate limiting çalışıyor.

---

## TEST 10: BUSY SLOTS API — /busy_slots

| Test | URL | Durum | Sonuç |
|------|-----|-------|-------|
| SQL injection | `?pitch_id=1 OR 1=1` | **500** | Stack trace + debugger |
| Non-integer | `?pitch_id=abc` | **500** | Stack trace + debugger |
| SQL injection #2 | `?pitch_id=1';DROP TABLE--` | **500** | Stack trace + debugger |
| Geçersiz tarih | `?pitch_id=1&date=NOT-A-DATE` | 200 | Boş JSON |
| Parametre yok | `/busy_slots` | 200 | Boş JSON |
| Negatif id | `?pitch_id=-1` | 200 | Boş JSON |

**Not:** SQLAlchemy parameterized query kullandığı için gerçek SQL injection (veri çalma/değiştirme) **mümkün değil**. Ancak doğrulama eksikliği debugger'ı tetikleyen hatalara yol açıyor.

**Karar: FAIL** — pitch_id input doğrulaması yok, hata sayfaları bilgi sızdırıyor.

---

## PENETRASYON TESTİ GENEL SONUÇ TABLOSU

| # | Önem | Bulgu | Konum |
|---|------|-------|-------|
| 1 | **KRİTİK** | Werkzeug interaktif debugger (RCE) | `FLASK_DEBUG=True`, `/console` |
| 2 | **KRİTİK** | Debugger secret hata sayfalarında ifşa | 500 hata yanıtları |
| 3 | **YÜKSEK** | Open redirect `//evil.com` ile bypass | app.py satır 288 |
| 4 | **YÜKSEK** | Stack trace + SQL sorgu ifşası | /busy_slots geçersiz girdi |
| 5 | **ORTA** | Tüm güvenlik header'ları eksik | Tüm yanıtlar |
| 6 | **ORTA** | Sunucu versiyon ifşası | `Server: Werkzeug/3.0.4 Python/3.8.12` |
| 7 | **ORTA** | pitch_id / time_slot doğrulama eksik | /reserve, /busy_slots |
| 8 | **DÜŞÜK** | Session cookie Secure flag eksik | Set-Cookie header |

**Geçen Testler:** CSRF koruması, rate limiting (login + reserve), dizin taraması engeli, admin erişim kontrolü, dosya yükleme doğrulaması.

---

*Bu rapor yetkili penetrasyon testi kapsamında hazırlanmıştır. Tüm testler yerel ortamda (127.0.0.1) gerçekleştirilmiştir.*
