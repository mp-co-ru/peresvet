Настройка безопасности промышленной редакции
============================================

.. warning::

   Раздел описывает целевую схему безопасности промышленной редакции.
   В открытой редакции всего этого нет: она работает со встроенным
   поставщиком ``AllowAllAuthorizationProvider`` и разрешает все действия.
   Контракт ядра, на который опирается схема, описан в разделе
   :doc:`security_extension_points`.

Общая схема
-----------

Безопасность подключается надстройкой над ядром платформы:

.. code-block:: text

   Браузер / Grafana / внешняя программа
          |
          v
   nginx / API-шлюз / oauth2-proxy
          |
          v
   API Пересвета  --(AMQP + заголовки безопасности)-->  RabbitMQ
          |                                                |
          v                                                v
   OPA / сервер решений                           Внутренние сервисы
          ^
          |
   Атрибуты узлов из LDAP

Роли компонентов:

* **Сервер учётных записей (IdP)** — Keycloak или Authentik. Выдаёт токены
  JWT пользователям и внешним программам.
* **Точки проверки (PEP)** — API-шлюз и проверки в сервисах Пересвета
  (точка расширения ядра).
* **Сервер решений (PDP)** — Open Policy Agent или другой поставщик,
  который по запросу отвечает «разрешить» или «запретить».
* **Источники атрибутов (PIP)** — иерархия Пересвета в LDAP, данные токена
  JWT, кэш Redis.
* **RabbitMQ** — защищённый внутренний канал между сервисами.

Поставщик авторизации
---------------------

Промышленная редакция поставляет Python-модуль с поставщиком авторизации,
реализующим контракт ``src.common.authorization``. Ядро подключает его
переменной ``PRS_AUTH_PROVIDER``. Остальные переменные читает уже сам
поставщик; например:

.. code-block:: bash

   PRS_AUTH_PROVIDER=enterprise_security.opa_provider:OpaAuthorizationProvider
   PRS_SECURITY_MODE=enforce
   PRS_OPA_URL=http://opa:8181/v1/data/peresvet/allow
   PRS_SECURITY_AUDIENCE=peresvet-api
   PRS_SECURITY_ISSUER=https://keycloak.example.com/realms/peresvet

Рекомендуемые режимы работы поставщика:

* ``audit`` — принимать решения и записывать их в журнал, но ничего
  не блокировать;
* ``enforce`` — запрещать действия, на которые нет прав;
* ``disabled`` — только для диагностики, не для рабочей установки.

Токены пользователей
--------------------

Для пользователей, работающих через браузер:

* вход по OIDC Authorization Code;
* клиент в IdP — ``peresvet-ui`` или ``grafana``;
* Grafana настраивается через Generic OAuth;
* API получает заголовок ``Authorization: Bearer <access_token>``.

Минимальный набор полей токена:

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

``allowedObjectRoots`` — объекты иерархии, внутри которых пользователю
разрешено работать.

Токены внешних программ
-----------------------

Для интеграций и сервисных клиентов:

* получение токена по OAuth2 Client Credentials;
* отдельный клиент в IdP на каждую интеграцию;
* короткий срок жизни токена;
* разрешения и атрибуты ресурсов задаются полями клиента или через
  преобразователь токена (token mapper).

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

Постоянные API-токены допускаются только как функция совместимости. Для них
хранят лишь хеш, срок действия, владельца, разрешения, допустимые корни
иерархии, время последнего использования и признак отзыва.

Запрос к серверу решений
------------------------

Поставщик преобразует ``AuthorizationInput`` в стабильный JSON для сервера
решений.

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

Пример для внутреннего сообщения RabbitMQ:

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

Для рабочей установки:

* включите TLS для AMQP;
* заведите отдельный виртуальный хост на каждое окружение;
* заведите отдельного пользователя RabbitMQ для каждого сервиса;
* ограничьте права configure / read / write;
* не используйте учётные записи администратора в контейнерах сервисов;
* храните пароли в секретах Docker или Kubernetes.

Пример разделения прав:

.. code-block:: text

   tags_app_api:
     write: prsTag.app_api.*
     read:  очереди ответов

   tags_app:
     read:  prsTag.app_api.*
     write: prsTag.app.*

   connectors_mqtt_app:
     read/write: prsConnector.*, prsTag.app_api.data_set.*

Поставщик подписывает контекст безопасности в ``amqp_publish_headers``
и проверяет подпись при ``amqp.consume``. Контекст входящего сообщения
доступен следующей публикации через ``environment.amqp_context``.
Переносить исходного пользователя и идентификатор запроса дальше можно
только после проверки подписи, срока действия и того, что отправитель —
доверенный сервис.

Коннекторы MQTT
---------------

Для коннекторов:

* TLS или взаимная аутентификация по сертификатам (mTLS), либо отдельные
  учётные записи MQTT;
* отдельные права на топики и ключи маршрутизации для каждого коннектора;
* запрет записи в чужие теги: коннектор может писать только в теги,
  привязанные к нему в LDAP.

Рекомендуемое правило:

.. code-block:: text

   allow if
     subject.subject_type == "connector"
     and action == "prsTag.data_set"
     and every tagId in resource.tagIds is bound to subject.connectorId

Порядок внедрения
-----------------

#. Включить IdP и проверку токенов на API-шлюзе.
#. Подключить поставщика в режиме ``audit``.
#. Написать правила доступа для сервера решений и тесты к ним.
#. Включить проверку прав в HTTP API для чтения.
#. Включить проверку прав в HTTP API для записи и управления.
#. Включить TLS в RabbitMQ и отдельных пользователей для сервисов.
#. Включить проверку ``amqp.consume`` для важных сервисов.
#. Включить учётные записи коннекторов и права на топики.
#. Перевести поставщика в режим ``enforce``.

Проверки перед запуском в работу
--------------------------------

* Пользователь без прав получает ``403`` на запросы к модели, данным
  и управлению.
* Внешняя программа с токеном Client Credentials работает без входа
  в браузере или Grafana.
* Сервис не может публиковать сообщения с чужими ключами маршрутизации.
* Сервис отклоняет сообщение без действительного контекста безопасности.
* Коннектор не может писать в непривязанные к нему теги.
* В журнале решений есть субъект, действие, ресурс, решение и
  идентификатор запроса.
* Если сервер решений недоступен, запросы на запись и управление
  запрещаются.
