#!/bin/bash
# Скрипт запускает контейнеры с сервисами платформы.
# в первом аргументе в командной строке можно передавать параметры
# команды compose up.

#-f docker/compose/docker-compose.grafana.yml \

back=""
if [ -n "$1" ]
then
    back=$1
fi
docker compose $back --env-file docker/compose/.cont_all_svc_in_one.env \
-f docker/compose/docker-compose.redis.yml \
-f docker/compose/docker-compose.all_svc_in_one.yml \
-f docker/compose/docker-compose.nginx.all_svc_in_one.yml \
up
