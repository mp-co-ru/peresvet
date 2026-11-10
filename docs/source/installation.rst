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
Перед первым запуском укажите IPv4-адрес сервера в ``PRS_IP``:

.. code:: text

   PRS_REGISTRY_MIRROR=10.14.143.57:5000
   PRS_HOSTNAME=
   PRS_IP=192.168.1.10
   PRS_SSL=false
   PRS_BUILD=false
   PRS_SKIP_IMAGE_PULL=0

Приоритет настроек: ``.env`` → переменные окружения shell → аргументы CLI
(``--ip``, ``--hostname``, ``--mirror`` и т.д.).

.. list-table::
   :header-rows: 1
   :widths: 32 68

   * - Переменная
     - Назначение
   * - ``PRS_REGISTRY_MIRROR``
     - Адрес зеркала базовых образов (``host:port``). Пусто — pull с Docker Hub.
   * - ``PRS_HOSTNAME``
     - Имя сервера для nginx. Пусто — имя текущего хоста.
   * - ``PRS_IP``
     - IPv4-адрес сервера для самоподписанного HTTPS-сертификата.
       Пусто — скрипт предупреждает и останавливается. Ключ ``--ip`` перекрывает значение.
   * - ``PRS_SSL``
     - ``false`` (по умолчанию) — HTTPS с самоподписанным сертификатом
       на адрес ``PRS_IP``. ``true`` — HTTPS с заранее подготовленными
       сертификатами; ``PRS_IP`` не нужен.
   * - ``PRS_BUILD``
     - ``true`` / ``false`` — пересборка локальных образов.
   * - ``PRS_SKIP_IMAGE_PULL``
     - ``1`` — не скачивать базовые образы перед запуском.

Примеры:

.. code:: sh

   $ ./run_one_app.sh
   $ ./run_one_app.sh --ip 192.168.1.10
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
   ubuntu:26.04
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

.. code:: text

   PRS_REGISTRY_MIRROR=

Если все образы уже загружены на сервер:

.. code:: sh

   $ PRS_SKIP_IMAGE_PULL=1 ./run_one_app.sh

Локальные секреты можно вынести в ``docker/compose/.cont_one_app.secrets.env`` —
шаблон: ``docker/compose/.cont_one_app.secrets.env.example``.

HTTPS
~~~~~

Обычный запуск поднимает платформу по HTTPS. Контейнер nginx при старте
выпускает самоподписанный сертификат на IPv4-адрес из ``PRS_IP``.
Ключ ``--ip`` перекрывает значение из ``.env``.
Туда же попадают ``127.0.0.1``, ``localhost`` и, если имя подходит для DNS,
значение ``--hostname`` (или имя компьютера). Если адрес не задан, скрипт
останавливается и просит указать его.

Браузер предупредит, что сертификат не из доверенного центра: для стенда
это ожидаемо. Порт HTTP перенаправляет на HTTPS.
Откройте ``https://<адрес из PRS_IP>/grafana``.

После обновления платформы один раз пересоберите образ nginx, чтобы в него
попал скрипт выпуска сертификата:

.. code:: sh

   $ ./run_one_app.sh --build true

``PRS_SSL=true`` или ``--ssl true`` — другой режим. Nginx берёт заранее
подготовленные сертификаты из ``certificates/tls/servers/<имя>/`` и сам их
не выпускает. ``PRS_IP`` в этом режиме не нужен.

Установка из исходников (для разработки)
----------------------------------------

#. Клонируйте проект:

   .. code:: sh

      $ git clone git@github.com:mp-co-ru/mpc-peresvet.git

#. Перейдите в каталог и при необходимости настройте ``.env`` (см. выше).

#. Запустите платформу:

   .. code:: sh

      $ ./run_one_app.sh

.. _optional-services:

Дополнительные сервисы
----------------------

``./run_one_app.sh`` поднимает ядро: RabbitMQ, OpenLDAP, PostgreSQL,
``one_app``, захват и отдачу видео, Grafana и nginx. Сервис, который стоит
не у каждого заказчика, в эту команду и в архив ``peresvet-product-*.tar.gz``
не входит. Его ставят после того, как платформа уже запущена.

Таких сервисов два типа, и запуск у них разный.

* Свой порт. Контейнер публикует порт на хост, клиент ходит на него
  напрямую. Nginx в этом не участвует.
* Через nginx. Снаружи порта нет, запрос приходит на 443 платформы,
  nginx передаёт его контейнеру в сети ``peresvet``. Так работают
  MCP-серверы платформы и Grafana (:doc:`mcp`) и так подключается
  распознавание видео. Распознавание в стандартную поставку не входит:
  пока файла маршрута нет, ``/v1/vision/overlay`` отвечает 404.
  MCP-серверы в поставку входят, но по умолчанию не запускаются.

.. _optional-own-port:

Свой порт
~~~~~~~~~

В compose-файле такого сервиса есть секция ``ports:`` и нет файла
в ``config/nginx/optional/``.

#. Файл сервиса лежит в ``docker/compose/``. Команду выполняйте из корня
   поставки: имя проекта остаётся ``compose``, контейнер попадает в сеть
   ``peresvet``. Если в файле есть ``depends_on: one_app``, добавьте
   в ту же команду ``-f docker/compose/docker-compose.one_app.yml``,
   иначе Compose не увидит зависимость. ``up`` вызывайте с именем
   сервиса, чтобы не пересоздавать ядро:

   .. code:: sh

      $ docker compose --env-file docker/compose/.cont_one_app.env \
          -f docker/compose/docker-compose.one_app.yml \
          -f docker/compose/docker-compose.<сервис>.yml \
          up -d --build <сервис>

#. Проверьте опубликованный порт на хосте, а не адрес nginx.

Остановка — ``stop`` этого сервиса тем же набором ``-f``.
``down`` здесь не используйте: в команде есть файл ядра, и ``down``
остановит ``one_app`` вместе с дополнительным сервисом.

.. _optional-via-nginx:

Через nginx
~~~~~~~~~~~

У такого сервиса в compose нет ``ports:`` на хост. Снаружи его публикует
уже запущенный ``prs-nginx-one-app``.

MCP-серверы платформы и Grafana включаются ключами скрипта запуска.
По умолчанию оба равны ``false``. Те же ключи есть у
``run_one_app.sh``, ``run_one_app_dev.sh``, ``run_one_app_dev_no_build.sh``
и ``run_one_app_ssl_letsencrypt.sh``. Значения по умолчанию задаются
в ``.env`` (``PRS_MCP_PERESVET``, ``PRS_MCP_GRAFANA``), ключ командной
строки их перекрывает.

.. code:: sh

   $ ./run_one_app.sh --mcp-peresvet true --mcp-grafana true

При ``true`` скрипт добавляет compose-файл сервера и копирует его маршрут
из ``config/nginx/mcp/`` в ``config/nginx/optional/``. При ``false``
удаляет маршрут и останавливает контейнер. Снаружи адреса такие:

* ``https://<хост>/mcp/peresvet`` — MCP платформы, проверка
  ``https://<хост>/mcp/peresvet/health``;
* ``https://<хост>/mcp/grafana`` — MCP Grafana.

Дальше описан тот же приём для сервиса, который скрипт запуска не знает.
Распознавание видео подключается именно так, его комплектом, не поставкой
платформы.

#. Поднимите контейнер из корня поставки. ``up`` — с именем сервиса:

   .. code:: sh

      $ docker compose --env-file docker/compose/.cont_one_app.env \
          -f docker/compose/docker-compose.<сервис>.yml \
          up -d --build <сервис>

#. Комплект сервиса кладёт готовый файл
   ``config/nginx/optional/<сервис>.conf``. Каталог смонтирован в nginx
   и подключён строкой ``include conf.d/optional/*.conf``.
   ``00-empty.conf`` не удаляйте: без единого ``.conf`` nginx не стартует.
   Это готовый конфиг, не шаблон: подстановки ``${...}`` в нём нет.

   Имя контейнера в ``proxy_pass`` пишите через переменную. Буквальное
   имя nginx проверяет при старте и не поднимется, пока контейнера нет.
   Для распознавания комплект сервиса (не поставка платформы) кладёт
   такой файл:

   .. code:: nginx

      location = /v1/vision/overlay {
          proxy_set_header Host $host;
          proxy_read_timeout 5s;
          set $prs_methods_video prs-methods-video;
          proxy_pass http://$prs_methods_video:8093/api/overlay$is_args$args;
      }

#. Перечитайте конфиг. Образ nginx пересобирать не нужно:

   .. code:: sh

      $ docker exec prs-nginx-one-app nginx -t \
          && docker exec prs-nginx-one-app nginx -s reload

Снятие идёт в обратную сторону. Сначала удалите ``<сервис>.conf``
(``00-empty.conf`` оставьте) и снова выполните ``nginx -t`` и
``nginx -s reload``. Затем остановите контейнер командой с одним
его ``-f``, без файлов ядра:

.. code:: sh

   $ docker compose --env-file docker/compose/.cont_one_app.env \
       -f docker/compose/docker-compose.<сервис>.yml \
       stop <сервис>

Остановка ядра командой из раздела «Остановка» дополнительный сервис
не гасит: его файла в том списке нет.

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

Из корня проекта остановите тот же набор compose-файлов, с которым
платформу поднимает ``./run_one_app.sh``. Для обычного запуска
(HTTPS с самоподписанным сертификатом):

.. code:: sh

   $ docker compose --env-file docker/compose/.cont_one_app.env \
     -f docker/compose/docker-compose.redis.yml \
     -f docker/compose/docker-compose.rabbitmq.yml \
     -f docker/compose/docker-compose.ldap.one_app.yml \
     -f docker/compose/docker-compose.postgresql.data_in_volume.yml \
     -f docker/compose/docker-compose.one_app.yml \
     -f docker/compose/docker-compose.video.yml \
     -f docker/compose/docker-compose.grafana.yml \
     -f docker/compose/docker-compose.nginx.one_app.yml \
     -f docker/compose/docker-compose.ports.yml \
     -f docker/compose/docker-compose.restart.yml \
     down

Для варианта с заранее подготовленными сертификатами (``--ssl true``)
замените ``docker-compose.nginx.one_app.yml`` на
``docker-compose.nginx.one_app.ssl.yml``.
Команда ``down`` останавливает контейнеры и удаляет сеть проекта.
Тома с данными LDAP, PostgreSQL, Grafana и видеоархивом остаются.
