"""
timeutil.py — Uygulama genelinde saat kaynağı: Türkiye saati (Europe/Istanbul).

Sunucunun kendi saat dilimi (Linux'ta genelde UTC) hiçbir hesapta kullanılmaz;
"şu an" ve "bugün" her yerde buradan alınır.

Veritabanındaki DateTime sütunları saat dilimi bilgisi içermez (naive);
değerler Türkiye yerel saati olarak saklanır.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

TR_TZ = ZoneInfo('Europe/Istanbul')


def now_tr() -> datetime:
    """Türkiye saatiyle şu an (naive — DB sütunlarıyla doğrudan karşılaştırılabilir)."""
    return datetime.now(TR_TZ).replace(tzinfo=None)


def today_tr():
    """Türkiye saatiyle bugünün tarihi."""
    return now_tr().date()
