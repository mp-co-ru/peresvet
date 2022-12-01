Администрирование
=================
Создание тэгов
++++++++++++++
Для записи данных необходимо сначала создать тэги.

Формат атрибута `prsStore`:

.. code-block:: json

   {
       "metric": "metric_name",
       "tags": {
           "t1": "v1",
           "t2": "v2"
       }
   }

В случае, если в атрибуте `prsStore` будет отсутствовать ключ `metric` или он будет равен None, то в качестве
имени метрики будет взято имя тэга.

В случае, если имя тэга совпадает с его `id`, тогда к имени метрики будет добавлен
префикс `t_`, а все дефисы между группами символов будут заменены на подчёркивания:

.. code-block:: json

   {
       "metric": "<tag_cn>"
   }

.. code-block:: json

   {
       "metric": "t_82afaa26_f846_103b_86c5_a9af65859d5c"
   }

При записи данных в **VictoriaMetrics** **Пересвет** добавит к этой структуре ключи `value` и `timestamp` (`см. пример
<http://opentsdb.net/docs/build/html/api_http/put.html#example-multiple-data-point-put>`_).


.. toctree::
   :maxdepth: 1
   :caption: Содержание:

   Создание самоподписанных сертификатов<self-signed-certificates>
