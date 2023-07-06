# -f docker/compose/docker-compose.dataStorages.all.yml \

docker compose -f docker/compose/docker-compose.ldap.yml \
-f docker/compose/docker-compose.rabbitmq.yml \
-f docker/compose/docker-compose.tags.all.yml \
up
