import os
import sys

# Menambahkan root project ke sys.path agar app.py dan modul lainnya dapat diimpor
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import app

# Vercel mencari WSGI callable bernama 'app'
if __name__ == "__main__":
    app.run()
