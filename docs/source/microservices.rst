Микросервисы
============
Базовые классы
--------------

Svc
~~~
Базовый класс для всех сервисов.

.. automodule:: svc
    :members:
    :private-members:
    :show-inheritance:

Settings
~~~~~~~~
Класс, от которого наследуются все классы-настройки для сервисов.

Определяет четыре переменные окружения:

**svc_name** - имя сервиса;

**amqp_url** - URL к брокеру сообщений;

**ldap_url** - URL к ldap-серверу;

**pub_exchange_type** - тип создаваемого обменника, в который сервис
будет публиковать свои сообщения.

.. automodule:: settings
    :members:
    :show-inheritance:

API_Crud_Svc
~~~~~~~~~~~~

.. automodule:: api_crud_svc
    :members:
