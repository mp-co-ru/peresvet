# -f docker/compose/docker-compose.pgadmin.yml \
docker compose \
-f docker/compose/docker-compose.ldap.load_tests.yml \
-f docker/compose/docker-compose.dataStorages.load_tests.yml \
-f docker/compose/docker-compose.rabbitmq.load_tests.yml \
-f docker/compose/docker-compose.tags.load_tests.yml \
-f docker/compose/docker-compose.postgresql.data_on_disk.yml \
-f docker/compose/docker-compose.vm.load_tests.yml \
-f docker/compose/docker-compose.locust.load_tests.yml \
up
