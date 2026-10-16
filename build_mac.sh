#!/bin/bash
# Сборка MacBookCam.app. Результат: dist/MacBookCam.app
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { rm -rf .venv; python3 -m venv .venv; }
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-mac.txt pyinstaller pillow
.venv/bin/python -m PyInstaller --noconfirm --clean MacBookCam-mac.spec
echo
echo "Готово: dist/MacBookCam.app — перетащите в «Программы»."
