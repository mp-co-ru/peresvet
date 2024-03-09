#!/bin/bash
uvicorn src.services.alerts.api_crud.alerts_api_crud_svc:app --proxy-headers --host 0.0.0.0 --port 80 &
uvicorn src.services.alerts.app_api.alerts_app_api_svc:app --proxy-headers --host 0.0.0.0 --port 81 &
uvicorn src.services.connectors.api_crud.connectors_api_crud_svc:app --proxy-headers --host 0.0.0.0 --port 82 &
uvicorn src.services.dataStorages.api_crud.dataStorages_api_crud_svc:app --proxy-headers --host 0.0.0.0 --port 84 &
uvicorn src.services.methods.api_crud.methods_api_crud_svc:app --proxy-headers --host 0.0.0.0 --port 85 &
uvicorn src.services.objects.api_crud.objects_api_crud_svc:app --proxy-headers --host 0.0.0.0 --port 86 &
uvicorn src.services.schedules.api_crud.schedules_api_crud_svc:app --proxy-headers --host 0.0.0.0 --port 87 &
uvicorn src.services.tags.api_crud.tags_api_crud_svc:app --proxy-headers --host 0.0.0.0 --port 88 &

uvicorn src.services.alerts.model_crud.alerts_model_crud_svc:app --host 0.0.0.0 --port 8000 &
uvicorn src.services.alerts.app.alerts_app_svc:app --host 0.0.0.0 --port 8001 &
uvicorn src.services.connectors.model_crud.connectors_model_crud_svc:app --host 0.0.0.0 --port 8002 &
uvicorn src.services.dataStorages.model_crud.dataStorages_model_crud_svc:app --host 0.0.0.0 --port 8003 &
uvicorn src.services.methods.model_crud.methods_model_crud_svc:app --host 0.0.0.0 --port 8004 &
uvicorn src.services.objects.model_crud.objects_model_crud_svc:app --host 0.0.0.0 --port 8005 &
uvicorn src.services.schedules.model_crud.schedules_model_crud_svc:app --host 0.0.0.0 --port 8006 &
uvicorn src.services.schedules.app.schedules_app_svc:app --host 0.0.0.0 --port 8007 &
uvicorn src.services.tags.model_crud.tags_model_crud_svc:app --host 0.0.0.0 --port 8008 &
uvicorn src.services.methods.app.methods_app_svc:app --host 0.0.0.0 --port 8009 &
uvicorn src.services.dataStorages.app.postgresql.dataStorages_app_postgresql_svc:app --host 0.0.0.0 --port 8010 &
uvicorn src.services.tags.app_api.tags_app_api_svc:app --proxy-headers --host 0.0.0.0 --port 89 &
uvicorn src.services.connectors.app.connectors_app_svc:app --proxy-headers --host 0.0.0.0 --port 83 &
uvicorn src.services.tags.app.tags_app_svc:app --host 0.0.0.0 --port 8011 &
uvicorn src.services.retranslator.app.retranslator_app_svc:app --host 0.0.0.0 --port 8012 &

wait -n
exit $?
