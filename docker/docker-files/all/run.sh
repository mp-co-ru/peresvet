#!/bin/bash
uvicorn src.services.methods.app.methods_app_svc:app --host 0.0.0.0 --port 800 &
uvicorn src.services.dataStorages.app.postgresql.dataStorages_app_postgresql_svc:app --host 0.0.0.0 --port 8001 &
uvicorn src.services.tags.app_api.tags_app_api_svc:app --proxy-headers --host 0.0.0.0 --port 89 &
uvicorn src.services.connectors.app.connectors_app_svc:app --proxy-headers --host 0.0.0.0 --port 83 &
uvicorn src.services.tags.app.tags_app_svc:app --host 0.0.0.0 --port 8002 &
uvicorn src.services.retranslator.app.retranslator_app_svc:app --host 0.0.0.0 --port 8003 &

wait -n
exit $?
