#!/bin/bash
# Скрипт запускает контейнеры с сервисами платформы.
<<<<<<< HEAD
# в первом аргументе в командной строке можно передавать параметры
# команды compose up.

#-f docker/compose/docker-compose.grafana.yml \

back=""
if [ -n "$1" ]
then
    back=$1
fi
sed -i "s/NGINX_HOST=.*/NGINX_HOST=$HOSTNAME/" docker/compose/.cont_one_app.env
docker compose $back --env-file docker/compose/.cont_one_app.env \
-f docker/compose/docker-compose.redis.yml \
-f docker/compose/docker-compose.rabbitmq.yml \
-f docker/compose/docker-compose.ldap.one_app.yml \
-f docker/compose/docker-compose.postgresql.data_in_container.yml \
-f docker/compose/docker-compose.one_app.yml \
-f docker/compose/docker-compose.grafana.yml \
-f docker/compose/docker-compose.nginx.one_app.yml \
=======
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
-f docker/compose/docker-compose.nginx.one_app.yml \
-f docker/compose/docker-compose.ports.yml \
>>>>>>> peresvet/dev
up
