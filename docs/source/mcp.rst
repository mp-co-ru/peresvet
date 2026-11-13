.. _mcp:

MCP-сервер платформы
====================

MCP (Model Context Protocol) позволяет ИИ-агентам — Cursor, Roo и другим —
работать с платформой: читать и строить модель, читать и писать данные
тегов, настраивать коннекторы и методы. MCP-сервер платформы (контейнер
``mcp_peresvet``) предоставляет агенту набор инструментов, каждый из которых
вызывает HTTP API платформы.

Вместе с ним поставляется MCP-сервер Grafana, через который агент работает
с экранами и источниками данных Grafana.

Оба сервера доступны через nginx:

* ``https://<хост>/mcp/peresvet`` — MCP платформы;
* ``https://<хост>/mcp/grafana`` — MCP Grafana.

Своих портов на сервере у них нет: внутри сети ``peresvet`` они слушают
порт ``8000``, а снаружи доступны только через nginx. Транспорт по умолчанию —
Streamable HTTP.

Запуск
------

По умолчанию оба сервера выключены. Их включают ключами скрипта запуска
платформы (подробнее — :ref:`optional-via-nginx`):

.. code:: sh

   ./run_one_app.sh --mcp-peresvet true --mcp-grafana true

Те же значения по умолчанию задаются в ``.env`` переменными
``PRS_MCP_PERESVET`` и ``PRS_MCP_GRAFANA`` (обе ``false``). Если сервер
выключен, скрипт удаляет его маршрут из nginx и останавливает контейнер.
Те же ключи понимают ``run_one_app_dev.sh``, ``run_one_app_dev_no_build.sh``
и ``run_one_app_ssl_letsencrypt.sh``.

Проверка MCP платформы: запрос ``GET https://<хост>/mcp/peresvet/health``
должен вернуть ``OK``.

MCP Grafana для большинства операций нужен токен сервисного аккаунта
Grafana. Выпустите его в Grafana (Administration → Users and access →
Service accounts → Add service account token, см.
`Service accounts <https://grafana.com/docs/grafana/latest/administration/service-accounts/>`_)
и запишите в переменную ``GRAFANA_SERVICE_ACCOUNT_TOKEN`` файла
``docker/compose/.cont_one_app.secrets.env``.

Подключение агента
------------------

Пример настройки клиента (``.roo/mcp.json``, настройки MCP в Cursor):

.. code-block:: json

   {
     "mcpServers": {
       "peresvet": {
         "type": "streamable-http",
         "url": "https://<хост>/mcp/peresvet"
       }
     }
   }

Переменные окружения
--------------------

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Переменная
     - Назначение
   * - ``PERESVET_BASE_URL``
     - Адрес API платформы. В Docker — ``http://one_app:8000``.
   * - ``PERESVET_TIMEOUT_SECONDS``
     - Ограничение времени запросов к API.
   * - ``PERESVET_BEARER_TOKEN``
     - Необязательный токен, который сервер передаёт в заголовке
       ``Authorization: Bearer`` (для промышленной редакции).
   * - ``MCP_PERESVET_TRANSPORT``
     - Транспорт: ``http`` (рекомендуется), ``sse`` или ``stdio``.
   * - ``MCP_PERESVET_ENABLE_V2``
     - Включить инструменты API v2 (интеграционные хранилища). Если не задана,
       берётся значение ``PRS_ENABLE_V2``.
   * - ``PORT_MCP_PERESVET_INNER``
     - Порт внутри контейнера, по умолчанию ``8000``.

Инструменты
-----------

**Модель: объекты и теги**

* ``peresvet_objects_list``, ``peresvet_objects_tree``,
  ``peresvet_object_create`` — объекты;
* ``peresvet_tags_list``, ``peresvet_tags_tree``, ``peresvet_tag_create`` —
  теги;
* ``peresvet_object_get_child_id``, ``peresvet_tag_get_child_id`` —
  найти идентификатор дочернего объекта или тега по имени;
* ``peresvet_apply_hierarchy`` — создать дерево объектов и тегов за один
  вызов, не создавая дубликатов.

Родителем (``parent_id``, ``root_parent_id``) может быть и пользовательская
папка.

**Папки**

* ``peresvet_folder_create``, ``peresvet_folders_list``,
  ``peresvet_folder_update``, ``peresvet_folder_delete`` — пользовательские
  папки в ветках объектов, тегов, коннекторов, расписаний и хранилищ
  (см. :doc:`folders`).

**Универсальный доступ**

* ``peresvet_crud_read``, ``peresvet_crud_create``, ``peresvet_crud_update``,
  ``peresvet_crud_delete`` — CRUD для ``objects``, ``tags``, ``alerts``,
  ``methods``, ``connectors``, ``schedules``, ``dataStorages``.

**Копирование**

* ``peresvet_object_copy``, ``peresvet_tag_copy``, ``peresvet_alert_copy``,
  ``peresvet_method_copy``, ``peresvet_connector_copy``.

**Тревоги**

* ``peresvet_alert_create`` — создать тревогу (порог ``value``, направление
  ``high``, автоквитирование ``autoAck``);
* ``peresvet_alarms_get``, ``peresvet_alarm_ack`` — активные тревоги
  и их квитирование.

**Коннекторы**

* ``peresvet_connector_create``, ``peresvet_connector_update``;
* ``peresvet_connector_command`` — удалённые команды коннектору;
* ``peresvet_connector_link_status`` — есть ли связь с коннектором;
* ``peresvet_connector_log_tail``, ``peresvet_connector_command_output_tail`` —
  журнал коннектора и результаты команд.

**Данные**

* ``peresvet_data_get``, ``peresvet_data_set`` — чтение и запись данных тегов;
* ``peresvet_datafunc_get`` — агрегаты данных (``/v1/datafunc/``).

**Методы** (см. :doc:`methods`)

* ``peresvet_method_create`` — метод любого типа ``0``–``4``;
* ``peresvet_virtual_method_create`` — метод чтения (тип ``1``);
* ``peresvet_write_method_create`` — метод записи (тип ``2``);
* ``peresvet_read_action_create`` — действие при чтении (тип ``3``);
* ``peresvet_write_action_create`` — действие при записи (тип ``4``);
* ``peresvet_method_folder_create``, ``peresvet_method_folders_list``,
  ``peresvet_method_folder_update``, ``peresvet_method_folder_delete`` —
  папки каталога методов;
* ``peresvet_method_description_import`` — загрузить YAML-описание
  в каталог, с пробным вызовом методов при ``probe=true``.

**Расписания**

* ``peresvet_schedule_create``.

**Камеры**

* ``peresvet_ptz`` — управление камерой (``status``, ``move``, ``step``,
  ``pulse``, ``stop``, ``home``, ``preset``, ``image``, ``image_set``),
  см. :ref:`video_tag`. Видео — живой поток, снимки и записи — через MCP
  не передаётся.

**Журналы сервисов платформы**

* ``peresvet_connector_services`` — список сервисов;
* ``peresvet_connector_service_log_tail``,
  ``peresvet_connector_service_log_clear`` — чтение и очистка их журналов.

**Интеграционные хранилища** (если включён API v2)

* ``peresvet_datastorages_v2_read``, ``peresvet_datastorages_v2_create``,
  ``peresvet_datastorages_v2_update``, ``peresvet_datastorages_v2_delete``;
* ``peresvet_integrational_datastorage_create``,
  ``peresvet_integrational_datastorage_update``;
* ``peresvet_integrational_tag_operations_update``.

См. :ref:`integrational_v2`.

**Служебные**

* ``peresvet_openapi`` — описание API платформы в формате OpenAPI;
* HTTP-адреса сервера ``GET /health`` и ``GET /config``. ``/config``
  показывает настройки сервера; токен в нём не раскрывается, есть только
  признак ``auth_configured``.
