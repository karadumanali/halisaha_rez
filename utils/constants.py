"""
constants.py — Uygulama genelinde kullanılan sabitler.

Tek bir yerde tanımlanır, her yerde import edilir.
Değişiklik yapılacağında sadece burası güncellenir.
"""

# ── Geçerli saat dilimleri ──────────────────────────────────────────

VALID_SLOTS = [
    '15:00 - 16:00',
    '16:00 - 17:00',
    '17:00 - 18:00',
    '18:00 - 19:00',
    '19:00 - 20:00',
    '20:00 - 21:00',
    '21:00 - 22:00',
]

# ── Admin panelinde seçilebilen saat aralıkları ─────────────────────
# (grup adı, ikon, başlangıç saatleri) — her saat 1 saatlik slottur.

SLOT_GROUPS = [
    ('Sabah',         'fa-sun',       list(range(8, 12))),
    ('Öğleden Sonra', 'fa-cloud-sun', list(range(12, 17))),
    ('Akşam',         'fa-moon',      list(range(17, 24))),
]
SLOT_START_HOURS = [h for _, _, hours in SLOT_GROUPS for h in hours]

# ── İzin verilen dosya uzantıları ───────────────────────────────────

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

# ── Brute-force parametreleri ───────────────────────────────────────

LOCKOUT_ATTEMPTS    = 5    # aynı kullanıcı adına başarısız deneme → o hesap kilitlenir
LOCKOUT_MINUTES     = 15
# Aynı IP'den (tüm kullanıcı adları toplamı) başarısız deneme sınırı.
# Üniversite ağında herkes tek IP ile göründüğü için hesap sınırından yüksek tutulur;
# böylece bir adminin yanlış şifreleri diğer adminleri kilitlemez.
IP_LOCKOUT_ATTEMPTS = 15

# ── Rezervasyon kuralları ───────────────────────────────────────────

# Rezervasyon durumları — sadece bu ikisi slotu "dolu" yapar
ACTIVE_STATUSES = ('Pending', 'Approved')

# Bir kişi (aynı telefon VEYA aynı e-posta) bir gün içinde en fazla kaç rezervasyon
# talebi oluşturabilir. Sayılan: o gün oluşturulmuş ve hâlâ aktif (bekleyen/onaylı)
# talepler — iptal edilen/reddedilen talepler hakkı geri verir.
# (IP bazlı değil: kampüs ağında tüm öğrenciler tek IP ile görünür.)
MAX_RESERVATIONS_PER_PERSON_PER_DAY = 2

# Bu kadar saat içinde onaylanmayan talep otomatik "Süresi Doldu" olur ve slot boşalır
PENDING_TIMEOUT_HOURS = 48
# Admin panelinde "uzun süredir bekliyor" uyarısı bu saatten sonra gösterilir
PENDING_WARN_HOURS = 24

# ── Hata sayfası tanımları ──────────────────────────────────────────

ERROR_PAGES = {
    404: {
        'title':      'Sayfa Bulunamadi',
        'message':    'Aradiginiz sayfa mevcut degil veya tasinmis olabilir.',
        'icon':       'search',
        'icon_color': 'clr-gray',
    },
    500: {
        'title':      'Sunucu Hatasi',
        'message':    'Bir seyler ters gitti. Lutfen daha sonra tekrar deneyin.',
        'icon':       'exclamation-triangle',
        'icon_color': 'clr-red',
    },
    429: {
        'title':      'Cok Fazla Istek',
        'message':    'Cok fazla istek gonderdiniz. Lutfen birkac dakika bekleyin.',
        'icon':       'hourglass-half',
        'icon_color': 'clr-yellow',
    },
    403: {
        'title':      'Erisim Engellendi',
        'message':    'Bu sayfaya erisim yetkiniz bulunmuyor.',
        'icon':       'ban',
        'icon_color': 'clr-red',
    },
}
