.. _installation:

<<<<<<< HEAD
Установка
---------
=======
Установка и запуск
------------------
>>>>>>> peresvet/dev
Опишем самый простой случай установки и запуска платформы.

Системные требования:

#. Ubuntu 22.04
#. `Docker <https://docs.docker.com/engine/install/>`_.
   Для Docker не забудьте выполнить
   `настройку <https://docs.docker.com/engine/install/linux-postinstall/>`_.
#. `Git <https://git-scm.com/>`_.

<<<<<<< HEAD
Базовый способ развёртывания платформы - в виде docker-контейнеров.
=======
Запуск:
>>>>>>> peresvet/dev

#. Клонируем проект платформы:

   .. code:: sh

<<<<<<< HEAD
      $ git clone git@github.com:mp-co-ru/mpc-peresvet.git
=======
      $ git clone git@github.com:Vovaman/peresvet.git 
>>>>>>> peresvet/dev
#. Заходим в каталог проекта:

   .. code:: sh

<<<<<<< HEAD
      $ cd mpc-peresvet
=======
      $ cd peresvet
>>>>>>> peresvet/dev

#. Запускаем платформу:

   .. code:: sh

      $ ./run_one_app.sh

В результате будут запущены следующие компоненты платформы:

#. Брокер сообщений RabbitMQ
#. Служба каталогов OpenLDAP
#. База данных PostgreSQL (данные будут храниться внутри контейнера)
#. Ядро платформы
#. Клиент для отображения данных Grafana
<<<<<<< HEAD
#. Конфигуратор. Web-приложение для создания моделей.
=======
>>>>>>> peresvet/dev


