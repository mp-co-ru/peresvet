#!/bin/bash
# Скрипт запускает контейнеры с сервисами платформы (dev-режим).
#
# в первом аргументе можно задать имя сервера, в качестве которого по умолчанию
# принимается имя текущего сервера

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=packaging/mcp_launch.sh
source "${SCRIPT_DIR}/packaging/mcp_launch.sh"
mcp_init
mcp_parse_leading_flags "$@"

srv="${HOSTNAME:-localhost}"
if [ -n "${mcp_rest_args[0]:-}" ]; then
    srv="${mcp_rest_args[0]}"
fi

if [[ "${PRS_LAUNCH_DRY_RUN:-0}" == "1" ]]; then
    mcp_dry_run_report
    exit 0
fi

mcp_fill_compose_args
mcp_prepare

sed -i "s/NGINX_HOST=.*/NGINX_HOST=$srv/" docker/compose/.cont_one_app.env
extra_env=""
if [ -f docker/compose/.cont_one_app.secrets.env ]; then
    extra_env="--env-file docker/compose/.cont_one_app.secrets.env"
fi

docker compose --env-file docker/compose/.cont_one_app.env $extra_env \
-f docker/compose/docker-compose.redis.yml \
-f docker/compose/docker-compose.rabbitmq.yml \
-f docker/compose/docker-compose.ldap.one_app.yml \
-f docker/compose/docker-compose.postgresql.data_in_volume.yml \
-f docker/compose/docker-compose.one_app.yml \
-f docker/compose/docker-compose.video.yml \
-f docker/compose/docker-compose.grafana.yml \
-f docker/compose/docker-compose.nginx.one_app.yml \
-f docker/compose/docker-compose.ports.yml \
"${mcp_compose_args[@]}" \
up --build

mcp_stop_disabled
mcp_reload_nginx
