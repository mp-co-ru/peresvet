#!/usr/bin/env bash
# Вызов POST /internal/prepare-shutdown у one_app перед остановкой платформы.
# Гарантирует запись null (качество 101) в теги коннекторов пока доступны LDAP, Redis и очередь.
# Использование: ./prepare_shutdown.sh [BASE_URL]
#   BASE_URL по умолчанию: ${ONE_APP_BASE_URL:-http://localhost:8000}
#   Токен (если задан PRS_PREPARE_SHUTDOWN_TOKEN): передаётся в заголовке X-Prepare-Shutdown-Token.

set -e
BASE_URL="${1:-${ONE_APP_BASE_URL:-http://localhost:8000}}"
URL="${BASE_URL%/}/internal/prepare-shutdown"

if [ -n "$PRS_PREPARE_SHUTDOWN_TOKEN" ]; then
  EXTRA_HEADER=(-H "X-Prepare-Shutdown-Token: $PRS_PREPARE_SHUTDOWN_TOKEN")
else
  EXTRA_HEADER=()
fi

echo "Calling $URL ..."
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "${EXTRA_HEADER[@]}" "$URL")
if [ "$HTTP" = "200" ]; then
  echo "OK (200). Wait 2-3 s, then stop containers (e.g. docker compose down)."
  exit 0
else
  echo "Error: HTTP $HTTP" >&2
  curl -s -X POST "${EXTRA_HEADER[@]}" "$URL" >&2
  exit 1
fi
