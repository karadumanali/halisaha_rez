"""
setup_db.py  —  Veritabani Baslangic Betigi
============================================
KULLANIM:
    python setup_db.py              -> Tablolari siler ve yeniden olusturur
    python setup_db.py --no-drop    -> Tablolari SILMEDEN eksik olanlari olusturur

UYARI:
    Bu betik YALNIZCA ilk kurulum veya sifirlama icin kullanilir.
    Production ortaminda ASLA calistirmayiniz.
"""

import sys
import os
import secrets
import string

# ── Production korumasi ───────────────────────────────────────────────────────
if os.getenv("FLASK_ENV") == "production":
    print("HATA: Bu betik production ortaminda calistirilamaz.")
    print("      FLASK_ENV=production algilandi, islem durduruldu.")
    sys.exit(1)

# ── Uygulama import ───────────────────────────────────────────────────────────
from app import app
from models import db, Admin
from werkzeug.security import generate_password_hash

# ── Parametre ─────────────────────────────────────────────────────────────────
no_drop = "--no-drop" in sys.argv

with app.app_context():

    if no_drop:
        # Mevcut verilere dokunmadan sadece eksik tablolari olustur
        db.create_all()
        print("Tablolar kontrol edildi — mevcut veriler korundu.")

    else:
        # Yanlis calistirmaya karsi onay al
        print("=" * 55)
        print("  UYARI: Tum tablolar ve icindeki VERILER SILINECEK!")
        print("=" * 55)
        onay = input("Devam etmek icin tam olarak  EVET  yazin: ").strip()
        if onay != "EVET":
            print("Iptal edildi. Hicbir degisiklik yapilmadi.")
            sys.exit(0)

        db.drop_all()
        print("Eski tablolar silindi.")
        db.create_all()
        print("Yeni tablolar olusturuldu.")

    # ── Admin hesabi ──────────────────────────────────────────────────────────
    mevcut = Admin.query.filter_by(username="yonetici").first()

    if mevcut:
        print("'yonetici' hesabi zaten mevcut — atlandi.")

    else:
        # Guvenli rastgele sifre — sabit sifre ASLA kullanilmaz
        alfabe    = string.ascii_letters + string.digits + "!@#$%^&*"
        ilk_sifre = "".join(secrets.choice(alfabe) for _ in range(20))

        hashed = generate_password_hash(
            ilk_sifre,
            method="pbkdf2:sha256:600000"
        )
        db.session.add(Admin(username="yonetici", password_hash=hashed))
        db.session.commit()

        print()
        print("=" * 55)
        print("  YENİ ADMİN HESABI OLUSTURULDU")
        print(f"  Kullanici adi : yonetici")
        print(f"  Sifre         : {ilk_sifre}")
        print()
        print("  !! Bu sifreyi simdi bir yere not alin.")
        print("  !! Terminal kapaninca bir daha goremazsiniz.")
        print("  Giris yapip admin panelinden sifreyi degistirin.")
        print("=" * 55)
        print()