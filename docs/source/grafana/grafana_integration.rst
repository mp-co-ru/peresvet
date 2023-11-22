Интеграция с Grafana
====================

.. note::
   Описание интеграции приводится для операционных систем Linux (Ubuntu/Debian)
   и MacOS с установленными `git <https://git-scm.com/>`_ и
   `Docker <https://docs.docker.com/engine/install/>`_. Для Docker не забудьте
   выполнить
   `настройку <https://docs.docker.com/engine/install/linux-postinstall/>`_.

Далее - пошаговый процесс интеграции Grafana и платформы МПК-Пересвет.

#. Запускаем все необходимые сервисы платформы МПК-Пересвет в Docker, для чего:

   #. Открываем консоль и переходим в папку, где будет расположен проект
      платформы:

      .. code:: bash

         $ cd <путь до папки>

   #. Клонируем проект:

      .. code:: bash

         $ git clone https://github.com/mp-co-ru/mpc-peresvet.git

   #. Переходим в папку проекта:

      .. code:: bash

         $ cd mpc-peresvet

   #. Запускаем платформу:

      .. code:: bash

         $ ./run.sh

   #. При первом запуске платформы после запуска всех сервисов в терминале 
      необходимо перейти в папку с логами сервисов с помощью команды 

      .. code:: bash

         $ cd docker/compose/logs

      Далее выполните команду 

      .. code:: bash

         $ chown -R $USER:1024 . && chmod -R 777 .

      Перейдите обратно в корневую директорию проекта командой `cd ../../..`.
      Перезапустите все сервисы командой 
      
      .. code:: bash

         $ ./run.sh

#. Запускаем Grafana

   Запуск возможен несколькими способами

   **Linux**

   #. Установить зависимости

      .. code-block:: sh

         sudo apt-get install -y apt-transport-https software-properties-common wgetsudo apt-get install -y apt-transport-https software-properties-common wget

   #. Импортируем GPG ключ

      .. code-block:: sh

         sudo mkdir -p /etc/apt/keyrings/
         wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null

   #. Создаем директорию для версий Grafana

      .. code-block:: sh

         echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee -a /etc/apt/sources.list.d/grafana.list

   #. Обновляем пакеты

      .. code-block:: sh

         sudo apt-get update

   #. Устанавливаем Grafana

      .. code-block:: sh

         sudo apt-get install grafana-enterprise

   #. Запуск Grafana

      .. code-block:: sh

         sudo systemctl daemon-reload
         sudo systemctl start grafana-server
         sudo systemctl status grafana-server

   **Docker**

   #. Запускаем контейнер с Grafana

      .. code-block:: sh

         docker run -d -p 3000:3000 --name=grafana --network=<название сети с платформой Пересвет, по умолчанию compose_default> \
         grafana/grafana-enterprise

      .. note::
         Флаг --network добавлен для того, чтобы контейнер Grafana запустилась в сети,
         в которой запущена платформа Пересвет

   **MacOS**

   #.

      .. code-block:: sh

         brew update
         brew install grafana

   #.

      .. code-block:: sh

         brew services start grafana

   .. note::

      По умолчанию Grafana запускает сервер на порту 3000. Если необходимо изменить порт, то это можно сделать с помощью инструмента
      `grafana-cli`.

      **Linux/MacOS**

      #. В любом терминале перейдите в директорию Grafana

         .. code-block:: sh

            cd <путь к корневой директории Grafana>/bin

      #. Выполните команду

         .. code-block:: sh

            ./grafana-cli admin set-config --http_port=<порт для сервера Grafana>

      #. Перезагрузите сервис Grafana

         **Linux**

         .. code-block:: sh

            sudo systemctl start grafana-server

         **MacOS**

         .. code-block:: sh

            brew services restart grafana

      **Docker**

      При использовании Docker возможно поменять порт для Grafana без изменения конфигурации самой Grafana
      Для этого при запуске контейнера укажите флаг -p в виде: -p <новый порт для Grafana>:3000

      .. code-block:: sh

         docker run -d -p <новый порт для Grafana>:3000 --name=grafana \
         -e "GF_INSTALL_PLUGINS=https://github.com/VolkovLabs/custom-plugin.zip;custom-plugin" \
         grafana/grafana-enterprise


#. Перейдите в браузер и откройте https://localhost:<порт grafana (по умолчанию 3000)>/login
#. В форме авторизации введите `admin` в качестве пользователя и `admin` в качестве пароля.

Подключение к платформе по протоколу MQTT
-----------------------------------------
В состав платформы входит брокер сообщений `RabbitMQ <https://www.rabbitmq.com/>`_.
Для связи с Grafana в RabbitMQ установлен плагин MQTT, также плагин MQTT необходимо
установить и в Grafana.

Настройка источника данных в Grafana
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* Для установки плагина MQTT нужно перейти в раздел `Connections` и ввести в поиске mqtt.

.. figure:: ../pics/grafana_setup_plugins_menu.png
    :align: center

    Меню плагинов

.. figure:: ../pics/grafana_setup_search_plugin.png
    :align: center

    Поиск MQTT плагина

* Выбираем появившийся плагин и нажимаем Install.

.. figure:: ../pics/grafana_setup_install_mqtt.png
    :align: center

    Установка плагина

* После установки нажимаем кнопку ``Add new data source``.

.. figure:: ../pics/grafana_setup_plugins_add_new_ds.png
    :align: center

    Создание нового источника данных

* Для настройки нового источника данных нужно указать

   .. figure:: ../pics/grafana_setup_conf_datasource.png
      :align: center

      Настройка источника данных

   * Название источника данных
   * URL адрес для подключения: ``tcp://rabbitmq:1883``
   * Имя пользователя и пароль для авторизации в брокере

Отображение данных из платформы
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Для отображения данных из платформы необходимо:

#. Cоздать новый dashboard и панель.

.. figure:: ../pics/grafana_setup_add_dashboard.png
    :align: center

    Создание нового дэшборда

.. figure:: ../pics/grafana_setup_add_panel.png
    :align: center

    Создание новой панели

#. Настроить источник данных в панели, а именно:
   #. Указать в качестве источника MQTT
   #. Прописать id тега, который необходимо отобразить. По нему данные из платформы через брокер сообщений будут поступать в панель.

      .. note:: В брокере сообщений RabbitMQ, в качестве обменника для получения данных, Grafana MQTT плагин использует `amq.topic`.

.. figure:: ../pics/grafana_setup_conf_panel.png
    :align: center

    Настройка источника данных в панели

После этого данные появятся и будут отображатся в панели.

.. warning:: ВАЖНО! Необходимо отключить автообновление дэшборда, если хотя бы одна панель использует MQTT плагин
   Автообновление нарушает ее работу и сбрасывает все данные, которые она получила до обновления.

   .. figure:: ../pics/grafana_setup_turn_off_refresh.png
       :align: center


Отправка данных из Grafana в платформу
--------------------------------------

Для отправки данных из Grafana необходимо установить плагин формы ручного ввода.

Установка плагина
~~~~~~~~~~~~~~~~~

Linux/MacOS
"""""""""""

.. code-block:: sh

   wget "https://github.com/mp-co-ru/grafana-ui-plugin/mp-co-peresvet-app-1-0-0.zip" -O <директория для плагинов в Grafana>/mp-co-peresvet-app-1-0-0.zip
   unzip <директория для плагинов в Grafana>/mp-co-peresvet-app-1-0-0.zip -d <директория для плагинов в Grafana>/mp-co-peresvet-app-1-0-0
   rm <директория для плагинов в Grafana>/mp-co-peresvet-app-1-0-0.zip

.. note::
   Директория для плагинов в Grafana по умолчанию находится по пути `/usr/local/var/lib/grafana/plugins`.

Docker
""""""

.. code-block:: sh

   docker run -d -p 3000:3000 --name=grafana \
   -e "GF_INSTALL_PLUGINS=https://github.com/mp-co-ru/grafana-ui-plugin/mp-co-peresvet-app-1-0-0.zip;mp-co-peresvet-app" \
   grafana/grafana-enterprise

Для его работы дополнительная настройка Grafana не требуется
Подробнее про запуск, конфигурацию и работу плагина

`Плагин для формы ручного ввода в Grafana <./grafana_plugin.rst>`
