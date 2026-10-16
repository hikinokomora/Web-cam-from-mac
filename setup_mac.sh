#!/bin/bash
set -e
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null; then
  echo "python3 не найден. Установите: xcode-select --install  (или с python.org)"
  exit 1
fi
[ -x .venv/bin/python ] || { rm -rf .venv; python3 -m venv .venv; }
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-mac.txt
chmod +x start_mac.command
echo
echo "Готово. Для запуска: ./start_mac.command (или двойной клик в Finder)"
