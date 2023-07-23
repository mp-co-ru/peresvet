docker compose \
-f docker/compose/docker-compose.ldap.load_tests.yml \
-f docker/compose/docker-compose.dataStorages.prepare_load_tests.yml \
-f docker/compose/docker-compose.rabbitmq.load_tests.yml \
-f docker/compose/docker-compose.tags.prepare_load_tests.yml \
-f docker/compose/docker-compose.postgresql.data_on_disk.yml \
-f docker/compose/docker-compose.pgadmin.yml \
up
