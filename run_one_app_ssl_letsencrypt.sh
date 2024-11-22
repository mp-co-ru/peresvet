#!/bin/bash
# Скрипт запускает контейнеры с сервисами платформы. Протокол - HTTPS.
# Предназначен для запуска на сервере, доступном из интернета, 
# так как сертификаты генерируются с помощью Let's Encrypt.
# 
# в первом аргументе можно задать имя сервера, в качестве которого по умолчанию
# принимается имя текущего сервера

#-f docker/compose/docker-compose.grafana.yml \

sed -i 's/restart: "no"/restart: always/' docker/compose/docker-compose.redis.yml
sed -i 's/restart: "no"/restart: always/' docker/compose/docker-compose.rabbitmq.yml
sed -i 's/restart: "no"/restart: always/' docker/compose/docker-compose.ldap.one_app.yml
sed -i 's/restart: "no"/restart: always/' docker/compose/docker-compose.postgresql.data_in_container.yml
sed -i 's/restart: "no"/restart: always/' docker/compose/docker-compose.one_app.yml
sed -i 's/restart: "no"/restart: always/' docker/compose/docker-compose.grafana.yml
sed -i 's/restart: "no"/restart: always/' docker/compose/docker-compose.nginx.one_app_ssl_letsencrypt.yml

docker compose --env-file docker/compose/.cont_one_app.env \
-f docker/compose/docker-compose.redis.yml \
-f docker/compose/docker-compose.rabbitmq.yml \
-f docker/compose/docker-compose.ldap.one_app.yml \
-f docker/compose/docker-compose.postgresql.data_in_container.yml \
-f docker/compose/docker-compose.one_app.yml \
-f docker/compose/docker-compose.grafana.yml \
-f docker/compose/docker-compose.nginx.one_app_ssl_letsencrypt.yml \
up -d
