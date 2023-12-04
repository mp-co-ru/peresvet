#!/bin/bash
# Скрипт запускает контейнеры с сервисами платформы.
# в первом аргументе в командной строке можно передавать параметры
# команды compose up.
back=""
if [ -n "$1" ]
then
    back=$1
fi
docker compose \
-f docker/compose/docker-compose.rabbitmq.yml \
-f docker/compose/docker-compose.ldap.yml \
-f docker/compose/docker-compose.postgresql.data_in_container.yml \
-f docker/compose/docker-compose.objects.all.yml \
-f docker/compose/docker-compose.dataStorages.all.yml \
-f docker/compose/docker-compose.tags.all.yml \
-f docker/compose/docker-compose.alerts.all.yml \
-f docker/compose/docker-compose.methods.all.yml \
-f docker/compose/docker-compose.schedules.all.yml \
up $back
