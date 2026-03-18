#!/bin/sh
# Ожидание появления upstream-хоста one_app в DNS перед запуском nginx.
# Устраняет ошибку "host not found in upstream" при старте контейнера.
# При condition: service_healthy для one_app резолв обычно уже есть; таймаут — страховка.
set -e
MAX_WAIT="${NGINX_WAIT_UPSTREAM_SEC:-30}"
elapsed=0
echo "Waiting for one_app to be resolvable..."
while ! ping -c 1 -W 2 one_app >/dev/null 2>&1; do
  sleep 1
  elapsed=$((elapsed + 1))
  if [ "$elapsed" -ge "$MAX_WAIT" ]; then
    echo "WARN: one_app not resolvable after ${MAX_WAIT}s, starting nginx anyway (may fail). Check: docker compose ps -a"
    break
  fi
done
echo "one_app is up, starting nginx"
# Всегда передаём nginx одной строкой, чтобы в Alpine sh не разбивалось "daemon off;" при передаче через $@
exec /docker-entrypoint.sh nginx -g "daemon off;"
