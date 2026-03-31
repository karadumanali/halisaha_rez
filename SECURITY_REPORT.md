# Güvenlik Taraması & Yapılan Değişiklikler Raporu

**Proje:** AYBÜ SKS Spor Tesisleri — Halisaha Rezervasyon Sistemi
**Tarih:** 2026-03-31
**Genel Güvenlik Puanı:** 7.5 / 10

---

## İçindekiler

1. [Proje Özeti](#1-proje-özeti)
2. [Güvenlik Taraması — Bulunan Açıklar](#2-güvenlik-taraması--bulunan-açıklar)
3. [Güçlü Yönler](#3-güçlü-yönler)
4. [OWASP Top 10 Karşılaştırması](#4-owasp-top-10-karşılaştırması)
5. [Bu Oturumda Yapılan Düzeltmeler](#5-bu-oturumda-yapılan-düzeltmeler)
6. [.env Git Geçmişinden Silme Talimatları](#6-env-git-geçmişinden-silme-talimatları)
7. [Kalan Öneriler](#7-kalan-öneriler)

---

## 1. Proje Özeti

| Özellik | Değer |
|---------|-------|
| Framework | Flask (Python) |
| Veritabanı | PostgreSQL / SQLite |
| Şifreleme | Argon2id (passlib) |
| Oturum Yönetimi | Flask-Login + session token |
| CSRF Koruması | Flask-WTF |
| Rate Limiting | Flask-Limiter |
| Dosya Yükleme | PDF / JPG / PNG (MIME doğrulama) |
| Raporlama | ReportLab (PDF) |
| Arka Plan Görevler | APScheduler |

---

## 2. Güvenlik Taraması — Bulunan Açıklar

### KRİTİK

#### C-01 — `.env` Dosyası Git Deposunda Açık
- **Nerede:** Repo kökü, tüm commit geçmişi
- **Risk:** `SECRET_KEY`, veritabanı şifresi, Gmail uygulama şifresi dışarıya sızdı
- **Durum:** Talimatlar aşağıda verildi → [Bkz. Bölüm 6](#6-env-git-geçmişinden-silme-talimatları)

#### C-02 — Zayıf Veritabanı Şifresi
- **Nerede:** `.env` → `DATABASE_URL`
- **Şifre:** `seng302` (çok kısa, tahmin edilebilir)
- **Durum:** Üniversite altyapısının sorumluluğunda

#### C-03 — reCAPTCHA Production'da Zorunlu Değildi
- **Nerede:** `app.py` → `verify_recaptcha()` fonksiyonu
- **Risk:** `RECAPTCHA_SECRET_KEY` girilmezse bot koruması tamamen devre dışı kalıyordu
- **Durum:** ✅ **Bu oturumda düzeltildi**

---

### YÜKSEK

#### H-01 — reCAPTCHA Ağ Hatasında "Geçir" Diyordu
- **Nerede:** `app.py` → `verify_recaptcha()` → `except` bloğu
- **Risk:** Google'ın sunucusuna ulaşılamazsa her istek otomatik geçiyordu
- **Durum:** ✅ **Bu oturumda düzeltildi** (fail-closed: production'da `False` döner)

#### H-02 — HTTPS Yönlendirmesi Yok
- **Risk:** HTTP üzerinden gelen istekler HTTPS'e yönlendirilmiyor
- **Durum:** Üniversite altyapısının sorumluluğunda (Nginx konfigürasyonu)

#### H-03 — Veritabanı SSL Bağlantısı Yok
- **Risk:** `DATABASE_URL`'de `?sslmode=require` yok
- **Durum:** Üniversite altyapısının sorumluluğunda

---

### ORTA

#### M-01 — CSP İhlalleri Raporlanmıyordu *(Bulgu #8)*
- **Nerede:** `app.py` → `apply_security_headers()` → CSP header
- **Risk:** Tarayıcı XSS girişimlerini veya izinsiz script yüklemelerini tespit etse bile sunucu habersiz kalıyordu
- **Durum:** ✅ **Bu oturumda düzeltildi**

#### M-02 — Denetim Logu Saklama Süresi Kısaydı *(Bulgu #9)*
- **Nerede:** `app.py` → `monthly_cleanup()` fonksiyonu
- **Eski değer:** 365 gün (1 yıl)
- **Risk:** KVKK/GDPR uyumu için yetersiz süre
- **Durum:** ✅ **Bu oturumda düzeltildi** → 730 güne (2 yıl) çıkarıldı

#### M-03 — Admin Şifre Sıfırlama Mekanizması Yok
- **Risk:** Admin şifresi unutulursa sisteme erişim kesilebilir
- **Öneri:** Yedek kurtarma kodu veya alternatif giriş eklenebilir

#### M-04 — CSP İhlal Bildirimleri İzlenmiyor
- **Durum:** `/csp-report` eklendi, loglar `app.log` dosyasına yazılıyor ✅

---

### DÜŞÜK

#### L-01 — `security.txt` Dosyası Yok
- **Öneri:** `/.well-known/security.txt` eklenirse güvenlik araştırmacıları iletişim kurabilir

#### L-02 — Log Uyarı Mekanizması Yok
- Brute-force denemeleri loglanıyor ama eşik aşılınca alarm gitmiyor
- Öneri: E-posta bildirimi eklenebilir

---

## 3. Güçlü Yönler

| # | Uygulama | Açıklama |
|---|----------|----------|
| 1 | Argon2id şifre hash | En güçlü modern algoritma |
| 2 | CSRF koruması | Flask-WTF, tüm formlarda |
| 3 | SQL Injection koruması | SQLAlchemy ORM, parametrik sorgular |
| 4 | XSS koruması | CSP nonce + Jinja2 auto-escape |
| 5 | Brute-force kilidi | 5 deneme → 15 dk kilit |
| 6 | Rate limiting | Login: 3/dk, Reserve: 3/dk |
| 7 | Dosya yükleme güvenliği | MIME byte kontrolü, UUID isimlendirme |
| 8 | Session token rotasyonu | Her login'de yeni token, çıkışta geçersiz |
| 9 | Timing-safe login | Olmayan kullanıcı için DUMMY_HASH |
| 10 | Audit log | Tüm admin işlemleri kayıt altında |
| 11 | Clickjacking koruması | `X-Frame-Options: DENY` |
| 12 | Honeypot bot tuzağı | Gizli `website` alanı |
| 13 | IP whitelist | Admin paneli isteğe bağlı IP kısıtlaması |
| 14 | Çift rezervasyon önlemi | DB UNIQUE constraint ile race condition koruması |
| 15 | Özel hata sayfaları | 404/500/429/403 — sistem bilgisi sızdırılmıyor |
| 16 | bcrypt → Argon2id otomatik yükseltme | Eski hash'ler login'de otomatik güncellenir |
| 17 | Server header kaldırıldı | `response.headers.pop('Server', None)` |
| 18 | Güvenli yönlendirme | `safe_redirect()` ile open-redirect önlemi |

---

## 4. OWASP Top 10 Karşılaştırması

| Zafiyet | Durum | Detay |
|---------|-------|-------|
| A01 — Broken Access Control | ✅ Korumalı | `@login_required`, IP whitelist |
| A02 — Cryptographic Failures | ⚠️ Kısmi | Argon2id var, HTTPS üniversiteye bağlı |
| A03 — SQL Injection | ✅ Korumalı | SQLAlchemy ORM |
| A04 — Insecure Design | ✅ İyi | Rate limit, honeypot, UNIQUE constraint |
| A05 — Security Misconfiguration | ✅ Düzeltildi | reCAPTCHA zorunlu hale getirildi |
| A06 — Vulnerable Components | ⚠️ Takip et | Bağımlılıklar güncel, düzenli kontrol önerilir |
| A07 — Auth & Session Failures | ✅ Korumalı | Token rotasyonu, brute-force kilidi |
| A08 — Software Integrity Failures | ✅ Korumalı | CSP, SRI uygulanmış |
| A09 — Logging & Monitoring | ✅ Düzeltildi | CSP report-uri eklendi, 2 yıl saklama |
| A10 — SSRF | ✅ N/A | Harici istek yapılmıyor |

---

## 5. Bu Oturumda Yapılan Düzeltmeler

### Düzeltme 1 — reCAPTCHA Production'da Zorunlu Hale Getirildi
**Dosya:** `app.py`

**Ne değişti:**
```python
# ÖNCE — reCAPTCHA anahtarı yoksa sessizce geçiyordu
if not RECAPTCHA_SECRET:
    return True

# SONRA — Production'da anahtar yoksa uygulama başlamıyor
if os.getenv('FLASK_ENV') == 'production' and not RECAPTCHA_SECRET:
    raise RuntimeError(
        "RECAPTCHA_SECRET_KEY prodüksiyonda zorunludur. ..."
    )
```

**Ağ hatası için de düzeltildi (fail-closed):**
```python
# ÖNCE — Google'a ulaşılamazsa herkes geçiyordu
except Exception:
    return True

# SONRA — Production'da ağ hatası = reddet
except Exception:
    return os.getenv('FLASK_ENV') != 'production'
```

---

### Düzeltme 2 — CSP İhlal Raporlama Endpoint'i Eklendi *(Bulgu #8)*
**Dosya:** `app.py`

**Eklenen route:**
```python
@app.route('/csp-report', methods=['POST'])
def csp_report():
    # Tarayıcı, izinsiz script/style girişimlerini buraya bildirir
    # İhlaller app.log'a yazılır: blocked-uri, violated-directive, ip
```

**CSP header'ına eklendi:**
```
report-uri /csp-report
```

**Ne işe yarar:** Bir saldırgan XSS ile script enjekte etmeye çalışırsa tarayıcı bunu engeller ve `/csp-report`'a bildirir. Sunucu bunu loglar — saldırı girişimleri izlenebilir hale gelir.

---

### Düzeltme 3 — Denetim Logu Saklama Süresi Uzatıldı *(Bulgu #9)*
**Dosya:** `app.py` → `monthly_cleanup()`

```python
# ÖNCE
audit_cutoff = datetime.now(timezone.utc) - timedelta(days=365)

# SONRA — KVKK/GDPR uyumu için 2 yıl
# V-09: Denetim kayıtları 2 yıl (730 gün) saklanır (KVKK/GDPR uyumu)
audit_cutoff = datetime.now(timezone.utc) - timedelta(days=730)
```

---

## 6. `.env` Git Geçmişinden Silme Talimatları

> **Önemli:** Bu işlem geçmişi yeniden yazar. Remote repo varsa dikkatli ol.

```bash
# Adım 1 — .env'i aktif takipten çıkar (dosya diskte kalır)
git rm --cached .env
git commit -m "chore: .env git takibinden cikarildi"

# Adım 2 — Tüm geçmiş commit'lerden sil
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch .env' \
  --prune-empty --tag-name-filter cat -- --all

# Adım 3 — Temizle
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# Adım 4 — Remote varsa (GitHub/GitLab) zorla gönder
git push origin --force --all
```

> **Not:** Üniversiteye yerel teslim yapılacaksa Adım 1-2 yeterlidir.

---

## 7. Kalan Öneriler

Aşağıdakiler üniversite altyapısına veya teslim sonrasına bırakılmıştır:

| Öncelik | Öneri | Sorumluluk |
|---------|-------|-----------|
| Yüksek | HTTPS / TLS sertifikası | Üniversite sunucusu |
| Yüksek | Veritabanı şifresi güçlendirilmeli | Üniversite DB yöneticisi |
| Yüksek | `DATABASE_URL`'e `?sslmode=require` | Üniversite altyapısı |
| Orta | Admin 2FA (TOTP) | Gelecek geliştirme |
| Orta | Brute-force e-posta alarmı | Gelecek geliştirme |
| Düşük | `/.well-known/security.txt` | Gelecek geliştirme |

---

*Rapor otomatik olarak oluşturulmuştur — 2026-03-31*
