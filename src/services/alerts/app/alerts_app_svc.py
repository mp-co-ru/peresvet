"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``.
"""
import sys
import copy
import json
import hashlib
from ldap.dn import str2dn, dn2str

sys.path.append(".")

from src.common import svc
import src.common.times as t
from src.services.alerts.app.alerts_app_settings import AlertsAppSettings
from src.common.cache import Cache
from src.common.hierarchy import CN_SCOPE_ONELEVEL

class AlertsApp(svc.Svc):
    """Сервис работы с тревогами.
    """

    _outgoing_commands = {}

    def __init__(self, settings: AlertsAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)
        self._cache = Cache(settings.ldap_url)

    def _set_incoming_commands(self) -> dict:
        return {
            "alerts.getAlarms": self._get_alarms,
            "alerts.ackAlarms": self._ack_alarms,
            "tags.uploadData": self._tag_changed
        }

    async def _get_alarms(self, mes: dict) -> dict:
        """_summary_

        Args:
            mes (dict): {
                "action": "alerts:getAlarms"
            }

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

    async def _ack_alarms(self, mes: dict):
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
        alert_data = self._cache.get_key(
            key=alert_cache_key,
            json_loads=True
        )

        if not alert_data:
            self._debug(f"Отсутствует кэш по тревоге {alert_id}.")
            return

        if not alert_data["fired"]:
            self._debug(f"Тревога {alert_id} неактивна.")
            return

        if alert_data["acked"]:
            self._debug(f"Тревога {alert_id} уже квитирована.")
            return

        alert_data["acked"] = mes["data"]["x"]
        self._cache.set_key(key=alert_cache_key, value=alert_data)
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
                alert_data = await self._cache.get_key(
                    key=alert_cache_key,
                    json_loads=True
                )

                self._logger.debug(f"Alert cache data: {alert_data}")

                if not alert_data:
                    self._logger.error(f"Нет кэша тревоги {alert_id}.")
                    continue

                for data_item in tag_item["data"]:

                    self._logger.debug(f"Data item: {data_item}")

                    # если данные более ранние, чем уже обработанные...
                    if alert_data["fired"]:
                        if data_item[1] <= alert_data["fired"]:
                            continue
                        if alert_data["acked"] and (data_item[1] <= alert_data["acked"]):
                            continue

                    alert_on = (
                        data_item[0] < alert_data["value"],
                        data_item[0] >= alert_data["value"],
                    )[alert_data["high"]]

                    self._logger.debug(f"Alarm on: {alert_on}")

                    if (alert_data["fired"] and alert_on) or \
                        (not alert_data["fired"] and not alert_on):
                        continue

                    if not alert_data["fired"] and alert_on:
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
                        alert_data["fired"] = data_item[1]

                        if alert_data["autoAck"]:
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
                            alert_data["acked"] = data_item[1]


                    if alert_data["fired"] and not alert_on:
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
                        alert_data["fired"] = None
                        alert_data["acked"] = None

                await self._cache.set_key(
                    key=alert_cache_key,
                    value=alert_data)

    def _cache_key(self, *args):
        '''
        return hashlib.sha3_256(
            f"{'.'.join(args)}".encode()
        ).hexdigest()   # SHA3-256
        '''
        return f"{'.'.join(args)}"

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
            alert_id = alert[0]
            alert_config = json.loads(alert[2]["prsJsonConfigString"][0])
            tag_id = await self._hierarchy.get_node_id(
                dn2str(str2dn(alert[1])[1:])
            )

            await self._amqp_consume["queue"].bind(
                exchange=self._amqp_consume["exchanges"]["main"]["exchange"],
                routing_key=tag_id
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

            await self._cache.set_key(
                self._cache_key(alert_id, self._config.svc_name),
                alert_data
            )

            self._logger.debug(f"Тревога {alert_id} прочитана.")

    async def on_startup(self) -> None:
        await super().on_startup()

        await self._cache.connect()
        try:
            await self._get_alerts()
        except Exception as ex:
            self._logger.error(f"Ошибка чтения тревог: {ex}")

settings = AlertsAppSettings()

app = AlertsApp(settings=settings, title="`TagsApp` service")
