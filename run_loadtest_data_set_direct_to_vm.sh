# Script launches containers in debug mode. Press F5 in VSCode after containers start to debug the app.
docker compose -f docker-compose.loadtest.locust_set_data_direct_to_vm.yml \
    -f docker-compose.victoriametrics.yml up
