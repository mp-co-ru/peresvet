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

Операции в конфигурации привязки тега
-------------------------------------

Операции описываются прямо в ``prsJsonConfigString`` узла привязки тега
``prsDatastorageTagData`` (а не под узлом хранилища данных).

Тип операции задаётся полем ``prsEntityTypeCode``:

- ``0`` — GET (чтение, ``SELECT/CTE``)
- ``1`` — SET (запись, ``INSERT/UPDATE/DELETE/CTE``)

Ограничения SQL:

- запрещён multi-statement (``;``)
- запрещены DDL-операции (``CREATE/ALTER/DROP/TRUNCATE/...``)

Интеграционные теги
-------------------

Привязка тега к хранилищу описывается узлом ``prsDatastorageTagData`` под
``cn=system/cn=tags``.

Для интеграционного тега:

- ``prsEntityTypeCode = 2``
- в ``prsJsonConfigString`` указывается список ``operations`` и правила выбора
  операций для ``get``/``set``:

.. code-block:: json

  {
    "operations": [
      {
        "cn": "erp.orders.select.v1",
        "prsEntityTypeCode": 0,
        "prsJsonConfigString": {
          "query": "select ts as x, payload as y, 0 as q from erp_orders where ts >= :start and ts < :finish order by ts",
          "prsTimeOutMs": 5000,
          "prsMaxRows": 10000,
          "prsVersion": 1
        },
        "parameters": [
          { "cn": "start", "prsJsonConfigString": { "JSONata": "$.start" } },
          { "cn": "finish", "prsJsonConfigString": { "JSONata": "$.finish" } }
        ]
      },
      {
        "cn": "erp.orders.insert.v1",
        "prsEntityTypeCode": 1,
        "prsJsonConfigString": {
          "query": "insert into erp_orders(ts, payload) values(:x, :y)",
          "prsTimeOutMs": 5000
        },
        "parameters": [
          { "cn": "x", "prsJsonConfigString": { "JSONata": "$.params.x" } },
          { "cn": "y", "prsJsonConfigString": { "JSONata": "$.params.y" } }
        ]
      }
    ],
    "get": {
      "operationCn": "erp.orders.select.v1"
    },
    "set": {
      "operations": {
        "insert": "erp.orders.insert.v1",
        "update": "erp.orders.update.v1",
        "delete": "erp.orders.delete.v1"
      }
    }
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
- ``set``: ``params.operation`` определяет тип операции
  (``insert``/``update``/``delete``) и используется для выбора
  соответствующей операции из ``set.operations``.

Эталонные примеры
-----------------

1) Пример ``prsJsonConfigString`` у привязки тега (включая ``operations``):

.. code-block:: json

  {
    "operations": [
      {
        "cn": "erp.orders.select.v1",
        "prsEntityTypeCode": 0,
        "prsJsonConfigString": {
          "query": "select ts as x, payload as y, 0 as q from erp_orders where ts >= :start and ts < :finish order by ts",
          "prsTimeOutMs": 5000,
          "prsMaxRows": 10000,
          "prsVersion": 1
        },
        "parameters": [
          { "cn": "start", "prsJsonConfigString": { "JSONata": "$.start" } },
          { "cn": "finish", "prsJsonConfigString": { "JSONata": "$.finish" } }
        ]
      },
      {
        "cn": "erp.orders.insert.v1",
        "prsEntityTypeCode": 1,
        "prsJsonConfigString": {
          "query": "insert into erp_orders(ts, payload) values(:x, :y)",
          "prsTimeOutMs": 5000
        },
        "parameters": [
          { "cn": "x", "prsJsonConfigString": { "JSONata": "$.params.x" } },
          { "cn": "y", "prsJsonConfigString": { "JSONata": "$.params.y" } }
        ]
      },
      {
        "cn": "erp.orders.update.v1",
        "prsEntityTypeCode": 1,
        "prsJsonConfigString": {
          "query": "update erp_orders set payload = :y where ts = :x",
          "prsTimeOutMs": 5000
        },
        "parameters": [
          { "cn": "x", "prsJsonConfigString": { "JSONata": "$.params.x" } },
          { "cn": "y", "prsJsonConfigString": { "JSONata": "$.params.y" } }
        ]
      },
      {
        "cn": "erp.orders.delete.v1",
        "prsEntityTypeCode": 1,
        "prsJsonConfigString": {
          "query": "delete from erp_orders where ts = :x",
          "prsTimeOutMs": 5000
        },
        "parameters": [
          { "cn": "x", "prsJsonConfigString": { "JSONata": "$.params.x" } }
        ]
      }
    ],
    "get": {
      "operationCn": "erp.orders.select.v1"
    },
    "set": {
      "operations": {
        "insert": "erp.orders.insert.v1",
        "update": "erp.orders.update.v1",
        "delete": "erp.orders.delete.v1"
      }
    }
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
        "data": []
      }
    ],
    "params": {
      "operation": "delete",
      "x": 1738450800000
    }
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

В v2 добавлены поля для операций:

- ``operations`` в ``create/update``
- ``getLinkedOperations`` в ``read``
- ``unlinkOperations`` в ``update``

Эндпоинты:

- ``GET /v2/dataStorages`` — чтение (включая операции по флагу)
- ``POST /v2/dataStorages`` — создание (включая операции)
- ``PUT /v2/dataStorages`` — обновление (включая операции)

Примечание про GET-параметры
----------------------------

Начиная с текущей версии рекомендуется передавать параметры GET-запросов
как обычные query-параметры (``id``, ``base``, ``scope``, ``filter`` и т.д.),
а не через ``q=<json>``.

