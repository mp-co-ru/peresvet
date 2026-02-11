#!/bin/bash
# Скрипт запускает контейнеры с сервисами платформы (dev-режим).
# Отличие от run_one_app.sh: дополнительно поднимается MCP-сервер Grafana (mcp/grafana).
#
# в первом аргументе можно задать имя сервера, в качестве которого по умолчанию
# принимается имя текущего сервера

srv=$HOSTNAME
if [ -n "$1" ]
then
    srv=$1
fi

sed -i "s/NGINX_HOST=.*/NGINX_HOST=$srv/" docker/compose/.cont_one_app.env
docker compose --env-file docker/compose/.cont_one_app.env \
-f docker/compose/docker-compose.redis.yml \
-f docker/compose/docker-compose.rabbitmq.yml \
-f docker/compose/docker-compose.ldap.one_app.yml \
-f docker/compose/docker-compose.postgresql.data_in_volume.yml \
-f docker/compose/docker-compose.one_app.yml \
-f docker/compose/docker-compose.grafana.yml \
-f docker/compose/docker-compose.mcp.grafana.yml \
-f docker/compose/docker-compose.mcp.peresvet.yml \
-f docker/compose/docker-compose.nginx.one_app.yml \
-f docker/compose/docker-compose.ports.yml \
up

