"""
migrate_tracking_code.py — Mevcut veritabanina tracking_code sutununu ekler.

Kullanim:
    python migrate_tracking_code.py

Bu script:
1. reservations tablosuna tracking_code sutununu ekler (yoksa)
2. Mevcut kayitlara benzersiz takip kodu atar
3. UNIQUE index olusturur

Not: Bu scripti uygulama calismazken calistirin.
     Islem geri alinamaz — oncesinde veritabani yedegi alin!
"""

import sqlite3
import secrets
import string
import os
import sys


def generate_tracking_code():
    """Benzersiz takip kodu uret: REZ-XXXX-XXXX formatinda."""
    chars = string.ascii_uppercase + string.digits
    part1 = ''.join(secrets.choice(chars) for _ in range(4))
    part2 = ''.join(secrets.choice(chars) for _ in range(4))
    return f"REZ-{part1}-{part2}"


def migrate(db_path):
    """tracking_code sutununu ekle ve mevcut kayitlari doldur."""

    if not os.path.exists(db_path):
        print(f"HATA: Veritabani bulunamadi: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Sutun var mi kontrol et
    cursor.execute("PRAGMA table_info(reservations)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'tracking_code' in columns:
        print("tracking_code sutunu zaten mevcut.")
    else:
        print("tracking_code sutunu ekleniyor...")
        cursor.execute("ALTER TABLE reservations ADD COLUMN tracking_code VARCHAR(13)")
        print("Sutun eklendi.")

    # Bos kayitlari doldur
    cursor.execute("SELECT id FROM reservations WHERE tracking_code IS NULL OR tracking_code = ''")
    empty_rows = cursor.fetchall()

    if empty_rows:
        print(f"{len(empty_rows)} kayit icin takip kodu uretiliyor...")

        # Mevcut kodlari topla (cakisma onlemi)
        cursor.execute("SELECT tracking_code FROM reservations WHERE tracking_code IS NOT NULL AND tracking_code != ''")
        existing_codes = set(row[0] for row in cursor.fetchall())

        for (row_id,) in empty_rows:
            # Benzersiz kod uret
            code = generate_tracking_code()
            while code in existing_codes:
                code = generate_tracking_code()
            existing_codes.add(code)

            cursor.execute("UPDATE reservations SET tracking_code = ? WHERE id = ?", (code, row_id))

        print(f"{len(empty_rows)} kayit guncellendi.")
    else:
        print("Bos kayit yok, tum kayitlarin takip kodu mevcut.")

    # UNIQUE index olustur (yoksa)
    try:
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_reservations_tracking_code ON reservations (tracking_code)")
        print("UNIQUE index olusturuldu.")
    except sqlite3.OperationalError as e:
        print(f"Index olusturulamadi (muhtemelen zaten var): {e}")

    conn.commit()
    conn.close()
    print("\nMigrasyon tamamlandi!")


if __name__ == '__main__':
    # Varsayilan veritabani yolu
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'halisaha.db')

    # Komut satirindan ozel yol verilebilir
    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    print(f"Veritabani: {db_path}")
    print("-" * 50)
    migrate(db_path)
