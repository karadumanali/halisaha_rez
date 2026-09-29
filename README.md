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
├── cli.py                  # Özel komutlar (flask create-admin)
├── migrations/             # Veritabanı migration dosyaları (Flask-Migrate / Alembic)
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
flask db upgrade        # Tabloları oluşturur / günceller
flask create-admin      # İlk 'yonetici' hesabını oluşturur
```

> ⚠️ Terminalde çıkan admin şifresini not alın! Bir daha gösterilmez.

### 6. Uygulamayı Başlatın

```bash
# Geliştirme (development):
python run.py

# Tarayıcıda açın: http://127.0.0.1:5000
```

---

## 🏭 Production Kurulumu

Development sunucusu (`python run.py`) production'da kullanılmaz. Gerçek ortam için:

### 1. .env Dosyasını Production İçin Ayarlayın

```env
SECRET_KEY=cok_uzun_rastgele_bir_anahtar
DATABASE_URL=postgresql://user:pass@localhost:5432/halisaha
FLASK_ENV=production
PROXY_COUNT=1
ALLOWED_ADMIN_IPS=sunucu_ip_adresi
```

### 2. Veritabanını Kurun

```bash
sudo apt install libmagic1    # Dosya tipi doğrulaması için sistem kütüphanesi (Linux)
pip install -r requirements.txt   # gunicorn + psycopg2 dahil
flask db upgrade              # Tabloları oluşturur
flask create-admin            # İlk admin hesabı (sadece ilk kurulumda)
```

> Her güncellemede (`git pull` sonrası) uygulamayı yeniden başlatmadan önce `flask db upgrade` çalıştırın.

### 3. Gunicorn ile Çalıştırın

```bash
gunicorn -w 1 --threads 4 -b 127.0.0.1:8000 "run:application"
```

> ⚠️ `-w 1` bilinçli olarak tek worker'dır: zamanlanmış görevler (APScheduler) ve rate limiter sayaçları her worker'da ayrı çalışır. Birden fazla worker, müşteriye tekrarlı mail gitmesine ve limitlerin zayıflamasına yol açar. Eşzamanlılık `--threads` ile sağlanır.

### 4. Nginx Yapılandırması

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

### 5. SSL Sertifikası (HTTPS)

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

### Şema Değişikliği (Migration)

Veritabanı şeması [Flask-Migrate](https://flask-migrate.readthedocs.io/) ile yönetilir. `models.py`'de bir değişiklik yaptığınızda:

```bash
flask db migrate -m "rezervasyona not alani eklendi"   # migrations/versions/ altına dosya üretir
# Üretilen dosyayı açıp kontrol edin!
flask db upgrade                                       # Değişikliği veritabanına uygular
```

Üretilen migration dosyasını modelle birlikte commit edin. Sunucuda sadece `flask db upgrade` çalıştırılır.

| Komut | Ne yapar |
|-------|----------|
| `flask db upgrade` | Bekleyen tüm migration'ları uygular |
| `flask db downgrade` | Son migration'ı geri alır |
| `flask db current` | Veritabanının hangi sürümde olduğunu gösterir |
| `flask db check` | Modeller ile veritabanı arasında fark var mı kontrol eder |

> ⚠️ Uygulama açılışta tabloları artık otomatik oluşturmaz. Şema güncel değilse başlangıçta uyarı verir.

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

İlk kurulumda `flask create-admin` terminalde admin bilgilerini gösterir (hesap zaten varsa dokunmaz):

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
  <strong> AYBÜ SKS Spor Tesisleri Rezervasyon Sistemi</strong><br>
  
</p>
