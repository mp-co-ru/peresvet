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

      $ git clone git@github.com:Vovaman/peresvet.git 
#. Заходим в каталог проекта:

   .. code:: sh

      $ cd peresvet

#. Запускаем платформу:

   .. code:: sh

      $ ./run_one_app.sh

В результате будут запущены следующие компоненты платформы:

#. Брокер сообщений RabbitMQ
#. Служба каталогов OpenLDAP
#. База данных PostgreSQL (данные будут храниться внутри контейнера)
#. Ядро платформы
#. Клиент для отображения данных Grafana


