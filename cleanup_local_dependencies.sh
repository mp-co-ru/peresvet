#!/usr/bin/env bash
set -euo pipefail

# Скрипт очистки подготовленных зависимостей для локального режима

echo "Очистка подготовленных зависимостей для локального режима..."

# Очищаем кэш apt
apt-get clean -y || true
rm -rf /var/lib/apt/lists/* || true

# Очищаем кэш pip
python3 -m pip cache purge 2>/dev/null || true

# Очищаем __pycache__
find /usr/local/lib/python3.12/site-packages -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

echo "Очистка завершена."
