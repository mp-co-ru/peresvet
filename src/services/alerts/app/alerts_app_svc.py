"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``\.
"""
import sys
import copy
import json
import hashlib
from ldap.dn import str2dn, dn2str

sys.path.append(".")

from src.common.app_svc import AppSvc
from src.services.alerts.app.alerts_app_settings import AlertsAppSettings
from src.common.hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE

class AlertsApp(AppSvc):
    """Сервис работы с тревогами.
    """

    def __init__(self, settings: AlertsAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _add_app_handlers(self) -> dict:
        self._handlers[f"{self._config.hierarchy['class']}.app_api.get_alarms"] = self._get_alarms
        self._handlers[f"{self._config.hierarchy['class']}.app_api.ack_alarm"] = self._ack_alarm

    async def _get_alarms(self, mes: dict) -> dict:
        """_summary_

        Args:
            

        Returns:
            dict: _description_
        """
        get_alerts = {
            "base": await self._hierarchy.get_node_id(self._cache._cache_node_dn),
            "scope": CN_SCOPE_ONELEVEL,
            "filter": {
                "cn": ['*.alerts_app']
            },
            "attributes": ["prsJsonConfigString"]
        }
        alerts = await self._hierarchy.search(get_alerts)
        result = {
            "data": []
        }
        for alert in alerts:
            a_data = json.loads(alert[2]["prsJsonConfigString"][0])
            if a_data["fired"]:
                result["data"].append({
                    "alertId": alert[0],
                    "fired": a_data["fired"],
                    "acked": a_data["acked"]
                })

        return result

    async def _ack_alarm(self, mes: dict):
        """_summary_

        Args:
            mes (dict): {
                "action": "alerts.ackAlarms",
                "data": {
                    "id": "alert_id",
                    "x": 123
                }
            }
        """
        alert_id = mes["data"]["id"]
        alert_cache_key = self._cache_key(alert_id, self._config.svc_name)
        alert_data = await self._cache.get(
            name=alert_cache_key
        ).exec()

        if not alert_data:
            self._logger.debug(f"Отсутствует кэш по тревоге {alert_id}.")
            return

        if not alert_data[0]["fired"]:
            self._logger.debug(f"Тревога {alert_id} неактивна.")
            return

        if alert_data[0]["acked"]:
            self._logger.debug(f"Тревога {alert_id} уже квитирована.")
            return

        alert_data[0]["acked"] = mes["data"]["x"]
        await self._cache.set(name=alert_cache_key, obj=alert_data)
        await self._post_message(
            {
                "action": "alerts.alarmAcked",
                "data": {
                    "alertId": alert_id,
                    "x": mes["data"]["x"]
                }
            },
            reply=False,
            routing_key=alert_id
        )

    async def _tag_changed(self, mes: dict) -> None:
        """_summary_

        Args:
            mes (dict): {
                "action": "tags.uploadData",
                "data": {
                    "data": [
                        {
                            "tagId": "...",
                            "data": [
                                (1, 2, 3)
                            ]
                        }
                    ]
                }
            }
        """
        for tag_item in mes["data"]["data"]:
            tag_id = tag_item["tagId"]

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
            for alert in alerts:
                alert_id = alert[0]
                alert_cache_key = self._cache_key(alert_id, self._config.svc_name)
                alert_data = await self._cache.get(
                    alert_cache_key
                ).exec()

                self._logger.debug(f"Alert cache data: {alert_data}")

                if not alert_data[0]:
                    self._logger.error(f"Нет кэша тревоги {alert_id}.")
                    continue

                for data_item in tag_item["data"]:

                    self._logger.debug(f"Data item: {data_item}")

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
                                "action": "alerts.alarmOn",
                                "data": {
                                    "alertId": alert_id,
                                    "x": data_item[1]
                                }
                            },
                            reply=False,
                            routing_key=alert_id
                        )
                        alert_data[0]["fired"] = data_item[1]

                        if alert_data[0]["autoAck"]:
                            await self._post_message(
                                {
                                    "action": "alerts.alarmAcked",
                                    "data": {
                                        "alertId": alert_id,
                                        "x": data_item[1]
                                    }
                                },
                                reply=False,
                                routing_key=alert_id
                            )
                            alert_data[0]["acked"] = data_item[1]


                    if alert_data[0]["fired"] and not alert_on:
                        await self._post_message(
                            {
                                "action": "alerts.alrmOff",
                                "data": {
                                    "alertId": alert_id,
                                    "x": data_item[1]
                                }
                            },
                            reply=False,
                            routing_key=alert_id
                        )
                        alert_data[0]["fired"] = None
                        alert_data[0]["acked"] = None

                await self._cache.set(
                    name=alert_cache_key,
                    obj=alert_data
                ).exec()

    def _cache_key(self, *args):
        '''
        return hashlib.sha3_256(
            f"{'.'.join(args)}".encode()
        ).hexdigest()   # SHA3-256
        '''
        return f"{'.'.join(args)}"
    
    async def _get_alert(self, alert) -> None:
        alert_id = alert[0]
        alert_config = json.loads(alert[2]["prsJsonConfigString"][0])
        tag_id, _ = await self._hierarchy.get_parent(alert_id)

        await self._amqp_consume_queue.bind(
            exchange=self._exchange,
            routing_key=f"tags.app.uploadData.{tag_id}"
        )

        alert_data = {
            "tagId": tag_id,
            "alertId": alert_id,
            "fired": None,
            "acked": None,
            "value": alert_config["value"],
            "high": alert_config["high"],
            "autoAck": alert_config["autoAck"],
            "cn": alert[2]["cn"][0],
            "description": alert[2]["description"][0]
        }

        await self._cache.set(
            name=self._cache_key(alert_id, self._config.svc_name),
            obj=alert_data
        ).exec()

        self._logger.debug(f"Тревога {alert_id} прочитана.")

    async def _get_alerts(self) -> None:
        get_alerts = {
            "filter": {
                "objectClass": ["prsAlert"],
                "prsActive": [True]
            },
            "attributes": ["cn", "description", "prsJsonConfigString"]
        }
        alerts = await self._hierarchy.search(get_alerts)
        for alert in alerts:
            self._get_alert(alert)

    async def on_startup(self) -> None:
        await super().on_startup()

        try:
            await self._get_alerts()
        except Exception as ex:
            self._logger.error(f"Ошибка чтения тревог: {ex}")

settings = AlertsAppSettings()

app = AlertsApp(settings=settings, title="`TagsApp` service")
