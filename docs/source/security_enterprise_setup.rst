Настройка безопасности платной редакции
=======================================

.. warning::

   Этот раздел описывает целевую настройку промышленной платной редакции.
   Бесплатная редакция не включает ABAC/PDP/IdP и по умолчанию продолжает
   работать в permissive-режиме через ``AllowAllAuthorizationProvider``.

Общая схема
-----------

Платная редакция должна подключать безопасность как надстройку над базовым
ядром:

.. code-block:: text

   Browser/Grafana/API client
          |
          v
   nginx / API gateway / oauth2-proxy
          |
          v
   Peresvet API service  --(AMQP + security headers)-->  RabbitMQ
          |                                             |
          v                                             v
   OPA / PDP                                  Internal microservices
          ^
          |
   LDAP resource attributes

Роли компонентов:

* **IdP** — Keycloak или Authentik. Выдаёт JWT для пользователей и
  API-клиентов.
* **PEP** — API gateway и FastAPI hooks в сервисах Пересвета.
* **PDP** — Open Policy Agent или другой enterprise provider.
* **PIP** — LDAP-иерархия Пересвета, JWT claims, кэш Redis.
* **RabbitMQ** — защищённый внутренний транспорт между микросервисами.

Включение enterprise provider
-----------------------------

В платной редакции должен поставляться Python-провайдер, реализующий контракт из
``src.common.authorization``.

Пример переменных:

.. code-block:: bash

   PRS_AUTH_PROVIDER=enterprise_security.opa_provider:OpaAuthorizationProvider
   PRS_SECURITY_MODE=enforce
   PRS_OPA_URL=http://opa:8181/v1/data/peresvet/allow
   PRS_SECURITY_AUDIENCE=peresvet-api
   PRS_SECURITY_ISSUER=https://keycloak.example.com/realms/peresvet

Рекомендуемые режимы:

* ``audit`` — считать решения и писать аудит, но не блокировать;
* ``enforce`` — блокировать denied-запросы;
* ``disabled`` — только для диагностики, не для production.

JWT для пользователей
---------------------

Для интерактивных пользователей:

* flow: OIDC Authorization Code;
* клиент IdP: ``peresvet-ui`` или ``grafana``;
* Grafana настраивается через Generic OAuth;
* API получает ``Authorization: Bearer <access_token>``.

Минимальные claims:

.. code-block:: json

   {
     "sub": "user-uuid",
     "preferred_username": "operator1",
     "subject_type": "user",
     "roles": ["operator"],
     "groups": ["workshop-1"],
     "allowedObjectRoots": ["object-root-uuid"],
     "allowedApps": ["scada"],
     "aud": "peresvet-api",
     "iss": "https://keycloak.example.com/realms/peresvet"
   }

JWT для прямых API-клиентов
---------------------------

Для интеграций и сервисных клиентов:

* flow: OAuth2 Client Credentials;
* отдельный client в IdP на каждую интеграцию;
* короткоживущий access token;
* scopes и resource attributes выдаются через client claims или token mapper.

Пример:

.. code-block:: json

   {
     "sub": "service:mes-importer",
     "client_id": "mes-importer",
     "subject_type": "service",
     "scopes": ["peresvet:data:read", "peresvet:data:write"],
     "allowedObjectRoots": ["object-root-uuid"],
     "allowedActions": ["prsTag.data_get", "prsTag.data_set"],
     "tenant": "plant-a",
     "aud": "peresvet-api"
   }

Legacy API tokens допускаются только как enterprise-функция совместимости. Для
них необходимо хранить только hash, срок действия, owner, scopes, allowed roots,
last-used и статус отзыва.

OPA input
---------

Enterprise provider должен преобразовывать ``AuthorizationInput`` в стабильный
JSON для PDP.

Пример для HTTP API:

.. code-block:: json

   {
     "subject": {
       "sub": "user-uuid",
       "subject_type": "user",
       "roles": ["operator"],
       "allowedObjectRoots": ["object-root-uuid"]
     },
     "action": "prsTag.data_set",
     "resource": {
       "tagIds": ["tag-uuid"],
       "resolved": [
         {
           "id": "tag-uuid",
           "objectClass": "prsTag",
           "ancestors": ["object-root-uuid", "unit-uuid"],
           "attrs": {
             "prsActive": true,
             "prsEntityTypeCode": 1,
             "prsApp": ["scada"]
           }
         }
       ]
     },
     "environment": {
       "ip": "10.1.2.3",
       "method": "POST",
       "path": "/v1/data/"
     }
   }

Пример для RabbitMQ consumer:

.. code-block:: json

   {
     "subject": {
       "subject_type": "service",
       "service": "tags_app_api"
     },
     "action": "amqp.consume",
     "resource": {
       "service": "tags_app",
       "routing_key": "prsTag.app_api.data_set.*"
     },
     "environment": {
       "headers": {
         "x-prs-security-context": "signed-token"
       }
     }
   }

RabbitMQ
--------

Для production-инсталляции:

* включить TLS для AMQP;
* использовать отдельный vhost на окружение;
* создать отдельного RabbitMQ user для каждого микросервиса;
* ограничить configure/read/write permissions;
* запретить использование admin/root credentials в runtime-контейнерах;
* хранить credentials в Docker/Kubernetes secrets.

Пример принципа разделения:

.. code-block:: text

   tags_app_api:
     write: prsTag.app_api.*
     read:  callback queues

   tags_app:
     read:  prsTag.app_api.*
     write: prsTag.app.*

   connectors_mqtt_app:
     read/write: prsConnector.*, prsTag.app_api.data_set.*

Дополнительно enterprise provider должен подписывать AMQP security context в
``amqp_publish_headers`` и проверять его при ``amqp.consume``.

MQTT-коннекторы
---------------

Для MQTT-коннекторов:

* TLS/mTLS или отдельные MQTT credentials;
* отдельные topic/routing-key permissions на каждого коннектора;
* запрет публикации данных в чужие теги;
* ABAC-проверка: ``connectorId`` может писать только в теги, которые реально
  привязаны к этому коннектору в LDAP.

Рекомендуемое правило:

.. code-block:: text

   allow if
     subject.subject_type == "connector"
     and action == "prsTag.data_set"
     and every tagId in resource.tagIds is bound to subject.connectorId

Порядок внедрения
-----------------

1. Включить IdP и JWT-проверку на gateway.
2. Подключить enterprise provider в режиме ``audit``.
3. Настроить OPA policies и тесты политик.
4. Включить HTTP API enforcement для read-only.
5. Включить HTTP API enforcement для write/control операций.
6. Включить RabbitMQ TLS и per-service users.
7. Включить ``amqp.consume`` enforcement для критичных consumers.
8. Включить MQTT connector identity и topic permissions.
9. Перевести ``PRS_SECURITY_MODE=enforce``.

Проверки перед production
-------------------------

* пользователь без прав получает ``403`` на CRUD/data/control API;
* API-клиент с Client Credentials работает без browser/Grafana session;
* сервис не может публиковать в чужие routing keys;
* consumer отклоняет сообщение без валидного AMQP security context;
* коннектор не может писать в непривязанные теги;
* audit log содержит subject/action/resource/decision/request_id;
* отказ OPA обрабатывается согласно fail policy: для write/control — fail
  closed.
