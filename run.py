"""
run.py — Development server giriş noktası.

Kullanım:
    python run.py

Production'da gunicorn veya waitress kullanılmalıdır:
    gunicorn "app:create_app()"
"""

import os
from dotenv import load_dotenv

# .env dosyasını yükle (create_app'den ÖNCE çalışmalı)
base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(base_dir, '.env')
load_dotenv(dotenv_path)

# Windows DLL dizini ayarı (SQLite vb. için)
if hasattr(os, 'add_dll_directory'):
    os.add_dll_directory(base_dir)
os.environ['PATH'] = base_dir + os.pathsep + os.environ.get('PATH', '')

from app import create_app

application = create_app()

if __name__ == '__main__':
    application.run(
        host='0.0.0.0',
        port=5000,
        debug=application.config.get('DEBUG', False)
    )
