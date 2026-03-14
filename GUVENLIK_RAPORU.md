# AYBÜ Hali Saha Rezervasyon Sistemi - Guvenlik Analiz Raporu

**Tarih:** 2026-03-14
**Kapsam:** Tum codebase (`app.py`, `models.py`, `setup_db.py`, templates, static, CI/CD)
**Uygulama:** Flask 3.1.2 + PostgreSQL + Redis

---

## GENEL DEGERLENDIRME

Uygulama guvenlik acisindan **iyi seviyede** tasarlanmis. Brute force korumasi, CSRF, rate limiting, dosya upload guvenligi, SQL injection korumasi ve guvenlik header'lari duzgun uygulanmis. Ancak birkac onemli bulgu mevcut.

---

## KRITIK BULGULAR

### 1. Hardcoded Varsayilan Admin Kimlik Bilgileri

| | |
|---|---|
| **Dosya** | `app.py:823-830`, `setup_db.py:15-18` |
| **Risk** | YUKSEK |
| **Detay** | Kullanici adi `yonetici`, sifre `halisaha123` kaynak kodda acik metin olarak bulunuyor. Uygulama ilk calistiginda bu kimlik bilgileriyle otomatik admin hesabi olusturuluyor. |
| **Etki** | Kaynak koda erisen herkes varsayilan sifreyi bilir. Sifre degistirilmemisse dogrudan admin paneline erisim saglanir. |
| **Oneri** | Ilk calistirmada rastgele sifre uretip konsola/log'a yazdirmak veya environment variable'dan almak. |

### 2. CSP'de `unsafe-inline` Kullanimi

| | |
|---|---|
| **Dosya** | `app.py:793-803` |
| **Risk** | YUKSEK |
| **Detay** | Content Security Policy'de hem `script-src` hem `style-src` direktiflerinde `'unsafe-inline'` var. Bu, CSP'nin XSS'e karsi sagladigi korumayi buyuk olcude zayiflatir. |
| **Oneri** | Nonce tabanli CSP'ye gecilmeli. Inline script ve style'lar harici dosyalara tasinmali veya nonce attribute ile isaretlenmeli. |

---

## ORTA SEVIYE BULGULAR

### 3. Tek Admin Kullanici / Rol Tabanli Erisim Yok

| | |
|---|---|
| **Dosya** | `models.py:9-17` |
| **Risk** | ORTA |
| **Detay** | Sistemde tek bir admin kullanici tipi var. Farkli yetki seviyeleri (orn: sadece goruntuleme, sadece onay) tanimlanamiyoyr. |
| **Etki** | Admin sifresi ele gecirilirse tum sistem fonksiyonlarina erisim saglanir. |
| **Oneri** | Birden fazla admin ve rol sistemi (RBAC) dusunulebilir. |

### 4. IP Kisitlamasi Varsayilan Olarak Kapali

| | |
|---|---|
| **Dosya** | `app.py:189` |
| **Risk** | ORTA |
| **Detay** | `ALLOWED_ADMIN_IPS` environment variable'i bos birakildiginda IP kisitlamasi tamamen devre disi kaliyor. |
| **Oneri** | Production ortaminda bu degiskenin mutlaka ayarlandigindan emin olunmali. Bos oldugunda uyari log'lanmasi dusunulebilir. |

### 5. Rate Limiter Storage Backend

| | |
|---|---|
| **Dosya** | `app.py:77-83` |
| **Risk** | ORTA |
| **Detay** | Redis baglantisi saglanamazsa rate limiter `memory://` fallback'ine dusuyor. Multi-process deployment'ta (gunicorn workers) her worker kendi belleginde sayim tutar, bu da rate limiting'in etkinligini azaltir. |
| **Oneri** | Production'da Redis'in calistigindan emin olunmali. |

---

## DUSUK SEVIYE BULGULAR

### 6. SameSite Cookie Ayari

| | |
|---|---|
| **Dosya** | `app.py:55` |
| **Risk** | DUSUK |
| **Detay** | `SameSite='Lax'` kullaniliyor. `Strict` daha guvenli olur ancak bazi kullanim senaryolarini kisitlayabilir. |

### 7. X-XSS-Protection Header'i Deprecated

| | |
|---|---|
| **Dosya** | `app.py:790` |
| **Risk** | DUSUK |
| **Detay** | `X-XSS-Protection: 1; mode=block` header'i modern tarayicilarda artik desteklenmiyor. CSP zaten bu korumayi sagliyor. |
| **Oneri** | Kaldirilabilir veya `0` olarak ayarlanabilir. |

### 8. Custom Hata Sayfalari Yok

| | |
|---|---|
| **Risk** | DUSUK |
| **Detay** | Custom 404/500 error handler'lari tanimlanmamis. Debug modunda Flask varsayilan hata sayfalari stack trace gosterebilir. |
| **Etki** | Production'da `DEBUG=False` oldugu surece sorun yok. |

---

## BRUTE FORCE ANALIZI

### Mevcut Korumalar

| Mekanizma | Detay | Dosya |
|-----------|-------|-------|
| Rate Limiting | `/login`: 3/dk, 10/saat, 20/gun | `app.py:517` |
| Hesap Kilitleme | 5 basarisiz deneme → 15 dk kilit (IP + kullanici adi bazli) | `app.py:119-145` |
| Timing Attack Korumasi | Olmayan kullanicilar icin dummy hash karsilastirmasi | `app.py:387, 541-543` |
| reCAPTCHA v3 | Login ve rezervasyon formlarinda bot korumasi (skor >= 0.5) | `app.py:239-258` |
| Honeypot | Gizli `website` alani bot tespiti icin | `app.py:426-429` |
| IP Whitelist | Admin sayfalari icin opsiyonel IP kisitlamasi (CIDR destekli) | `app.py:158-230` |
| Login Attempt Logging | Tum giris denemeleri DB'de kayit altinda | `models.py:79-89` |
| Aylik Temizlik | 30 gunden eski login kayitlari otomatik siliniyor | `app.py:98-116` |

### Degerlendirme

Brute force korumasi **kapsamli ve cok katmanli**. Rate limiting + hesap kilitleme + reCAPTCHA + IP kisitlamasi birlikte calisarak guclu bir savunma hatti olusturuyor. Bu alanda ek aksiyon gerekmiyor.

---

## GUVENLIK KONTROL LISTESI

| Kategori | Durum | Notlar |
|----------|:-----:|--------|
| SQL Injection | KORUNUYOR | SQLAlchemy ORM, raw SQL yok |
| XSS | KORUNUYOR | Jinja2 auto-escape aktif |
| CSRF | KORUNUYOR | Flask-WTF CSRFProtect, tum POST formlarda token var |
| Dosya Upload | KORUNUYOR | Magic bytes + extension whitelist + UUID rename + PIL reprocess |
| Path Traversal | KORUNUYOR | `os.path.basename()` + `send_from_directory()` |
| Open Redirect | KORUNUYOR | `safe_redirect()` fonksiyonu scheme/netloc kontrolu yapiyor |
| Command Injection | KORUNUYOR | `subprocess`, `os.system()` kullanilmiyor |
| Session Guvenligi | KORUNUYOR | HttpOnly, SameSite, 30dk timeout, Secure (prod) |
| Sifre Hashleme | KORUNUYOR | pbkdf2:sha256 |
| HTTPS / HSTS | KORUNUYOR | Production'da HSTS header'i aktif |
| Security Headers | KORUNUYOR | X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy |
| Gizli Bilgi Yonetimi | KORUNUYOR | `.env` dosyasi, `.gitignore`'da, `os.getenv()` kullanimi |
| CI/CD Guvenlik Taramasi | KORUNUYOR | Bandit + Safety otomatik tarama (`security.yml`) |
| Rate Limiting | KORUNUYOR | Global (500/gun, 100/saat) + endpoint bazli limitler |
| Input Validation | KORUNUYOR | Isim, telefon, email, tarih, saat, fiyat dogrulamasi |

---

## ONCELIKLI AKSIYON PLANI

### Hemen Yapilmasi Gerekenler
1. Hardcoded admin sifresini kaldir → Environment variable veya rastgele uretim
2. CSP'den `unsafe-inline` kaldir → Nonce tabanli sisteme gec

### Kisa Vadede Yapilmasi Gerekenler
3. IP kisitlamasi bosken production'da uyari log'la
4. Rate limiter'in Redis'e bagli oldugunu dogrula (production)
5. Custom 404/500 hata sayfalari ekle

### Uzun Vadede Dusunulecekler
6. Rol tabanli erisim kontrolu (RBAC)
7. `X-XSS-Protection` header'ini kaldir/guncelle

---

## SONUC

Uygulama OWASP Top 10'un buyuk cogunluguna karsi korunmus durumda. Brute force korumasi ozellikle cok katmanli ve guclu. **En kritik iki aksiyon**: hardcoded admin sifresinin kaldirilmasi ve CSP'deki `unsafe-inline`'in giderilmesi. Bu iki duzeltme yapildiginda uygulama guvenlik seviyesi production icin yeterli olacaktir.
