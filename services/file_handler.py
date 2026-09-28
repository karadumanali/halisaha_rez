"""
file_handler.py — Dosya yükleme ve doğrulama servisi.

Dekont yükleme, saha resmi yükleme ve logo güncelleme
işlemlerinin dosya işleme mantığı burada.
"""

import os
import uuid
import logging

from PIL import Image
from flask import current_app

from services.security import detect_mime
from utils.constants import ALLOWED_EXTENSIONS

logger = logging.getLogger(__name__)


def allowed_file(filename: str) -> bool:
    """Dosya uzantısının izin verilenler listesinde olup olmadığını kontrol et."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_secure_receipt(file) -> str | None:
    """
    Dekont dosyasını güvenli şekilde kaydet.

    MIME magic-bytes doğrulaması yapar, resim ise yeniden boyutlandırır.
    Başarılı: dosya adı döndürür. Başarısız: None döndürür.
    """
    if not file or not file.filename:
        return None

    file_content = file.read(2048)
    file.seek(0)
    mime_type = detect_mime(file_content)

    if not mime_type:
        logger.warning("MIME tespit edilemedi, dosya reddedildi.")
        return None

    ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png'}
    ALLOWED_PDF         = {'application/pdf'}

    if mime_type not in (ALLOWED_IMAGE_TYPES | ALLOWED_PDF) or not allowed_file(file.filename):
        return None

    ext           = file.filename.rsplit('.', 1)[1].lower()
    safe_filename = f"{uuid.uuid4().hex}.{ext}"
    save_path     = os.path.join(current_app.config['UPLOAD_FOLDER'], safe_filename)

    if mime_type in ALLOWED_IMAGE_TYPES:
        try:
            with Image.open(file) as img:
                if img.mode in ("RGBA", "P") and ext in ['jpg', 'jpeg']:
                    img = img.convert("RGB")
                elif img.mode != "RGB" and ext not in ['png']:
                    img = img.convert("RGB")
                img.thumbnail((1920, 1920))
                img.save(save_path, optimize=True, quality=85)
        except Exception as e:
            logger.warning(f"Resim isleme hatasi: {e}")
            return None
    elif mime_type in ALLOWED_PDF:
        try:
            file.save(save_path)
        except Exception as e:
            logger.warning(f"PDF kaydetme hatasi: {e}")
            return None

    return safe_filename


def save_secure_pitch_image(file) -> str | None:
    """
    Saha resmini güvenli şekilde kaydet.

    MIME doğrulaması + yeniden boyutlandırma yapar.
    """
    if not file:
        return None

    file_content = file.read(2048)
    file.seek(0)
    mime_type = detect_mime(file_content)

    ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png'}
    if mime_type not in ALLOWED_IMAGE_TYPES or not allowed_file(file.filename):
        return None

    ext           = file.filename.rsplit('.', 1)[1].lower()
    safe_filename = f"pitch_{uuid.uuid4().hex}.{ext}"
    save_path     = os.path.join(current_app.config['PITCH_IMAGES_FOLDER'], safe_filename)

    try:
        with Image.open(file) as img:
            if img.mode in ("RGBA", "P") and ext in ['jpg', 'jpeg']:
                img = img.convert("RGB")
            elif img.mode != "RGB" and ext not in ['png']:
                img = img.convert("RGB")
            img.thumbnail((1920, 1080))
            img.save(save_path, optimize=True, quality=85)
    except Exception:
        return None

    return safe_filename
