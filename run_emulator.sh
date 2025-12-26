# -f docker/compose/docker-compose.pgadmin.yml \
docker compose \
-f docker/compose/docker-compose.rabbitmq.yml \
-f docker/compose/docker-compose.ldap.yml \
-f docker/compose/docker-compose.tags.all.yml \
-f docker/compose/docker-compose.retranslator.yml \
-f docker/compose/docker-compose.methods.all.yml \
-f docker/compose/docker-compose.postgresql.emulator.data_on_disk.yml \
-f docker/compose/docker-compose.objects.all.yml \
-f docker/compose/docker-compose.dataStorages.all.yml \
-f docker/compose/docker-compose.grafana.yml \
up -d --build

