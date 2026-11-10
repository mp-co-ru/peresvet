#!/bin/bash
# Скрипт запускает контейнеры с сервисами платформы. Протокол - HTTPS.
# Предназначен для запуска на сервере, доступном из интернета, 
# так как сертификаты генерируются с помощью Let's Encrypt.
# 
# Запускается после скрипта run_one_app_ssl_letsencrypt_generate_certificates.sh !
# Ключи --mcp-peresvet и --mcp-grafana по умолчанию false.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=packaging/mcp_launch.sh
source "${SCRIPT_DIR}/packaging/mcp_launch.sh"
mcp_init
mcp_parse_leading_flags "$@"

if [[ "${PRS_LAUNCH_DRY_RUN:-0}" == "1" ]]; then
    mcp_dry_run_report
    exit 0
fi

mcp_fill_compose_args
mcp_prepare

docker compose --env-file docker/compose/.cont_one_app.env \
-f docker/compose/docker-compose.redis.yml \
-f docker/compose/docker-compose.rabbitmq.yml \
-f docker/compose/docker-compose.ldap.one_app.yml \
-f docker/compose/docker-compose.postgresql.data_in_volume.yml \
-f docker/compose/docker-compose.one_app.yml \
-f docker/compose/docker-compose.video.yml \
-f docker/compose/docker-compose.grafana.yml \
-f docker/compose/docker-compose.nginx.one_app_ssl_letsencrypt.yml \
-f docker/compose/docker-compose.restart.yml \
"${mcp_compose_args[@]}" \
up -d

mcp_stop_disabled
mcp_reload_nginx
