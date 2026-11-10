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
py_mm=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "3.14")
find \
    "/usr/local/lib/python${py_mm}/site-packages" \
    "/usr/local/lib/python${py_mm}/dist-packages" \
    "/usr/lib/python3/dist-packages" \
    -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

echo "Очистка завершена."
