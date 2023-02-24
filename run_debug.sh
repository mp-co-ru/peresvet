# Script launches containers in debug mode. Press F5 in VSCode after containers start to debug the app.
docker compose -f docker-compose.peresvet.yml \
    -f docker-compose.postgres.yml \
    -f docker-compose.pgadmin.yml stop
docker compose -f docker-compose.peresvet.yml \
    -f docker-compose.postgres.yml \
    -f docker-compose.pgadmin.yml \
    -f docker-compose.debug.yml up
