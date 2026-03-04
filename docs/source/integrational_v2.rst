.. include:: <isonum.txt>

Интеграционные хранилища и операции (API v2)
============================================

В платформе Пересвет есть базовая поддержка исторических данных (historian) и
иерархической модели (LDAP). Для интеграции со “внешними” реляционными данными
(справочники, планы, календари и т.п.) добавлен механизм *интеграционных хранилищ*
и *операций*.

Ключевая идея: значения “интеграционного” тега берутся/пишутся не в
автоматически создаваемую таблицу historian, а через *параметризованный запрос*,
описанный в LDAP как операция.

Включение/выключение v2
-----------------------

Функциональность v2 является опциональной и может не запускаться в некоторых
сборках/конфигурациях.

- Для монолитного приложения ``one_app`` используется переменная окружения:

  - ``PRS_ENABLE_V2=1`` (или ``true/yes/on``) — включить v2 API и v2 model_crud.
  - если переменная не задана — работает только v1.

- Для MCP сервера ``mcp_peresvet``:

  - ``MCP_PERESVET_ENABLE_V2=1`` включает MCP-инструменты для ``/v2``.
  - если не задано — берётся значение ``PRS_ENABLE_V2``.

Тип хранилища integrational
---------------------------

Для ``prsDataStorage`` тип хранилища задаётся атрибутом:

- ``prsEntityTypeCode = 2`` — *integrational relational*.

Операции как дочерние узлы привязки тега
----------------------------------------

Операции интеграционной привязки описываются как **дочерние LDAP-узлы** под
узлом привязки ``prsDatastorageTagData`` (а не в ``prsJsonConfigString`` и не
под узлом хранилища данных).

- узел операции: ``objectClass = prsDatastorageTagOperation``
- узел параметра операции: ``objectClass = prsDatastorageTagOperationParameter``

Тип операции задаётся полем ``prsEntityTypeCode``:

- ``0`` — GET
- ``1`` — SET

Ограничения SQL:

- запрещён multi-statement (``;``);
- запрещены DDL-операции (``CREATE/ALTER/DROP/TRUNCATE/...``).

Интеграционные теги
-------------------

Привязка тега к хранилищу описывается узлом ``prsDatastorageTagData`` под
``cn=system/cn=tags``.

Для интеграционного тега:

- интеграционность определяется **принадлежностью** узла привязки
  ``prsDatastorageTagData`` к ``prsDataStorage`` с ``prsEntityTypeCode = 2``;
- ``prsEntityTypeCode`` у самой привязки тега является опциональным метаполем
  (может быть ``2`` для совместимости), но не обязателен для runtime-обработки;
- блок ``linkTags[].attributes`` также опционален: CN узла привязки задаётся как ``tagId``;
- операции передаются в ``linkTags[].operations``:

.. code-block:: json

  {
    "id": "<DATASTORAGE_ID>",
    "linkTags": [
      {
        "tagId": "<TABLE_TAG_ID>",
        "operations": [
          {
            "attributes": {
              "cn": "erp.orders.select.v1",
              "prsEntityTypeCode": 0,
              "prsJsonConfigString": {
                "query": "select ts as x, payload as y, 0 as q from erp_orders where ts >= :start and ts < :finish order by ts",
                "timeoutMs": 5000,
                "maxRows": 10000,
                "version": 1
              }
            },
            "parameters": [
              { "attributes": { "cn": "start",  "prsJsonConfigString": { "JSONata": "$.start" } } },
              { "attributes": { "cn": "finish", "prsJsonConfigString": { "JSONata": "$.finish" } } }
            ]
          },
          {
            "attributes": {
              "cn": "erp.orders.insert.v1",
              "prsEntityTypeCode": 1,
              "prsJsonConfigString": {
                "query": "insert into erp_orders(ts, payload) values(:x, :y)",
                "timeoutMs": 5000
              }
            },
            "parameters": [
              { "attributes": { "cn": "x", "prsJsonConfigString": { "JSONata": "$.params.x" } } },
              { "attributes": { "cn": "y", "prsJsonConfigString": { "JSONata": "$.params.y" } } }
            ]
          }
        ]
      }
    ]
  }

Правила параметров SQL
----------------------

- Для каждого параметра ``:param`` из SQL **обязательно** должен быть описан
  параметр операции ``cn=param`` с ``prsJsonConfigString.JSONata``.
- Значение параметра вычисляется только через это JSONata-выражение.
- Если JSONata отсутствует или вернул ``null`` — запрос завершается ошибкой.
- Значения по умолчанию не применяются.

Контракт ``params`` в запросах
------------------------------

- ``get``: если JSONata параметров ссылается на ``$.params.*``, клиент передаёт
  соответствующие ключи в ``params``.
- ``get``: ``params.operation`` (строка) задаёт ``cn`` операции.
- ``set``: ``data[i].params.operation`` (строка) задаёт ``cn`` операции для
  конкретного тега ``data[i]``.
  Если ключ операции не указан, выбирается первая операция нужного типа:
  ``prsEntityTypeCode=0`` для ``data/get`` и ``prsEntityTypeCode=1`` для ``data/set``.

Эталонные примеры
-----------------

1) Пример ``PUT /v2/dataStorages`` для привязки табличного тега с операциями:

.. code-block:: json

  {
    "id": "<DATASTORAGE_ID>",
    "linkTags": [
      {
        "tagId": "<TABLE_TAG_ID>",
        "operations": [
          {
            "attributes": {
              "cn": "erp.orders.select.v1",
              "prsEntityTypeCode": 0,
              "prsJsonConfigString": {
                "query": "select ts as x, payload as y, 0 as q from erp_orders where ts >= :start and ts < :finish order by ts",
                "timeoutMs": 5000,
                "maxRows": 10000,
                "version": 1
              }
            },
            "parameters": [
              { "attributes": { "cn": "start",  "prsJsonConfigString": { "JSONata": "$.start" } } },
              { "attributes": { "cn": "finish", "prsJsonConfigString": { "JSONata": "$.finish" } } }
            ]
          },
          {
            "attributes": {
              "cn": "erp.orders.delete.v1",
              "prsEntityTypeCode": 1,
              "prsJsonConfigString": {
                "query": "delete from erp_orders where ts = :x",
                "timeoutMs": 5000
              }
            },
            "parameters": [
              { "attributes": { "cn": "x", "prsJsonConfigString": { "JSONata": "$.params.x" } } }
            ]
          }
        ]
      }
    ]
  }

2) Пример пользовательского ``data/get`` запроса:

.. code-block:: json

  {
    "tagId": ["<tag_id>"],
    "start": "2026-02-02T00:00:00+03:00",
    "finish": "2026-02-03T00:00:00+03:00"
  }

3) Пример пользовательского ``data/set`` запроса:

.. code-block:: json

  {
    "data": [
      {
        "tagId": "<tag_id>",
        "data": [],
        "params": {
          "operation": "delete",
          "x": 1738450800000
        }
      }
    ]
  }

Контракт результата GET
-----------------------

GET-операция обязана возвращать колонки (или поля результата):

- ``y``, ``x``, ``q``

Сервис интеграционного хранилища преобразует результат в стандартный ответ
``data/get``:

.. code-block:: json

  {
    "data": [
      {
        "tagId": "<tagId>",
        "data": [["<x1>", "<y1>", "<q1>"], ["<x2>", "<y2>", "<q2>"]]
      }
    ]
  }

API v2 для dataStorages
-----------------------

В v2 операции интеграционных тегов передаются внутри ``linkTags``:

- ``linkTags[].operations`` в ``create/update``
- ``linkTags[].operations[].parameters`` в ``create/update``

Эндпоинты:

- ``GET /v2/dataStorages`` — чтение (включая операции по флагу)
- ``POST /v2/dataStorages`` — создание (включая операции)
- ``PUT /v2/dataStorages`` — обновление (включая операции)

Примечание про GET-параметры
----------------------------

Начиная с текущей версии рекомендуется передавать параметры GET-запросов
как обычные query-параметры (``id``, ``base``, ``scope``, ``filter`` и т.д.),
а не через ``q=<json>``.

