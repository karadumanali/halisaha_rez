# ⚽ AYBÜ SKS Spor Tesisleri — Halı Saha Rezervasyon Sistemi

Ankara Yıldırım Beyazıt Üniversitesi Sağlık Kültür ve Spor Daire Başkanlığı için geliştirdiğimiz halı saha rezervasyon ve yönetim sistemi.

## 📋 Proje Hakkında

Öğrencilerin ve personelin üniversite halı sahalarını online olarak rezerve edebildiği, yöneticilerin tek panelden tüm süreçleri yönetebildiği bir web uygulamasıdır.

### Kullanıcı (Öğrenci/Personel) Tarafı
- Tarih ve saha seçerek müsait saatleri görme
- 3 adımlı rezervasyon sihirbazı (tarih → saat → ödeme)
- Ödeme dekontu yükleme (PDF/JPG/PNG)
- E-posta ile onay bildirimi alma

### Yönetici (Admin) Tarafı
- Rezervasyon onaylama / reddetme
- Saha ekleme, fiyat güncelleme, silme
- Slot kilitleme (bakım, turnuva vb.)
- Günlük PDF rapor indirme
- Denetim kayıtları (audit log)
- Şifre değiştirme (güçlü şifre politikası)

---

## 🛡️ Güvenlik Özellikleri

Bu proje güvenlik odaklı geliştirilmiştir. Uygulanan önlemler:

| Önlem | Açıklama |
|-------|----------|
| **Argon2id Hash** | Şifreler en güçlü hash algoritması ile saklanır |
| **CSRF Koruması** | Tüm POST formlarında Flask-WTF token kontrolü |
| **CSP Nonce** | Her istekte benzersiz nonce ile XSS engellenir |
| **Brute-Force Kilitleme** | 5 başarısız deneme → 15 dk hesap kilidi (IP + kullanıcı bazlı) |
| **Timing-Safe Login** | DUMMY_HASH ile kullanıcı adı tespiti engellenir |
| **Session Token** | Her girişte yeni token — çoklu cihaz oturumu engeli |
| **Rate Limiting** | Rezervasyon: 3/dk, Login: 3/dk, PDF: 10/dk |
| **IP Whitelist** | Admin paneline sadece belirli IP'lerden erişim |
| **reCAPTCHA v3** | Google bot koruması (opsiyonel) |
| **Honeypot** | Gizli form alanı ile bot tespiti |
| **ProxyFix** | X-Forwarded-For spoofing önlemi |
| **CORS Kısıtlama** | Cross-origin veri okuma engeli |
| **Güvenlik Header'ları** | X-Frame-Options, HSTS, nosniff, Referrer-Policy |
| **MIME Doğrulama** | Magic bytes ile gerçek dosya tipi kontrolü |
| **Dosya Adı Güvenliği** | UUID ile rastgele dosya adı + regex whitelist |
| **Audit Log** | Tüm admin işlemleri denetim kaydında |
| **Otomatik Temizlik** | Süresi dolan rezervasyonlar ve kilitler otomatik kapatılır |

---

## 📁 Proje Yapısı

```
halisaha_rez/
├── app.py                  # Ana uygulama (rotalar, güvenlik, iş mantığı)
├── models.py               # Veritabanı modelleri (SQLAlchemy)
├── setup_db.py             # Veritabanı kurulum scripti
├── .env.example            # Ortam değişkenleri şablonu
├── .env                    # Gerçek ayarlar (Git'e PUSHLANMAZ)
├── .gitignore
├── requirements.txt
│
├── templates/
│   ├── layout.html         # Ana şablon (navbar, footer, CSS)
│   ├── index.html          # Rezervasyon sayfası (3 adımlı wizard)
│   ├── admin.html          # Yönetici paneli (5 tab)
│   ├── login.html          # Admin giriş sayfası
│   └── error.html          # Hata sayfası (404, 500, 429, 403)
│
├── static/
│   └── uploads/
│       ├── site_logo.png   # Site logosu
│       └── pitches/        # Saha resimleri
│
└── uploads/
    └── receipts/           # Ödeme dekontları (admin erişimli)
```

---

## 🚀 Kurulum

### Gereksinimler

- Python 3.10 veya üstü
- PostgreSQL 15 veya üstü (production) / SQLite (test)
- pip (Python paket yöneticisi)

### 1. Projeyi İndirin

```bash
git clone https://github.com/KULLANICI_ADINIZ/halisaha_rez.git
cd halisaha_rez
```

### 2. Sanal Ortam Oluşturun

```bash
python -m venv .venv

# Windows:
.venv\Scripts\activate

# Linux/Mac:
source .venv/bin/activate
```

### 3. Bağımlılıkları Kurun

```bash
pip install -r requirements.txt
```

### 4. Ortam Değişkenlerini Ayarlayın

```bash
# Şablon dosyayı kopyalayın
cp .env.example .env

# .env dosyasını açıp değerleri doldurun
# En az şu 3 satır ZORUNLU:
#   SECRET_KEY=...
#   DATABASE_URL=...
#   FLASK_ENV=...
```

**SECRET_KEY üretmek için:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Veritabanını Oluşturun

```bash
python setup_db.py
```

> ⚠️ Terminalde çıkan admin şifresini not alın! Bir daha gösterilmez.

### 6. Uygulamayı Başlatın

```bash
# Geliştirme (development):
python app.py

# Tarayıcıda açın: http://127.0.0.1:5000
```

---

## 🏭 Production Kurulumu

Development sunucusu (`python app.py`) production'da kullanılmaz. Gerçek ortam için:

### 1. .env Dosyasını Production İçin Ayarlayın

```env
SECRET_KEY=cok_uzun_rastgele_bir_anahtar
DATABASE_URL=postgresql://user:pass@localhost:5432/halisaha
FLASK_ENV=production
PROXY_COUNT=1
ALLOWED_ADMIN_IPS=sunucu_ip_adresi
```

### 2. Gunicorn ile Çalıştırın

```bash
pip install gunicorn
gunicorn -w 4 -b 127.0.0.1:8000 app:app
```

### 3. Nginx Yapılandırması

```nginx
server {
    listen 80;
    server_name halisaha.aybu.edu.tr;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /path/to/halisaha_rez/static/;
        expires 30d;
    }
}
```

### 4. SSL Sertifikası (HTTPS)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d halisaha.aybu.edu.tr
```

---

## 📊 Veritabanı Şeması

```
admins              → Yönetici hesapları
pitches             → Halı sahalar (ad, fiyat)
pitch_images        → Saha resimleri
reservations        → Rezervasyon talepleri (Pending/Approved/Rejected/Expired)
blocked_slots       → Kilitli saat dilimleri
login_attempts      → Giriş denemeleri (brute-force koruması)
audit_logs          → Denetim kayıtları (tüm admin işlemleri)
```

---

## ⏰ Otomatik İşlemler

Sistem arka planda şu işlemleri otomatik yapar:

| İşlem | Zamanlama | Açıklama |
|-------|-----------|----------|
| Rezervasyon süre dolumu | Her saat başı + admin panel açılışı | Tarihi geçmiş bekleyen rezervasyonları "Expired" yapar, müşteriye mail gönderir |
| Slot kilidi temizleme | Her saat başı + admin panel açılışı | Tarihi geçmiş slot kilitlerini otomatik kaldırır |
| Login kaydı temizleme | Ayın 1'i, saat 03:00 | 30 günden eski giriş denemelerini siler |
| Audit log temizleme | Ayın 1'i, saat 03:00 | 1 yıldan eski denetim kayıtlarını siler |

---

## 🔑 Varsayılan Giriş

İlk kurulumda `setup_db.py` terminalde admin bilgilerini gösterir:

```
════════════════════════════════════════════════════════
  YENİ ADMİN HESABI OLUŞTURULDU
  Kullanıcı adı : yonetici
  Şifre         : [rastgele 20 karakter]
  !! Giriş yapıp şifrenizi hemen değiştirin !!
════════════════════════════════════════════════════════
```

> ⚠️ İlk girişten sonra şifreyi hemen değiştirin. Şifre politikası: en az 10 karakter, büyük harf, küçük harf, rakam ve özel karakter zorunlu.

---

## 🛠️ Teknolojiler

| Katman | Teknoloji |
|--------|-----------|
| Backend | Python 3, Flask, SQLAlchemy, Flask-Login |
| Veritabanı | PostgreSQL / SQLite |
| Frontend | Jinja2, Bootstrap 5, Vanilla JavaScript |
| Güvenlik | Argon2id, Flask-WTF (CSRF), Flask-Limiter, CSP Nonce |
| PDF | ReportLab |
| Zamanlama | APScheduler |
| E-posta | smtplib (Gmail SMTP) |

---

## 📝 Lisans

Bu proje MIT lisansı altında yayınlanmıştır. Detaylar için [LICENSE](LICENSE) dosyasına bakın.

---

## 👥 Geliştiriciler

Fatih Muaz EKİNCİ -
Ali KARADUMAN -
Mustafa AYYILDIZ

---

<p align="center">
  <strong>⚽ AYBÜ SKS Spor Tesisleri Rezervasyon Sistemi</strong><br>
  <em>Güvenlik öncelikli, modern, kullanıcı dostu</em>
</p>
