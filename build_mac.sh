#!/bin/bash
# Сборка MacBookCam.app. Результат: dist/MacBookCam.app
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { rm -rf .venv; python3 -m venv .venv; }
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-mac.txt pyinstaller pillow
.venv/bin/python -m PyInstaller --noconfirm --clean MacBookCam-mac.spec
rm -rf dist/dmg && mkdir dist/dmg
cp -R dist/MacBookCam.app dist/dmg/
ln -s /Applications dist/dmg/Applications
hdiutil create -volname MacBookCam -srcfolder dist/dmg -ov -format UDZO dist/MacBookCam.dmg
rm -rf dist/dmg
echo
echo "Готово: dist/MacBookCam.dmg (и dist/MacBookCam.app)"
