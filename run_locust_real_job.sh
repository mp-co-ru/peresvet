# Script launches containers in debug mode. Press F5 in VSCode after containers start to debug the app.
docker compose -f docker-compose.locust.real_job.yml \
    -f docker-compose.postgres.set_test.yml up \
    --scale peresvet=4 \
    #--scale locust_worker=4
