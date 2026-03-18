.. _installation:

Установка и запуск
------------------
Опишем самый простой случай установки и запуска платформы.

Системные требования:

#. Ubuntu 22.04
#. `Docker <https://docs.docker.com/engine/install/>`_.
   Для Docker не забудьте выполнить
   `настройку <https://docs.docker.com/engine/install/linux-postinstall/>`_.
#. `Git <https://git-scm.com/>`_.

Запуск:

#. Клонируем проект платформы:

   .. code:: sh

      $ git clone git@github.com:mp-co-ru/mpc-peresvet.git
#. Заходим в каталог проекта:

   .. code:: sh

      $ cd mpc-peresvet

#. Запускаем платформу:

   .. code:: sh

      $ ./run_one_app.sh

В результате будут запущены следующие компоненты платформы:

#. Брокер сообщений RabbitMQ
#. Служба каталогов OpenLDAP
#. База данных PostgreSQL (данные будут храниться внутри контейнера)
#. Ядро платформы
#. Клиент для отображения данных Grafana

Остановка платформы
-------------------
При остановке платформы необходимо гарантированно записать в теги, привязанные к
коннекторам, значение null (код качества 101). Поскольку LDAP, Redis и историческая
база работают в отдельных контейнерах (и могут быть на разных серверах), запись
должна выполняться *до* остановки контейнеров, пока все сервисы доступны.

Рекомендуемый порядок:

#. Вызвать HTTP-эндпоинт подготовки к остановке у приложения ``one_app``:
   ``POST /internal/prepare-shutdown``. Можно использовать скрипт
   ``docker/compose/prepare_shutdown.sh`` (см. ниже).
#. Подождать 2–3 секунды, чтобы сообщения ушли в очередь.
#. Остановить контейнеры (например, ``docker compose down``).

Эндпоинт ``/internal/prepare-shutdown`` принимает опциональный заголовок
``X-Prepare-Shutdown-Token``; если в окружении задана переменная
``PRS_PREPARE_SHUTDOWN_TOKEN``, заголовок обязан совпадать с ней.

Пример вызова с хоста (порт 8000 проброшен на one_app):

.. code:: sh

   curl -X POST "http://localhost:8000/internal/prepare-shutdown"

Или с токеном:

.. code:: sh

   curl -X POST -H "X-Prepare-Shutdown-Token: your-secret" "http://localhost:8000/internal/prepare-shutdown"

Скрипт ``docker/compose/prepare_shutdown.sh`` вызывает эндпоинт по адресу из
переменной ``ONE_APP_BASE_URL`` (по умолчанию ``http://localhost:8000``) и
опционально ``PRS_PREPARE_SHUTDOWN_TOKEN``. После успешного вызова можно
остановить стек (например, ``docker compose -f ... down``).
