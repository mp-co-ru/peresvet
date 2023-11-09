Интеграция с Grafana
==================================================

.. note:: 
   Для дальнейшей работы необходимо иметь Linux (Ubuntu/Debian) в качестве ОС и установить Docker и git.

Для связи между Grafana и платформой Пересвет необходимо произвести несколько настроек

#. Запускаем все необходимые сервисы платформы Пересвет в Docker.
   
   Для этого необходимо:
   
   #. Скачать проект с помощью команды `git clone https://github.com/mp-co-ru/mpc-peresvet.git`
   #. Открыть любой терминал и перейти в корневую директорию проекта `cd <путь до директории проекта>/mpc-peresvet` 
   #. Выполнить команду `./run.sh`.

      .. warning::
         Для того, чтобы процедура запуска сервисов прошла успешно, в системе должнен быть установлен Docker. 

#. Запустить Grafana

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

   #. Запускаем контейнер с помощью команды
   
      .. code-block:: sh

         docker run -d -p 3000:3000 --name=grafana \
         -e "GF_INSTALL_PLUGINS=https://github.com/VolkovLabs/custom-plugin.zip;custom-plugin" \
         grafana/grafana-enterprise 

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

Настройка источника данных в Grafana
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Для получения метрик из платформы необходимо воспользоваться плагином для Grafana,
который позволяет подключаться к брокеру сообщений по протоколу MQTT

* Для установки плагина нужно перейти в раздел `plugins` и ввести в поиске mqtt.

.. figure:: ../pics/grafana_setup_plugins_menu.png
    :align: center

    Меню плагинов

.. figure:: ../pics/grafana_setup_search_plugin.png
    :align: center

    Посик MQTT плагина

* Выбираем появившийся плагин и нажимаем Install.

.. figure:: ../pics/grafana_setup_install_mqtt.png
    :align: center

    Установка плагина

* После установки выбираем появившийся вариант Create a MQTT Datasource.

.. figure:: ../pics/grafana_setup_plugins_menu.png
    :align: center

    Создание нового источника данных

* Для настройки нового источника данных нужно указать

   .. figure:: ../pics/grafana_setup_conf_datasource.png
      :align: center

      Настройка источника данных

   * Название источника данных
   * URL адрес для подключения к брокеру сообщений, например tcp://localhost:1883
   * Имя пользователя для авторизации в брокере
   * Пароль для авторизации в брокере

   .. warning::
      ВАЖНО! При настройке источника данных, для брокера сообщений
      должен быть открыт порт `1883` и установлен плагин для работы с протоколом mqtt
      Для RabbitMQ это плагин `rabbitmq-mqtt`

   .. note::
      Для установки плагина `rabbit-mqtt` нужно зайти в контейнер RabbitMQ выполнив в любом терминале
      команду `docker exec -it <id контейнера> bash` и далее выполнив команду `rabbitmq-plugins enable rabbitmq_mqtt`
      внутри контейнера

Отображение данных из платформы
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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
   #. Прописать необходимый topic по которому из брочека сообщений панель будет получать данный из платформы.

      .. note:: В качестве обменника для получения данный Grafana MQTT плагин использует `amq.topic`.

.. figure:: ../pics/grafana_setup_conf_panel.png
    :align: center

    Настройка источника данных в панели

После этого данные появятся и будут отображатся в панели.

.. warning:: ВАЖНО! Необходимо отключить автообновление дэшборда, если хотя бы одна панель использует MQTT плагин
   Автообновление нарушает ее работу и сбрасывает все данные, еоторые она получила до обновления.

Отправка данных из Grafana в платформу
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Для отправки данных из Grafana необходимо установить плагин формы ручного ввода.

Установка плагина
~~~~~~~~~~~~~~~~~

**Linux/MacOS**

.. code-block:: sh

   wget "https://github.com/mp-co-ru/grafana-ui-plugin/mp-co-peresvet-app-1-0-0.zip" -O <директория для плагинов в Grafana>/mp-co-peresvet-app-1-0-0.zip
   unzip <директория для плагинов в Grafana>/mp-co-peresvet-app-1-0-0.zip -d <директория для плагинов в Grafana>/mp-co-peresvet-app-1-0-0 
   rm <директория для плагинов в Grafana>/mp-co-peresvet-app-1-0-0.zip

.. note::
   Директория для плагинов в Grafana по умолчанию находится по пути `/usr/local/var/lib/grafana/plugins`.

**Docker**

.. code-block:: sh

   docker run -d -p 3000:3000 --name=grafana \
   -e "GF_INSTALL_PLUGINS=https://github.com/mp-co-ru/grafana-ui-plugin/mp-co-peresvet-app-1-0-0.zip;mp-co-peresvet-app" \
   grafana/grafana-enterprise

Для его работы дополнительная настройка Grafana не требуется
Подробнее про запуск, конфигурацию и работу плагина

`Плагин для формы ручного ввода в Grafana <./grafana_plugin.rst>`
