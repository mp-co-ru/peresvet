.. _mcp:

MCP-сервер платформы
====================

Контейнер ``mcp_peresvet`` даёт агентам (Cursor, Roo и т.п.) набор инструментов
поверх HTTP API ``one_app``. Транспорт по умолчанию — Streamable HTTP,
конечная точка ``http://localhost:8009/mcp``.

Запуск
------

MCP **не** входит в ``./run_one_app.sh``. После старта платформы поднимите
сервер отдельным compose-файлом (тот же ``.cont_one_app.env``):

.. code:: sh

   docker compose --env-file docker/compose/.cont_one_app.env \
     -f docker/compose/docker-compose.one_app.yml \
     -f docker/compose/docker-compose.mcp.peresvet.yml \
     up -d --build mcp_peresvet

Проверка: ``GET http://localhost:8009/health`` должен вернуть ``OK``.

Переменные окружения
--------------------

+---------------------------+--------------------------------------------------+
| Переменная                | Назначение                                       |
+===========================+==================================================+
| ``PERESVET_BASE_URL``     | Базовый URL API (в Docker:                       |
|                           | ``http://one_app:8000``).                        |
+---------------------------+--------------------------------------------------+
| ``PERESVET_TIMEOUT_SECONDS`` | Таймаут запросов к API.                       |
+---------------------------+--------------------------------------------------+
| ``PERESVET_BEARER_TOKEN`` | Необязательный Bearer-токен; пробрасывается в    |
|                           | заголовок ``Authorization`` (платная редакция).  |
+---------------------------+--------------------------------------------------+
| ``MCP_PERESVET_TRANSPORT`` | ``http`` (рекомендуется), ``sse``, ``stdio``.   |
+---------------------------+--------------------------------------------------+
| ``MCP_PERESVET_ENABLE_V2`` | Инструменты ``/v2/dataStorages/``. Если не       |
|                           | задано — берётся ``PRS_ENABLE_V2``.              |
+---------------------------+--------------------------------------------------+
| ``PORT_MCP_PERESVET``     | Порт на хосте (по умолчанию ``8009``).           |
+---------------------------+--------------------------------------------------+

Пример клиента (``.roo/mcp.json`` / Cursor MCP):

.. code-block:: json

   {
     "mcpServers": {
       "peresvet": {
         "type": "streamable-http",
         "url": "http://localhost:8009/mcp"
       }
     }
   }

Инструменты
-----------

Иерархия и CRUD:

* ``peresvet_objects_list`` / ``peresvet_objects_tree`` / ``peresvet_object_create``
* ``peresvet_tags_list`` / ``peresvet_tags_tree`` / ``peresvet_tag_create``
* ``peresvet_apply_hierarchy`` — безопасное создание дерева объектов и тегов
* ``peresvet_crud_read`` / ``create`` / ``update`` / ``delete`` — низкоуровневый
  доступ к ``objects``, ``tags``, ``alerts``, ``methods``, ``connectors``,
  ``schedules``, ``dataStorages``

Копирование узлов (``POST /v1/<entity>/copy``, для коннекторов — ``POST`` с
``sourceId``):

* ``peresvet_object_copy``, ``peresvet_tag_copy``, ``peresvet_alert_copy``,
  ``peresvet_method_copy``, ``peresvet_connector_copy``

Тревоги и алармы:

* ``peresvet_alert_create`` — порог ``value`` / ``high`` / ``autoAck``
* ``peresvet_alarms_get``, ``peresvet_alarm_ack``

Коннекторы (MQTT runtime):

* ``peresvet_connector_create`` / ``peresvet_connector_update``
* ``peresvet_connector_command``
* ``peresvet_connector_link_status``
* ``peresvet_connector_log_tail``
* ``peresvet_connector_command_output_tail``

Данные и методы:

* ``peresvet_data_get`` / ``peresvet_data_set``
* ``peresvet_datafunc_get`` — агрегации ``/v1/datafunc/``
* ``peresvet_method_create`` / ``peresvet_virtual_method_create``
* ``peresvet_schedule_create``

Интеграционные хранилища (v2, при ``MCP_PERESVET_ENABLE_V2`` / ``PRS_ENABLE_V2``):

* ``peresvet_datastorages_v2_read`` / ``create`` / ``update``
* ``peresvet_integrational_datastorage_create`` / ``update``
* ``peresvet_integrational_tag_operations_update``

Служебные:

* ``peresvet_openapi``
* HTTP ``GET /health``, ``GET /config`` (``auth_configured`` не раскрывает токен)
