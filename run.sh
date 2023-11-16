# -f docker/compose/docker-compose.pgadmin.yml \
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
-f docker/compose/docker-compose.retranslator.yml \
up
