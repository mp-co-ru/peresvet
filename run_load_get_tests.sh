docker compose -f docker/compose/docker-compose.ldap.load_tests.yml \
-f docker/compose/docker-compose.dataStorages.all.load_tests.yml \
-f docker/compose/docker-compose.rabbitmq.load_tests.yml \
-f docker/compose/docker-compose.pgadmin.load_tests.yml \
-f docker/compose/docker-compose.tags.all.load_tests.yml \
-f docker/compose/docker-compose.locust.load_tests.get_data_psql.yml \
up
