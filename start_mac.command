#!/bin/bash
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "Сначала запустите ./setup_mac.sh"; exit 1; }
exec .venv/bin/python mac_sender.py "$@"
