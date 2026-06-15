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

Контекст запроса
----------------

Во время обработки HTTP-запроса ядро сохраняет текущий ``Request`` в
context variable. Enterprise-поставщик может использовать его, чтобы прочитать:

* ``Authorization: Bearer ...``;
* IP-адрес клиента;
* путь и HTTP-метод;
* служебные заголовки reverse proxy.

Типы действий
-------------

Базовые CRUD-сервисы вызывают авторизацию с действиями вида:

* ``prsObject.create`` / ``prsObject.read`` / ``prsObject.update`` /
  ``prsObject.delete``;
* ``prsTag.create`` / ``prsTag.read`` / ``prsTag.update`` /
  ``prsTag.delete``;
* аналогично для ``prsAlert``, ``prsMethod``, ``prsConnector``,
  ``prsDataStorage``, ``prsSchedule``.

Операционные API вызывают отдельные действия:

* ``prsTag.data_get``;
* ``prsTag.data_set``;
* ``prsAlert.alarm_read``;
* ``prsAlert.alarm_ack``;
* ``prsConnector.connector_command``;
* ``prsConnector.connector_log_read``;
* ``prsConnector.service_log_read``.

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
