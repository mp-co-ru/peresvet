"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``\.
"""
import sys
import json

sys.path.append(".")

from src.common.app_svc import AppSvc
from src.services.alerts.app.alerts_app_settings import AlertsAppSettings
from src.common.hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE

class AlertsApp(AppSvc):
    """Сервис работы с тревогами.
    """

    def __init__(self, settings: AlertsAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _add_app_handlers(self):
        self._handlers[f"{self._config.hierarchy['class']}.app_api.get_alarms"] = self._get_alarms
        self._handlers[f"{self._config.hierarchy['class']}.app_api.ack_alarm"] = self._ack_alarm
        self._handlers["prsTag.app.data_set.*"] = self._tag_value_changed
        
    async def _deleting(self, mes: dict, routing_key: str = None):
        # перед удалением тревоги
        await self._delete_alert_cache(mes['id'])
        await self._unbind_alert(mes['id'])

    async def _bind_alert(self, alert_id: str):
        # только логика привязки
        # проверка активности тревоги производится вызывающим методом
        # привязка к сообщениям prsAlert.model.* выполняется при старте сервиса и здесь не меняется
        tag_id, _ = await self._hierarchy.get_parent(alert_id)
        await self._amqp_consume_queue.bind(self._exchange, f"prsTag.app.data_set.{tag_id }")
    
    async def _unbind_alert(self, alert_id: str):
        # если это последняя активная привязанная к тегу тревога, 
        # то отписываемся от изменений значений тега
        tag_id, _ = await self._hierarchy.get_parent(alert_id)
        payload = {
            "base": tag_id,
            "scope": CN_SCOPE_SUBTREE,
            "filter": {
                "objectClass": ["prsAlerts"]
            },
            "attributes": ["prsActive"]
        }
        res = await self._hierarchy.search(payload)

        unbind = len(res) == 0
        for alert in res:
            if (alert[0] != alert_id) and (alert[2]["prsActive"][0] == 'TRUE'):
                unbind = False
                break
        if unbind:
            await self._amqp_consume_queue.unbind(self._exchange, f"prsTag.app.data_set.{tag_id }")
            self._logger.info(f"{self._config.svc_name} :: Отвязка от изменений тега {tag_id}")

    async def _created(self, mes: dict, routing_key: str = None):
        # тревога создана
        active = await self._make_alert_cache(mes['id'])
        if active:
            await self._bind_alert(mes['id'])

    async def _updated(self, mes: dict, routing_key: str = None):
        # метод, срабатывающий на изменение экземпляра сущности в иерархии
        # сервис <>.app подписан на это событие по умолчанию

        # поступаем так: удаляем кэш
        # читаем данные по тревоге

        #TODO: не учитываем пока возможности переноса тревоги на другого родителя!

        active = await self._make_alert_cache(mes["id"])
        if active:
            await self._bind_alert(mes['id'])
        else:
            await self._unbind_alert(mes['id'])
    
    async def _delete_alert_cache(self, alert_id: str):
        await self._cache.delete(f"{alert_id}.{self._config.svc_name}").exec()

    async def _make_alert_cache(self, alert_id: str) -> bool | None:
        # метод создаёт кэш тревоги и возвращает значение флага prsActive
        # если указанной тревоги нет, то возвращается None
        await self._delete_alert_cache(alert_id=alert_id)

        payload = {
            "id": alert_id,
            "attributes": ['prsActive', 'cn', 'description', 'prsJsonConfigString']
        }
        alert_data = await self._hierarchy.search(payload)
        if not alert_data:
            self._logger.error(f"{self._config.svc_name} :: Нет данных по тревоге {alert_id}.")
            return None
        alert = alert_data[0]

        tag_id, _ = await self._hierarchy.get_parent(alert_id)

        active = alert[2]["prsActive"][0] == 'TRUE'
        if not active:
            self._logger.warning(f"{self._config.svc_name} :: Тревога '{alert_id}' неактивна.")
            return False

        try:
            # json.loads вполне может возвращать целые и вещественные числа,
            # то есть преобразует строку не только в словарь, но и в другие типы
            alert_config = json.loads(alert[2]["prsJsonConfigString"][0])
        except (json.JSONDecodeError, TypeError):
            alert_config = None

        if not isinstance(alert_config, dict):
            self._logger.error(f"{self._config.svc_name} :: У тревоги '{alert_id}' неверная конфигурация.")
            return None
        
        if (alert_config.get("value") is None) or \
           (alert_config.get("high") is None) or \
           (alert_config.get("autoAck") is None):
            self._logger.error(f"{self._config.svc_name} :: У тревоги '{alert_id}' неверная конфигурация.")
            return None

        alert_data = {
            #"tagId": tag_id,
            "alertId": alert_id,
            "fired": False,
            "acked": False,
            "value": alert_config["value"],
            "high": alert_config["high"],
            "autoAck": alert_config["autoAck"],
            "cn": alert[2]["cn"][0],
            "description": alert[2]["description"][0]
        }

        await self._cache.set(
            name=f"{alert_id}.{self._config.svc_name}",
            obj=alert_data
        ).exec()

        # проведём активацию тревоги ---------------
        payload = {
            "tagId": tag_id,
            "actual": True
        }
        res = await self._post_message(
            mes=payload, 
            reply=True, 
            routing_key=f"prsTag.app_api_client.data_get.{tag_id}"
        )
        if not res is None:
            if res.get('data'):
                await self._tag_value_changed(res, id_alert=alert_id)
            else:
                self._logger.warning(f"{self._config.svc_name} :: Тег {tag_id} не имеет данных.")
            return True    
        else:
            self._logger.warning(f"{self._config.svc_name} :: Тег {tag_id} не привязан к хранилищу.")
            return True

    async def _get_alarms(self, mes: dict, routing_key: str = None) -> dict:
        """
        Метод получения алярмов.
        Пока получаем только текущие алярмы - либо активные, либо незаквитированные.
        #TODO: Работа с историей алармов
        
        Args:
            mes (dict): 
                parentId: str | list[str] - Объект, тревоги которого запрашиваем.
                getChildren: bool = False - Учитывать тревоги дочерних объектов.
                format: bool = False - форматировать метки времени.
                fired: bool = True - только активированные/

        Returns:
            dict: _description_
        """
        
        scope = (CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE)[bool(mes.get('getChildren'))]

        get_alerts = {
            "base": mes.get("parentId"),
            "scope": scope,
            "filter": {
                "objectClass": ['prsAlert'],
                "prsActive": [True]
            },
            "attributes": ["cn"]
        }

        alerts = await self._hierarchy.search(get_alerts)
        result = {
            "data": []
        }
        for alert in alerts:
            alarm = await self._cache.get(f"{alert[0]}.{self._config.svc_name}").exec()
            if alarm[0] is None:
                self._logger.error(f"{self._config.svc_name} :: Нет кэша для тревоги {alert[0]}")
                continue

            if mes["fired"] and not alarm["fired"]:
                continue

            res_item = {
                "id": alert[0],
                "cn": alarm[0]["cn"],
                "description": alarm[0]["description"],
                "start": (False, alarm[0]["fired"])[alarm[0]["fired"]],
                "finish": False,
                "acked": (False, alarm[0]["acked"])[alarm[0]["acked"]]
            }

            result["data"].append(res_item)


        return result

    async def _ack_alarm(self, mes: dict, routing_key: str = None):
        """_summary_

        Args:
            mes (dict): {
                "id": "alert_id",
                "x": 123                
            }
        """
        alert_id = mes["id"]
        alert_cache_key = f"{alert_id}.{self._config.svc_name}"
        alert_data = await self._cache.get(name=alert_cache_key).exec()

        if not alert_data[0]:
            self._logger.error(f"{self._config.svc_name} :: Отсутствует кэш по тревоге {alert_id}.")
            return

        if not alert_data[0]["fired"]:
            self._logger.warning(f"{self._config.svc_name} :: Тревога {alert_id} неактивна.")
            return

        if alert_data[0]["acked"]:
            self._logger.warning(f"{self._config.svc_name} :: Тревога {alert_id} уже квитирована.")
            return

        alert_data[0]["acked"] = mes["x"]
        await self._cache.set(name=alert_cache_key, obj=alert_data)
        await self._post_message(
            {
                "alertId": alert_id,
                "x": mes["data"]["x"]                
            },
            reply=False,
            routing_key=f"{self._config.hierarchy['class']}.app.alarm_acked.{alert_id}"
        )

    async def _tag_value_changed(self, mes: dict, routing_key: str = None, id_alert: str = None) -> None:
        """_summary_

        Args:
            mes (dict): {
                "data": [
                    {
                        "tagId": "...",
                        "data": [
                            (1, 2, 3)
                        ]
                    }
                ]                
            }
        """
        for tag_item in mes["data"]:
            tag_id = tag_item["tagId"]

            if id_alert is None:
                get_alerts = {
                    "base": tag_id,
                    "scope": CN_SCOPE_ONELEVEL,
                    "filter": {
                        "objectClass": ["prsAlert"],
                        "prsActive": [True]
                    },
                    "attributes": ["entryUUID"]
                }
                alerts = await self._hierarchy.search(get_alerts)
            else:
                alerts = [(id_alert, None, None)]

            for alert in alerts:
                alert_id = alert[0]
                alert_data = await self._cache.get(
                    f"{alert_id}.{self._config.svc_name}"
                ).exec()

                if not alert_data[0]:
                    self._logger.error(f"{self._config.svc_name} :: Нет кэша тревоги {alert_id}.")
                    continue

                for data_item in tag_item["data"]:

                    # если данные более ранние, чем уже обработанные...
                    if alert_data[0]["fired"]:
                        if data_item[1] <= alert_data[0]["fired"]:
                            continue
                        if alert_data[0]["acked"] and (data_item[1] <= alert_data[0]["acked"]):
                            continue

                    alert_on = (
                        data_item[0] < alert_data[0]["value"],
                        data_item[0] >= alert_data[0]["value"],
                    )[alert_data[0]["high"]]

                    self._logger.debug(f"Alarm on: {alert_on}")

                    if (alert_data[0]["fired"] and alert_on) or \
                        (not alert_data[0]["fired"] and not alert_on):
                        continue

                    if not alert_data[0]["fired"] and alert_on:
                        await self._post_message(
                            {                                
                                "alertId": alert_id,
                                "x": data_item[1]
                            },
                            reply=False,
                            routing_key=f"{self._config.hierarchy['class']}.app.alarm_on.{alert_id}"
                        )
                        alert_data[0]["fired"] = data_item[1]

                        if alert_data[0]["autoAck"]:
                            await self._post_message(
                                {                                    
                                    "alertId": alert_id,
                                    "x": data_item[1]                                    
                                },
                                reply=False,
                                routing_key=f"{self._config.hierarchy['class']}.app.alarm_acked.{alert_id}"
                            )
                            alert_data[0]["acked"] = data_item[1]


                    if alert_data[0]["fired"] and not alert_on:
                        await self._post_message(
                            {
                                "alertId": alert_id,
                                "x": data_item[1]                             
                            },
                            reply=False,
                            routing_key=f"{self._config.hierarchy['class']}.app.alarm_off.{alert_id}"
                        )
                        alert_data[0]["fired"] = None
                        alert_data[0]["acked"] = None

                await self._cache.set(
                    name=f"{alert_id}.{self._config.svc_name}",
                    obj=alert_data[0]
                ).exec()

    async def _get_alerts(self, routing_key: str = None) -> None:
        get_alerts = {
            "filter": {
                "objectClass": ["prsAlert"],
                "prsActive": [True]
            },
            "attributes": ["cn", "description", "prsJsonConfigString"]
        }
        alerts = await self._hierarchy.search(get_alerts)
        for alert in alerts:
            await self._make_alert_cache(alert[0])
            await self._bind_alert(alert[0])

    async def on_startup(self) -> None:
        await super().on_startup()

        # по умолчанию очередь привязывается к изменениям всех тегов
        # нам же нужны только изменения тегов, у которых есть тревоги
        await self._amqp_consume_queue.unbind(self._exchange, "prsTag.app.data_set.*")
        
        try:
            await self._get_alerts()
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: {ex}")

settings = AlertsAppSettings()

app = AlertsApp(settings=settings, title="`TagsApp` service")
