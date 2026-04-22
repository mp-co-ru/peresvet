.. _administration:

Администрирование
=================

Раздел описывает операции сопровождения развёртывания, не относящиеся к
повседневной работе с моделью в конфигураторе.

.. _administration_ldap_backup:

Резервное копирование и восстановление OpenLDAP
-----------------------------------------------

Каталог OpenLDAP в контейнере хранит рабочие данные в каталоге
``/var/lib/ldap``. В файлах Docker Compose этот путь монтируется во
**внешний том** Docker (или в каталог на хосте при bind mount):

* ``docker/compose/docker-compose.ldap.one_app.yml`` — том
  ``ldap_data_one_app``;
* ``docker/compose/docker-compose.ldap.yml`` — том ``ldap_data``.

Имя тома в Docker обычно имеет вид
``<префикс_проекта_compose>_ldap_data_one_app`` или
``<префикс>_ldap_data``. Список томов::

   docker volume ls | grep ldap

Для согласованной копии базы LDAP перед снимком рекомендуется **остановить**
контейнер с ``slapd``. В проекте для этого предусмотрены оболочечные скрипты
(запуск из **корня репозитория**):

* ``docker/scripts/ldap/ldap_volume_backup.sh`` — создание архива;
* ``docker/scripts/ldap/ldap_volume_restore.sh`` — восстановление из архива.

Полный перечень переменных окружения и поведение по умолчанию описаны в
комментариях в начале каждого скрипта.

Создание бэкапа
~~~~~~~~~~~~~~~

Минимальный пример для стека с файлом
``docker/compose/docker-compose.ldap.one_app.yml``: перед снимком скрипт
может остановить сервис ``ldap`` через ``docker compose``, если задана
переменная ``COMPOSE_FILE``:

.. code:: sh

   COMPOSE_FILE=docker/compose/docker-compose.ldap.one_app.yml \
     ./docker/scripts/ldap/ldap_volume_backup.sh

По умолчанию архивы сохраняются в ``./ldap-backups``. Каталог вывода задаётся
переменной ``BACKUP_DIR``.

Если автоматический выбор тома по суффиксу ``_ldap_data_one_app`` /
``_ldap_data`` не подходит (несколько томов и т.п.), укажите том явно:

.. code:: sh

   LDAP_DOCKER_VOLUME=compose_ldap_data_one_app \
     ./docker/scripts/ldap/ldap_volume_backup.sh

Если данные LDAP смонтированы **каталогом на хосте** (bind mount), укажите
путь вместо работы с Docker-томом:

.. code:: sh

   LDAP_DATA_DIR=/путь/к/данным/ldap \
     ./docker/scripts/ldap/ldap_volume_backup.sh

.. note::

   Переменная ``SKIP_STOP=1`` позволяет не останавливать контейнеры перед
   чтением тома. Это ускоряет операцию, но повышает риск неконсистентного
   архива; используйте только при осознанной необходимости.

Восстановление из бэкапа
~~~~~~~~~~~~~~~~~~~~~~~~

Восстановление **перезаписывает** текущее содержимое целевого тома или
каталога: скрипт очищает данные в точке монтирования и распаковывает архив,
после чего снова запускает сервис LDAP (через ``docker compose`` или
``docker start`` для ранее остановленных контейнеров).

Пример для того же compose-файла; флаг ``-y`` отключает интерактивный запрос
подтверждения:

.. code:: sh

   COMPOSE_FILE=docker/compose/docker-compose.ldap.one_app.yml \
     ./docker/scripts/ldap/ldap_volume_restore.sh -y \
     ./ldap-backups/ИМЯ_АРХИВА.tar.gz

Целевой том можно передать **вторым аргументом** после пути к архиву либо
через ``LDAP_DOCKER_VOLUME``.

Восстановление в **каталог на хосте**:

.. code:: sh

   LDAP_DATA_DIR=/путь/к/данным/ldap \
     ./docker/scripts/ldap/ldap_volume_restore.sh -y \
     ./ldap-backups/ИМЯ_АРХИВА.tar.gz

.. warning::

   Убедитесь, что архив соответствует той же развёртке (образ и схема LDAP),
   что и целевое окружение. Конфигурация ``slapd`` в образе задаётся при
   сборке; в типовом compose в том сохраняется прежде всего содержимое
   ``/var/lib/ldap``.
