#!/bin/sh
# Выпустить самоподписанный сертификат до официального entrypoint nginx.
# Скрипт в /docker-entrypoint.d/ с именем 20-* выполняется после
# 20-envsubst-on-templates.sh: конфиг уже ссылается на stand.crt, а файла ещё нет.
# Ненулевой код такого скрипта entrypoint nginx не останавливает контейнер.
set -eu

/usr/local/bin/prs-self-signed-cert.sh
exec /docker-entrypoint.sh "$@"
