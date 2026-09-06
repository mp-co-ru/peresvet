Точки расширения безопасности
=============================

Бесплатная редакция МПК-Пересвет сохраняет прежнее поведение API: если
специальный поставщик авторизации не настроен, все действия разрешены. Это
сделано для того, чтобы базовая функциональность не зависела от внешнего
Identity Provider, OPA или других enterprise-компонентов.

При этом в ядре есть нейтральная точка расширения для редакций и продуктов,
которые должны подключать собственную авторизацию.

Переменная окружения
--------------------

По умолчанию используется разрешающий поставщик:

.. code-block:: bash

   PRS_AUTH_PROVIDER=

Платная редакция может указать Python-объект в формате ``module:attribute``:

.. code-block:: bash

   PRS_AUTH_PROVIDER=enterprise_security.opa_provider:OpaAuthorizationProvider

Объект должен реализовать асинхронный метод:

.. code-block:: python

   async def authorize(self, data: AuthorizationInput) -> AuthorizationDecision:
       ...

Если ``authorize`` возвращает ``AuthorizationDecision(allow=False)``, API
возвращает HTTP ``403``.

Для промышленной платной редакции, где микросервисы могут работать в разных
контейнерах и на разных серверах, тот же поставщик может реализовать
дополнительный метод:

.. code-block:: python

   async def amqp_publish_headers(self, data: AuthorizationInput) -> dict:
       ...

Этот метод позволяет добавить в исходящее RabbitMQ-сообщение подписанный
контекст безопасности через AMQP headers, не меняя JSON-тело сообщения и не
ломая совместимость бесплатной редакции.

Контекст запроса
----------------

Во время обработки HTTP-запроса ядро сохраняет текущий ``Request`` в
context variable. Enterprise-поставщик может использовать его, чтобы прочитать:

* ``Authorization: Bearer ...``;
* IP-адрес клиента;
* путь и HTTP-метод;
* служебные заголовки reverse proxy.

Middleware подключается как к отдельным сервисным FastAPI-приложениям, так и к
агрегированному ``one_app``. Поэтому enterprise provider получает контекст
запроса и при запуске микросервисов по отдельности, и при запуске платформы в
одном приложении.

Контекст RabbitMQ
-----------------

При публикации внутренних сообщений ядро вызывает ``amqp_publish_headers`` с
действием ``amqp.publish`` и ресурсом вида:

.. code-block:: json

   {
      "service": "tags_app_api",
      "routing_key": "prsTag.app_api.data_set.*",
      "reply": true
   }

Платная редакция может вернуть, например, заголовок с подписанным actor/request
context. Бесплатная редакция возвращает пустой набор заголовков.

Поле ``service`` — имя сервиса-издателя из его конфигурации. Это позволяет
платной редакции строить service identity поверх RabbitMQ credentials, mTLS или
service JWT.

Если сервис обрабатывает входящее RabbitMQ-сообщение и в процессе handler-а
публикует следующее сообщение, ``amqp_publish_headers`` получает в
``environment.amqp_context`` контекст исходного сообщения: сервис-потребитель,
routing key, headers, ``reply_to`` и ``correlation_id``. Это нужно для
multi-hop цепочек:

.. code-block:: text

   HTTP API -> service A -> RabbitMQ -> service B -> RabbitMQ -> service C

Платный provider может использовать этот context для переноса исходного actor-а
и request id через всю цепочку внутренних сервисов.

При получении сообщения из RabbitMQ ядро вызывает ``authorize`` с действием
``amqp.consume`` до передачи сообщения конкретному handler-у. В ``resource``
попадает имя сервиса-потребителя, routing key, ``reply_to`` и
``correlation_id``, а в ``environment`` — AMQP headers. Если поставщик вернёт ``allow=False``, сообщение не
обрабатывается; для RPC-запросов отправляется ответ с ошибкой ``403``.

RPC-ответы также проходят через extension points:

* при отправке ответа handler-а вызывается ``amqp_publish_headers``;
* при получении ответа callback-очередью вызывается ``authorize`` с
  ``amqp.consume``;
* если enterprise provider запрещает RPC-ответ, ожидающий вызов получает
  error payload с кодом ``403``.

Эти hooks нужны именно для распределённой платной инсталляции, где микросервисы
могут находиться в разных контейнерах и на разных серверах, а RabbitMQ является
основным внутренним каналом связи.

Типы действий
-------------

Базовые CRUD-сервисы вызывают авторизацию с действиями вида:

* ``prsObject.create`` / ``prsObject.read`` / ``prsObject.update`` /
  ``prsObject.delete``;
* ``prsTag.create`` / ``prsTag.read`` / ``prsTag.update`` /
  ``prsTag.delete``;
* аналогично для ``prsAlert``, ``prsMethod``, ``prsConnector``,
  ``prsDataStorage``, ``prsSchedule``.
* copy-операции используют действия вида ``prsObject.copy``,
  ``prsTag.copy``, ``prsAlert.copy``, ``prsMethod.copy``,
  ``prsConnector.copy``.

Операционные API вызывают отдельные действия:

* ``prsTag.data_get``;
* ``prsTag.data_set``;
* ``prsAlert.alarm_read``;
* ``prsAlert.alarm_ack``;
* ``prsConnector.connector_command``;
* ``prsConnector.connector_log_read``;
* ``prsConnector.service_log_read``.

Внутренний контур RabbitMQ использует действия:

* ``amqp.publish``;
* ``amqp.consume``.

Назначение
----------

Эта точка расширения предназначена для платной редакции, где поверх базового
ядра подключаются:

* аутентификация пользователей и API-клиентов;
* ABAC/PBAC-политики;
* обращение к внешнему PDP, например Open Policy Agent;
* аудит решений авторизации;
* привязка прав к LDAP-иерархии объектов, тегов, тревог и коннекторов.

Бесплатная редакция не содержит политик и не включает enforcement без явного
подключения внешнего поставщика.
