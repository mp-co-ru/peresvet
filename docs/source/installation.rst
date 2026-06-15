.. _installation:

Установка и запуск
==================

Системные требования
--------------------

#. Ubuntu 22.04 (или совместимый Linux с Docker Engine).
#. `Docker <https://docs.docker.com/engine/install/>`_ с плагином ``docker compose``.
   Для Docker не забудьте выполнить
   `настройку <https://docs.docker.com/engine/install/linux-postinstall/>`_.
#. Для установки из исходников — `Git <https://git-scm.com/>`_.

После запуска поднимаются компоненты: RabbitMQ, OpenLDAP, PostgreSQL, ядро
платформы и Grafana.

Установка из продуктового дистрибутива
--------------------------------------

Рекомендуемый способ для конечного пользователя. Архив ``peresvet-product-<tag>.tar.gz``
публикуется в `GitHub Release <https://github.com/Vovaman/peresvet/releases>`_.
В архив входят Docker Compose-файлы, исходники runtime-сервисов, конфигурация,
PDF-документация, скрипт ``./run_one_app.sh``, файл ``.env`` с настройками по
умолчанию и список базовых образов ``packaging/required-images.manifest``.

Распаковка и запуск:

.. code:: sh

   $ tar -xzf peresvet-product-<tag>.tar.gz
   $ cd peresvet-product-<tag>
   $ ./run_one_app.sh

Файл ``.env``
~~~~~~~~~~~~~

Параметры по умолчанию задаются в файле ``.env`` в корне распакованного архива.
Перед первым запуском при необходимости отредактируйте его:

.. code:: env

   PRS_REGISTRY_MIRROR=10.14.143.57:5000
   PRS_HOSTNAME=
   PRS_SSL=false
   PRS_BUILD=false
   PRS_SKIP_IMAGE_PULL=0

Приоритет настроек: ``.env`` → переменные окружения shell → аргументы CLI
(``--hostname``, ``--mirror`` и т.д.).

+-----------------------+----------------------------------------------------------+
| Переменная            | Назначение                                               |
+=======================+==========================================================+
| ``PRS_REGISTRY_MIRROR`` | Адрес зеркала базовых образов (``host:port``). Пусто —   |
|                       | pull с Docker Hub.                                       |
+-----------------------+----------------------------------------------------------+
| ``PRS_HOSTNAME``      | Имя сервера для nginx. Пусто — имя текущего хоста.      |
+-----------------------+----------------------------------------------------------+
| ``PRS_SSL``           | ``true`` / ``false`` — HTTPS-вариант nginx.              |
+-----------------------+----------------------------------------------------------+
| ``PRS_BUILD``         | ``true`` / ``false`` — пересборка локальных образов.     |
+-----------------------+----------------------------------------------------------+
| ``PRS_SKIP_IMAGE_PULL`` | ``1`` — не скачивать базовые образы перед запуском.    |
+-----------------------+----------------------------------------------------------+

Примеры:

.. code:: sh

   $ ./run_one_app.sh --hostname prod-oee
   $ ./run_one_app.sh --build true
   $ ./run_one_app.sh --mirror mirror.example.com:5000

Зеркало базовых образов
~~~~~~~~~~~~~~~~~~~~~~~

Дистрибутив **не содержит** Docker-образы. При установке ``./run_one_app.sh``
проверяет наличие базовых образов локально и скачивает только отсутствующие.

Если Docker Hub недоступен, укажите **зеркало образов продукта** — registry,
на котором заранее опубликован фиксированный набор образов, необходимых для
работы платформы. Адрес задаётся в ``PRS_REGISTRY_MIRROR`` (файл ``.env``) или
ключом ``--mirror``.

.. important::

   **Не** добавляйте адрес зеркала в ``registry-mirrors`` файла
   ``/etc/docker/daemon.json``. Такая настройка перенаправляет **все** обращения
   к ``docker.io`` на указанный registry, в том числе при последующих ручных
   ``docker pull`` посторонних образов. Скрипт ``./run_one_app.sh`` обращается к
   зеркалу **явно** и не меняет глобальное поведение Docker на хосте.

Список базовых образов — в ``packaging/required-images.manifest``:

.. code:: text

   redis/redis-stack:7.2.0-v6
   rabbitmq:4.1.1-management
   postgres:16.1
   python:3.12-slim
   osixia/openldap
   grafana/grafana-enterprise:12.4.0-22081664032-ubuntu
   nginx:1.25.3-alpine-slim

На зеркале каждый образ должен быть доступен по тому же пути и тегу, например:
``10.14.143.57:5000/postgres:16.1``.

Для HTTP-зеркала (без TLS) добавьте хост в ``insecure-registries`` в
``/etc/docker/daemon.json`` — это **не** то же самое, что ``registry-mirrors``:

.. code:: json

   {
     "insecure-registries": ["10.14.143.57:5000"]
   }

После изменения перезапустите Docker: ``sudo systemctl restart docker``.

Чтобы отключить зеркало и использовать Docker Hub, очистите переменную в ``.env``:

.. code:: env

   PRS_REGISTRY_MIRROR=

Если все образы уже загружены на сервер:

.. code:: sh

   $ PRS_SKIP_IMAGE_PULL=1 ./run_one_app.sh

Локальные секреты (например, ``GRAFANA_SERVICE_ACCOUNT_TOKEN``) можно вынести в
``docker/compose/.cont_one_app.secrets.env`` — шаблон:
``docker/compose/.cont_one_app.secrets.env.example``.

HTTPS
~~~~~

HTTPS включается ``PRS_SSL=true`` в ``.env`` или ``--ssl true``. Серверный
сертификат должен быть подготовлен до запуска; подробности — в README репозитория
(раздел «Запуск HTTPS-варианта»).

Установка из исходников (для разработки)
----------------------------------------

#. Клонируйте проект:

   .. code:: sh

      $ git clone git@github.com:mp-co-ru/mpc-peresvet.git

#. Перейдите в каталог и при необходимости настройте ``.env`` (см. выше).

#. Запустите платформу:

   .. code:: sh

      $ ./run_one_app.sh

Сборка продуктового дистрибутива
--------------------------------

Для подготовки архива релиза (из корня репозитория):

.. code:: sh

   $ ./packaging/build_product_distribution.sh
   $ ./packaging/build_product_distribution.sh --output dist/peresvet-product-<tag>.tar.gz

Архив создаётся в каталоге ``dist/``. При push тега на ветку ``main`` сборка
выполняется workflow ``.github/workflows/product_distribution.yml`` и прикрепляется
к GitHub Release.

Остановка платформы
-------------------

Остановите контейнеры, например:

.. code:: sh

   $ docker compose -f docker/compose/docker-compose.redis.yml down
   $ # или остановите все контейнеры проекта compose вручную
