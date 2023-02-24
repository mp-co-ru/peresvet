# Script launches containers in debug mode. Press F5 in VSCode after containers start to debug the app.
docker compose -f docker-compose.locust.data_get_prs-psql.yml \
    -f docker-compose.postgres.get_test.yml up --scale peresvet=4
