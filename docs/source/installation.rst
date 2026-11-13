.. _installation:

Установка и запуск
==================

Платформа поставляется набором Docker-контейнеров и запускается одним
скриптом ``./run_one_app.sh``. Скрипт скачивает недостающие базовые образы,
собирает образы платформы и поднимает контейнеры в фоне:

* RabbitMQ — брокер сообщений между сервисами;
* Redis — кэш;
* OpenLDAP — хранилище иерархии модели;
* PostgreSQL — хранилище истории тегов по умолчанию;
* ядро платформы (контейнер ``one_app``);
* сервисы захвата и отдачи видео;
* Grafana с конфигуратором модели;
* nginx — единая точка входа по HTTPS.

Первый запуск занимает несколько минут.

Системные требования
--------------------

#. Linux-сервер с `Docker Engine <https://docs.docker.com/engine/install/>`_
   и плагином ``docker compose``. После установки Docker выполните
   `настройку прав <https://docs.docker.com/engine/install/linux-postinstall/>`_,
   чтобы команды ``docker`` работали без ``sudo``.
#. ``python3`` на сервере — только если образы скачиваются с зеркала
   (см. `Зеркало образов`_).
#. `Git <https://git-scm.com/>`_ — только для установки из исходников.

Установка из дистрибутива
-------------------------

Рекомендуемый способ. Архив ``peresvet-product-<tag>.tar.gz`` публикуется
в `релизах на GitHub <https://github.com/Vovaman/peresvet/releases>`_.
В нём Docker Compose-файлы, исходный код сервисов, конфигурация,
PDF-документация, скрипт ``./run_one_app.sh`` и файл настроек ``.env``.
Docker-образов в архиве нет: их скачивает скрипт запуска.

#. Распакуйте архив:

   .. code:: sh

      $ tar -xzf peresvet-product-<tag>.tar.gz
      $ cd peresvet-product-<tag>

#. Впишите в файл ``.env`` IPv4-адрес сервера:

   .. code:: text

      PRS_IP=192.168.1.10

   На этот адрес выпускается HTTPS-сертификат. Без него скрипт
   остановится с предупреждением.

#. Запустите платформу:

   .. code:: sh

      $ ./run_one_app.sh

Установка из исходников
-----------------------

Для разработки платформу запускают прямо из репозитория:

.. code:: sh

   $ git clone git@github.com:mp-co-ru/peresvet.git
   $ cd peresvet
   $ ./run_one_app.sh --ip 192.168.1.10

Настройки ``.env`` и ключи скрипта те же, что у дистрибутива.

Первый вход
-----------

Когда запустится контейнер ``prs-nginx-one-app``, откройте в браузере
``https://<адрес из PRS_IP>/grafana``. На самом сервере работает и
``https://localhost/grafana``.

Сертификат самоподписанный, поэтому браузер предупредит, что не доверяет ему.
Для внутреннего стенда это нормально: подтвердите переход.

Имя и пароль при первом входе — ``admin`` / ``admin``. Grafana сразу
предложит сменить пароль. После входа откроется
:ref:`конфигуратор модели <configurator>`.

Настройки запуска
-----------------

Настройки по умолчанию лежат в файле ``.env`` рядом со скриптом.
Переменная окружения с тем же именем перекрывает значение из ``.env``,
а ключ командной строки перекрывает и то, и другое.

.. list-table::
   :header-rows: 1
   :widths: 26 20 54

   * - Переменная ``.env``
     - Ключ скрипта
     - Назначение
   * - ``PRS_IP``
     - ``--ip``
     - IPv4-адрес сервера для самоподписанного сертификата.
       Обязателен, если не включён ``PRS_SSL``.
   * - ``PRS_HOSTNAME``
     - ``--hostname``
     - Имя сервера для nginx. Пусто — имя текущего компьютера.
   * - ``PRS_SSL``
     - ``--ssl``
     - ``false`` (по умолчанию) — самоподписанный сертификат на ``PRS_IP``.
       ``true`` — заранее подготовленные сертификаты, см. `HTTPS`_.
   * - ``PRS_BUILD``
     - ``--build``
     - ``true`` — пересобрать образы платформы перед запуском.
   * - ``PRS_REGISTRY_MIRROR``
     - ``--mirror``
     - Адрес зеркала базовых образов. Пусто — образы берутся с Docker Hub.
   * - ``PRS_SKIP_IMAGE_PULL``
     - —
     - ``1`` — не проверять и не скачивать базовые образы перед запуском.
   * - ``PRS_MCP_PERESVET``
     - ``--mcp-peresvet``
     - ``true`` — запустить MCP-сервер платформы (:ref:`mcp`).
   * - ``PRS_MCP_GRAFANA``
     - ``--mcp-grafana``
     - ``true`` — запустить MCP-сервер Grafana.

Ключ ``--tmpdir <каталог>`` задаёт каталог для временных файлов при
скачивании образов с зеркала. По умолчанию это ``/tmp``; если там маленький
``tmpfs``, укажите каталог на диске, например ``--tmpdir /var/tmp``.
Полный список ключей выводит ``./run_one_app.sh --help``.

Примеры:

.. code:: sh

   $ ./run_one_app.sh --ip 192.168.1.10
   $ ./run_one_app.sh --hostname prod-oee
   $ ./run_one_app.sh --build true
   $ ./run_one_app.sh --mirror https://mirror.example.com/dist/images

Пароли и токены, которые не должны попадать в репозиторий, кладут в файл
``docker/compose/.cont_one_app.secrets.env``. Шаблон —
``docker/compose/.cont_one_app.secrets.env.example``. Если файл есть,
скрипт подключает его автоматически.

HTTPS
-----

Платформа всегда работает по HTTPS. Запросы на порт HTTP nginx
перенаправляет на HTTPS.

**Самоподписанный сертификат** (``PRS_SSL=false``, по умолчанию).
При старте контейнер nginx сам выпускает сертификат. В сертификат попадают
адрес ``PRS_IP``, ``127.0.0.1``, ``localhost`` и имя сервера, если оно
годится для DNS.

**Свои сертификаты** (``PRS_SSL=true``). Nginx берёт готовые файлы
из ``certificates/tls/servers/<имя сервера>/`` и ничего не выпускает.
``PRS_IP`` в этом режиме не нужен.

.. note::

   Если платформа обновлена с версии, где nginx ещё не выпускал сертификат
   сам, один раз пересоберите образы: ``./run_one_app.sh --build true``.

Зеркало образов
---------------

Если Docker Hub с сервера недоступен, базовые образы можно скачивать
с зеркала — registry, где заранее опубликован нужный платформе набор
образов. Адрес задаётся переменной ``PRS_REGISTRY_MIRROR`` или ключом
``--mirror`` и обязательно начинается со схемы ``http://`` или ``https://``:

.. code:: text

   PRS_REGISTRY_MIRROR=https://mpcperesvet.matchpoint-consulting.ru/dist/images
   PRS_REGISTRY_MIRROR=http://127.0.0.1:5000

Как скрипт работает с образами:

* образы, которые уже есть на сервере, повторно не скачиваются;
* недостающие образы сначала запрашиваются с зеркала, а если оно
  недоступно — с Docker Hub;
* пока идут попытки скачать с зеркала, сочетание ``Ctrl+I`` переключает
  все оставшиеся образы этого запуска на Docker Hub;
* скрипт обращается к зеркалу напрямую по HTTP(S), для этого ему нужен
  ``python3``. Настройки Docker на сервере не меняются.

.. important::

   Не добавляйте адрес зеркала в ``registry-mirrors`` файла
   ``/etc/docker/daemon.json``. Такая настройка перенаправит на зеркало
   **все** обращения Docker к Docker Hub, в том числе ваши ручные
   ``docker pull`` посторонних образов.

Список нужных образов лежит в ``packaging/required-images.manifest``.
На зеркале образ должен лежать по тому же пути и с тем же тегом.
Официальные образы Docker Hub без пространства имён хранятся
под префиксом ``library/``: образ ``postgres:16.1`` ищется как
``library/postgres:16.1``.

Чтобы отказаться от зеркала, оставьте переменную пустой:
``PRS_REGISTRY_MIRROR=``. Если все образы уже загружены на сервер,
проверку можно пропустить: ``PRS_SKIP_IMAGE_PULL=1 ./run_one_app.sh``.

Остановка платформы
-------------------

Из каталога со скриптом ``./run_one_app.sh`` выполните ``down`` для того же
набора compose-файлов, с которым платформа запускалась:

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

Если платформа запускалась со своими сертификатами (``--ssl true``),
замените ``docker-compose.nginx.one_app.yml`` на
``docker-compose.nginx.one_app.ssl.yml``.

Команда ``down`` удаляет контейнеры и сеть проекта. Данные остаются
в томах Docker: иерархия LDAP, история PostgreSQL, настройки Grafana,
видеоархив. Следующий ``./run_one_app.sh`` подхватит их.

.. _optional-services:

Дополнительные сервисы
----------------------

Некоторые сервисы нужны не каждому заказчику. Они не входят ни в команду
``./run_one_app.sh``, ни в архив ``peresvet-product-*.tar.gz``, и их ставят
после того, как платформа уже запущена.

Такие сервисы бывают двух видов:

* **Со своим портом.** Контейнер публикует порт на сервере, и клиенты
  обращаются к нему напрямую, минуя nginx.
* **Через nginx.** Своего порта на сервере у контейнера нет. Клиент
  обращается на порт 443 платформы, а nginx передаёт запрос контейнеру
  во внутренней сети ``peresvet``. Так работают MCP-серверы (:doc:`mcp`)
  и распознавание видео.

.. _optional-own-port:

Сервис со своим портом
~~~~~~~~~~~~~~~~~~~~~~

Такой сервис узнаётся по compose-файлу: в нём есть секция ``ports:``,
и к нему не прилагается файл для ``config/nginx/optional/``.

#. Положите compose-файл сервиса в ``docker/compose/`` и выполните команду
   из корня установки. Тогда контейнер попадёт в проект ``compose`` и в сеть
   ``peresvet``. Если в файле есть ``depends_on: one_app``, добавьте
   в команду файл ядра ``-f docker/compose/docker-compose.one_app.yml``,
   иначе Compose не найдёт зависимость. В ``up`` указывайте имя сервиса,
   чтобы не пересоздавать контейнеры ядра:

   .. code:: sh

      $ docker compose --env-file docker/compose/.cont_one_app.env \
          -f docker/compose/docker-compose.one_app.yml \
          -f docker/compose/docker-compose.<сервис>.yml \
          up -d --build <сервис>

#. Проверьте, что сервис отвечает на своём порту сервера.

Останавливают сервис командой ``stop <сервис>`` с тем же набором ``-f``.
Команду ``down`` здесь не используйте: в списке есть файл ядра, и ``down``
остановит ``one_app`` вместе с дополнительным сервисом.

.. _optional-via-nginx:

Сервис через nginx
~~~~~~~~~~~~~~~~~~

**MCP-серверы.** MCP-сервер платформы и MCP-сервер Grafana входят
в поставку, но по умолчанию выключены. Их включают ключами скрипта запуска
или переменными ``PRS_MCP_PERESVET`` и ``PRS_MCP_GRAFANA`` в ``.env``:

.. code:: sh

   $ ./run_one_app.sh --mcp-peresvet true --mcp-grafana true

Те же ключи понимают ``run_one_app_dev.sh``, ``run_one_app_dev_no_build.sh``
и ``run_one_app_ssl_letsencrypt.sh``. При ``true`` скрипт запускает
контейнер и копирует его маршрут из ``config/nginx/mcp/``
в ``config/nginx/optional/``. При ``false`` удаляет маршрут и останавливает
контейнер. Адреса серверов:

* ``https://<хост>/mcp/peresvet`` — MCP платформы; проверка работы —
  ``https://<хост>/mcp/peresvet/health``;
* ``https://<хост>/mcp/grafana`` — MCP Grafana.

**Другие сервисы.** Сервис, о котором скрипт запуска не знает, подключают
вручную. Так, например, подключается распознавание видео: его поставляют
отдельным комплектом. Пока распознавание не подключено, адрес
``/v1/vision/overlay`` отвечает 404.

#. Запустите контейнер из корня установки, указав имя сервиса в ``up``:

   .. code:: sh

      $ docker compose --env-file docker/compose/.cont_one_app.env \
          -f docker/compose/docker-compose.<сервис>.yml \
          up -d --build <сервис>

#. Положите файл маршрута ``config/nginx/optional/<сервис>.conf``. Обычно он
   идёт в комплекте сервиса. Каталог ``config/nginx/optional/`` смонтирован
   в контейнер nginx и подключён строкой ``include conf.d/optional/*.conf``.
   Файл ``00-empty.conf`` не удаляйте: без единого ``.conf`` в каталоге nginx
   не запустится.

   Файл маршрута — готовый конфиг nginx, подстановок ``${...}`` в нём нет.
   Имя контейнера в ``proxy_pass`` задавайте через переменную: буквальное
   имя nginx проверяет при старте и не запустится, пока такого контейнера
   нет. Маршрут распознавания видео выглядит так:

   .. code:: nginx

      location = /v1/vision/overlay {
          proxy_set_header Host $host;
          proxy_read_timeout 5s;
          set $prs_methods_video prs-methods-video;
          proxy_pass http://$prs_methods_video:8093/api/overlay$is_args$args;
      }

#. Проверьте конфиг и перечитайте его. Пересобирать образ nginx не нужно:

   .. code:: sh

      $ docker exec prs-nginx-one-app nginx -t \
          && docker exec prs-nginx-one-app nginx -s reload

Отключают сервис в обратном порядке. Удалите ``<сервис>.conf``
(``00-empty.conf`` оставьте), снова выполните ``nginx -t`` и
``nginx -s reload``, затем остановите контейнер командой только с его
compose-файлом, без файлов ядра:

.. code:: sh

   $ docker compose --env-file docker/compose/.cont_one_app.env \
       -f docker/compose/docker-compose.<сервис>.yml \
       stop <сервис>

Команда остановки платформы из раздела `Остановка платформы`_
дополнительные сервисы не затрагивает: их compose-файлов в ней нет.

Сборка дистрибутива
-------------------

Архив для релиза собирают из корня репозитория:

.. code:: sh

   $ ./packaging/build_product_distribution.sh
   $ ./packaging/build_product_distribution.sh --output dist/peresvet-product-<tag>.tar.gz

Архив появляется в каталоге ``dist/``. Когда в репозиторий публикуется тег
на коммите из ветки ``main``, архив собирает workflow ``.github/workflows/product_distribution.yml``
и прикрепляет его к релизу на GitHub.
