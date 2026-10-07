import sys
import json
import asyncio
import base64
import os
import re
from collections import deque
from collections.abc import Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import APIRouter
import aio_pika
import aio_pika.abc
sys.path.append(".")

from src.services.connectors.app.connectors_mqtt_app_settings import ConnectorsMQTTAppSettings
from src.common.app_svc import AppSvc
from src.common import hierarchy
from src.common import runtime_flags
from src.common.tag_quality_codes import (
    CN_QUALITY_CONNECTION_LOST,
    CN_QUALITY_CONNECTION_RESTORED,
)
from src.services.video.camera import config_is_camera, is_camera_connector
import src.common.times as t

_CONNECTOR_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
# RabbitMQ 4 отдаёт client_properties MQTT-сессии строкой терма:
# {client_id,longstr,<<"uuid">>}, а не таблицей.
_CLIENT_ID_IN_PROPERTIES_RE = re.compile(
    r"client_id.*?([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
    re.IGNORECASE | re.DOTALL,
)


def _amqp_scalar_to_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, (list, tuple)):
        return " ".join(_amqp_scalar_to_str(item) for item in value)
    return str(value)


def _amqp_table_to_dict(value) -> dict:
    if not isinstance(value, dict):
        return {}
    out = {}
    for key, item in value.items():
        name = key.decode("utf-8", "replace") if isinstance(key, bytes) else str(key)
        if isinstance(item, dict):
            out[name] = _amqp_table_to_dict(item)
        elif isinstance(item, bytes):
            out[name] = item.decode("utf-8", "replace")
        else:
            out[name] = item
    return out


def _as_connector_uuid(value) -> str | None:
    text = _amqp_scalar_to_str(value).strip()
    if _CONNECTOR_UUID_RE.fullmatch(text):
        return text.lower()
    return None


def _is_mqtt_broker_connection(headers: dict) -> bool:
    return "mqtt" in _amqp_scalar_to_str(headers.get("protocol")).lower()


def broker_connection_identity(headers: dict | None) -> str:
    headers = _amqp_table_to_dict(headers or {})
    pid = _amqp_scalar_to_str(headers.get("pid"))
    name = _amqp_scalar_to_str(headers.get("name"))
    return f"{pid}|{name}"


def _client_id_from_properties_term(props) -> str | None:
    """UUID из client_properties, когда брокер прислал терм строкой, а не таблицей."""
    if isinstance(props, dict):
        chunks = [str(key) + str(value) for key, value in props.items()]
    elif isinstance(props, (list, tuple)):
        chunks = [_amqp_scalar_to_str(item) for item in props]
    else:
        chunks = [_amqp_scalar_to_str(props)]
    for chunk in chunks:
        match = _CLIENT_ID_IN_PROPERTIES_RE.search(chunk)
        if match:
            return match.group(1).lower()
    return None


def connector_id_from_broker_connection_headers(headers: dict | None) -> str | None:
    """Id коннектора из события RabbitMQ ``connection.*`` (MQTT client_id = UUID)."""
    headers = _amqp_table_to_dict(headers or {})
    if not _is_mqtt_broker_connection(headers):
        return None
    props = headers.get("client_properties")
    if not isinstance(props, dict):
        props = {}
    for candidate in (
        props.get("client_id"),
        props.get("clientId"),
        props.get("user_provided_name"),
        headers.get("client_id"),
        headers.get("user"),
    ):
        conn_id = _as_connector_uuid(candidate)
        if conn_id:
            return conn_id
    return _client_id_from_properties_term(headers.get("client_properties"))


def connector_id_from_management_connection(connection: dict | None) -> str | None:
    """Id коннектора из элемента ``GET /api/connections`` (MQTT client_id = UUID)."""
    if not isinstance(connection, dict):
        return None
    props = connection.get("client_properties")
    headers = {
        "protocol": connection.get("protocol"),
        "client_properties": props if isinstance(props, dict) else {},
        "client_id": connection.get("client_id"),
        "user": connection.get("user"),
    }
    return connector_id_from_broker_connection_headers(headers)


def live_mqtt_connector_ids_from_management_connections(connections) -> list[str]:
    """UUID коннекторов с живой MQTT-сессией на брокере."""
    ids: list[str] = []
    seen: set[str] = set()
    if not isinstance(connections, list):
        return ids
    for item in connections:
        conn_id = connector_id_from_management_connection(item)
        if conn_id and conn_id not in seen:
            seen.add(conn_id)
            ids.append(conn_id)
    return ids


class ConnectorsMQTTApp(AppSvc):
    """Сервис работы с коннекторами.

    Подписывается на очередь ``connectors_tags_api`` обменника ``connectors_api_crud``,
    в которую публикует сообщения сервис ``connectors_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: ConnectorsMQTTAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)
        self._connected_connectors: set[str] = set()
        # камеры, чья MQTT-сессия — признак связи видеосервера, без кодов 100/101
        self._camera_presence_ids: set[str] = set()
        # поколение сессии: LWT увеличивает, in-flight getConfig сверяет после RPC 101
        self._connector_session_epoch: dict[str, int] = {}
        # id тегов, привязанных к коннектору (без LDAP при записи качества в историю через AMQP)
        self._connector_tag_ids: dict[str, set[str]] = {}
        # MQTT-сессия на брокере: connector_id → identity (pid|name) из connection.created
        self._mqtt_broker_conn_by_connector: dict[str, str] = {}
        self._broker_events_channel = None
        # ожидание ответа TagsApp при записи 101 до full_configuration
        self._quality_write_ack_timeout_sec: float = 60.0
        # последние строки лога с коннектора (prsConnector.log_line по MQTT) для UI конфигуратора
        self._connector_log_buffer_max: int = 400
        self._connector_log_lines: dict[str, deque[dict]] = {}
        # вывод удалённых команд (prsConnector.command_output), отдельно от log_line
        self._connector_command_output_buffer_max: int = 200
        self._connector_command_output_lines: dict[str, deque[dict]] = {}

    def append_connector_log_line(
        self, conn_id: str, *, level: str, message: str, ts: int | None = None
    ) -> None:
        if ts is None:
            ts = int(t.now_int())
        buf = self._connector_log_lines.setdefault(
            conn_id, deque(maxlen=self._connector_log_buffer_max)
        )
        text = (message or "")[:8192]
        buf.append({"ts": ts, "level": level, "message": text})

    def append_connector_command_output(self, conn_id: str, entry: dict) -> None:
        buf = self._connector_command_output_lines.setdefault(
            conn_id, deque(maxlen=self._connector_command_output_buffer_max)
        )
        buf.append(entry)

    def _replace_connector_tag_cache(self, conn_id: str, tag_ids: Iterable[str]) -> None:
        self._connector_tag_ids[conn_id] = set(tag_ids)

    def _add_connector_tags(self, conn_id: str, tag_ids: Iterable[str]) -> None:
        self._connector_tag_ids.setdefault(conn_id, set()).update(tag_ids)

    def _remove_connector_tags(self, conn_id: str, tag_ids: Iterable[str]) -> None:
        s = self._connector_tag_ids.get(conn_id)
        if not s:
            return
        for t in tag_ids:
            s.discard(t)
        if not s:
            self._connector_tag_ids.pop(conn_id, None)

    def _invalidate_connector_session(self, conn_id: str) -> None:
        self._connected_connectors.discard(conn_id)
        self._connector_session_epoch[conn_id] = self._connector_session_epoch.get(conn_id, 0) + 1

    def _connector_session_is_current(self, conn_id: str, epoch: int) -> bool:
        return self._connector_session_epoch.get(conn_id, 0) == epoch

    def _add_app_handlers(self):
        self._handlers["conn2prs.*"] = self._send_config_to_connector
        self._handlers["prsConnector.connection_lost.*"] = self._connection_lost
        self._handlers[f"{self._config.hierarchy['class']}.model.tag_updated.*"] = self._tags_updated
        self._handlers[f"{self._config.hierarchy['class']}.model.tag_deleted.*"] = self._tag_deleted
        self._handlers[f"{self._config.hierarchy['class']}.model.tag_link_updated.*"] = self._tags_updated
        self._handlers[f"{self._config.hierarchy['class']}.model.unlink_tag.*"] = self._tags_unlinked
        self._handlers[f"{self._config.hierarchy['class']}.model.link_tag.*"] = self._tag_linked
        self._handlers[f"{self._config.hierarchy['class']}.app_api.command.*"] = self._send_command

    async def _is_camera(self, conn_id: str) -> bool:
        try:
            res = await self._get_connector_data(conn_id)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            return False
        if not res:
            return False
        return is_camera_connector(res.get("prsEntityTypeCode")) or config_is_camera(
            res.get("prsJsonConfigString")
        )

    async def _tag_linked(self, mes: dict, routing_key: str | None = None):
        conn_id = mes["connectorId"]
        if await self._is_camera(conn_id):
            return {}
        tags = mes["tagId"]
        if isinstance(tags, str):
            tags = [tags]

        tags_data = {}
        for tag_id in tags:
            tags_data[tag_id] = await self._get_tag_data(conn_id=conn_id, tag_id=tag_id)

        mes2conn = {
            "action": "prsConnector.tags_configuration",
            "data": {
                "tags": tags_data
            }
        }
        await self._post_message(mes=mes2conn, routing_key=f"prs2conn.{conn_id}")
        self._add_connector_tags(conn_id, tags)
        self._logger.info(f"{self._config.svc_name} :: Коннектору {conn_id} послано сообщение о привязке тега {tags}.")

    async def _send_command(self, mes: dict, routing_key: str | None = None):
        conn_id = mes["id"]
        if await self._is_camera(conn_id):
            return {}
        mes2conn = {
            "action": "prsConnector.command",
            "data": mes
        }
        conn_id = mes["id"]
        await self._post_message(mes=mes2conn, routing_key=f"prs2conn.{conn_id}")
        cmd = mes.get("command") or {}
        self._logger.info(
            f"{self._config.svc_name} :: Коннектору {conn_id} посланы команды: {cmd.get('lines', [])}."
        )

    async def _find_connector_by_tag(self, tag_id: str) -> list[str]:
        if not self._config.nodes: # type: ignore
            payload = {
                "base": "cn=connectors,cn=prs",
                "scope": hierarchy.CN_SCOPE_ONELEVEL,
                "filter": {"objectClass": ["prsConnector"]}
            }
            res = await self._hierarchy.search(payload)
            connectors = [res_item[0] for res_item in res]
        else:
            connectors = self._config.nodes # type: ignore

        if not connectors:
            return []

        result = []
        for conn_id in connectors:
            payload = {"base": conn_id, "filter": {"cn": [tag_id]}}
            res = await self._hierarchy.search(payload)
            if res:
                result.append(conn_id)
        return result

    async def _tags_updated(self, mes: dict, routing_key: str | None = None):
        # TODO: по правильному, чтобы получить данные по какой-либо сущности,
        # необходимо делать запрос соответствующему сервису,
        # но, так как система сообщений ещё не устоялась,
        # будем искать данные сразу в иерархии

        # сервис prsConnector.model сам ищет привязки тега к коннекторам
        # и для каждого посылает сообщение, поэтому здесь не ищем список привязки тега

        tags = mes["tagId"]
        if isinstance(tags, str):
            tags = [tags]
        conn_id = mes["connectorId"]
        if await self._is_camera(conn_id):
            return {}

        tags_data = {}
        for tag_id in tags:
            tags_data[tag_id] = await self._get_tag_data(conn_id=conn_id, tag_id=tag_id)

        mes2conn = {
            "action": "prsConnector.tags_configuration",
            "data": {
                "tags": tags_data
            }
        }

        await self._post_message(mes=mes2conn, routing_key=f"prs2conn.{conn_id}")
        self._add_connector_tags(conn_id, tags)

        self._logger.info(f"{self._config.svc_name} :: Сообщение об обновлении тега {tags} отправлено коннектору {conn_id}.")

    async def _tags_unlinked(self, mes: dict, routing_key: str | None = None):
        tags = mes["tagId"]
        if isinstance(tags, str):
            tags = [tags]
        conn_id = mes["connectorId"]
        if await self._is_camera(conn_id):
            return {}
        mes2conn = {
            "action": "prsConnector.tags_deleted",
            "data": {"tags": tags}
        }

        await self._post_message(mes=mes2conn, routing_key=f"prs2conn.{conn_id}")
        self._remove_connector_tags(conn_id, tags)
        self._logger.info(f"{self._config.svc_name} :: Сообщение об отвязке тега {tags} отправлено коннектору {conn_id}.")

    async def _tag_deleted(self, mes: dict, routing_key: str | None = None):
        # сервис prsConnector.model сам ищет привязки тега к коннекторам
        # и для каждого посылает сообщение, поэтому здесь не ищем список привязки тега

        tag_id = mes["tagId"]
        conn_id = mes["connectorId"]
        if await self._is_camera(conn_id):
            return {}
        mes2conn = {
            "action": "prsConnector.tags_deleted",
            "data": {"tags": [tag_id]}
        }

        await self._post_message(mes=mes2conn, routing_key=f"prs2conn.{conn_id}")
        self._remove_connector_tags(conn_id, [tag_id])
        self._logger.info(f"{self._config.svc_name} :: Сообщение об удалении тега {tag_id} отправлено коннектору {conn_id}.")

    async def _get_tag_data(self, conn_id: str, tag_id: str) -> dict | None:
        # метод возвращает данные по тегу, привязанному к коннектору
        payload = {
            "base": conn_id,
            "filter": {
                "cn": [tag_id]
            },
            "attributes": ["prsJsonConfigString"]
        }
        link_res = await self._hierarchy.search(payload=payload)
        if not link_res:
            self._logger.error(f"{self._config.svc_name} :: В списке привязанных к коннектору {conn_id} не найден тег {tag_id}.")
            return None

        payload = {
            "id": tag_id,
            "attributes": ["prsValueTypeCode", "prsActive"]
        }
        tag_res = await self._hierarchy.search(payload=payload)
        if not tag_res:
            self._logger.error(f"{self._config.svc_name} :: К коннектору {conn_id} привязан несуществующий тег {tag_id}.")
            return None

        return {
            "prsActive": tag_res[0][2]["prsActive"][0] == 'TRUE',
            "prsValueTypeCode": int(tag_res[0][2]["prsValueTypeCode"][0]),
            "prsJsonConfigString": json.loads(link_res[0][2]["prsJsonConfigString"][0])
        }

    async def _get_connector_data(self, conn_id: str) -> dict:
        payload = {
            "id": conn_id,
            "attributes": ["prsActive", "prsEntityTypeCode", "prsJsonConfigString"]
        }
        res = await self._hierarchy.search(payload=payload)
        if not res:
            return {}
        return {
            "prsActive": res[0][2]["prsActive"][0] == 'TRUE',
            "prsEntityTypeCode": res[0][2]["prsEntityTypeCode"][0],
            "prsJsonConfigString": json.loads(
                res[0][2]["prsJsonConfigString"][0]
            )
        }

    async def _get_connector_tag_ids(self, conn_id: str) -> list[str]:
        tags = await self._hierarchy.search(payload={
            "base": conn_id,
            "scope": hierarchy.CN_SCOPE_SUBTREE,
            "filter": {
                "objectClass": ["prsConnectorTagData"]
            },
            "attributes": ["cn"]
        })
        return [attrs["cn"][0] for _, _, attrs in tags]

    async def _write_connector_tags_quality(
        self,
        conn_id: str,
        quality_code: int,
        *,
        wait_ack: bool = False,
        tag_ids: Iterable[str] | None = None,
    ) -> bool:
        """Публикует null с кодом качества в шину для записи в историю тегов (БД), без LDAP.

        Список тегов берётся из кэша привязок, если ``tag_ids`` не задан явно
        (кэш обновляется при полной конфигурации и событиях модели).

        Args:
            wait_ack: если True, ждать ответ TagsApp (тот же RPC, что и у data_set),
                а не только публикацию в брокер. Нужно для 101 до ``full_configuration``.
            tag_ids: явный список тегов; иначе кэш коннектора.

        Returns:
            True, если нечего писать, либо публикация (и при wait_ack — запись) удалась;
            False, если публикация или подтверждение не удались.
        """
        ids = list(tag_ids) if tag_ids is not None else list(self._connector_tag_ids.get(conn_id, ()))
        if not ids:
            return True
        now_ts = t.now_int()
        data = {
            "data": [
                {"tagId": tag_id, "data": [[now_ts, None, quality_code]]}
                for tag_id in ids
            ]
        }
        try:
            send = self._post_message(
                mes=data, routing_key="prsTag.app_api.data_set.*", reply=wait_ack
            )
            if wait_ack:
                res = await asyncio.wait_for(
                    send, timeout=self._quality_write_ack_timeout_sec
                )
            else:
                res = await send
        except TimeoutError:
            self._logger.warning(
                f"{self._config.svc_name} :: Таймаут записи качества {quality_code} "
                f"для тегов коннектора {conn_id} ({self._quality_write_ack_timeout_sec} с)."
            )
            return False
        except Exception as ex:
            self._logger.warning(
                f"{self._config.svc_name} :: Не удалось записать качество {quality_code} "
                f"в историю тегов коннектора {conn_id}: {ex}."
            )
            return False
        if not wait_ack:
            return bool(res)
        if res is None:
            self._logger.warning(
                f"{self._config.svc_name} :: Нет обработчика записи качества {quality_code} "
                f"для тегов коннектора {conn_id}."
            )
            return False
        if isinstance(res, dict) and res.get("error"):
            self._logger.warning(
                f"{self._config.svc_name} :: TagsApp вернул ошибку при записи качества "
                f"{quality_code} для коннектора {conn_id}: {res.get('error')}."
            )
            return False
        return True

    async def _load_connector_tag_ids_for_quality(self, conn_id: str) -> list[str] | None:
        tag_ids = list(self._connector_tag_ids.get(conn_id, ()))
        if tag_ids:
            return tag_ids
        try:
            tag_ids = await self._get_connector_tag_ids(conn_id)
        except Exception as ex:
            self._logger.warning(
                f"{self._config.svc_name} :: Не удалось получить список тегов коннектора "
                f"{conn_id} для записи кода качества: {ex}."
            )
            return None
        self._replace_connector_tag_cache(conn_id, tag_ids)
        return tag_ids

    async def _persist_connection_restored(self, conn_id: str) -> bool:
        """Пишет null/101 во все теги коннектора и ждёт подтверждения TagsApp.

        Список тегов — из кэша привязок; если кэш пуст (рестарт сервиса), один LDAP
        только идентификаторов, без полной конфигурации тегов.
        """
        tag_ids = await self._load_connector_tag_ids_for_quality(conn_id)
        if tag_ids is None:
            return False
        wrote = await self._write_connector_tags_quality(
            conn_id,
            CN_QUALITY_CONNECTION_RESTORED,
            wait_ack=True,
            tag_ids=tag_ids,
        )
        if wrote:
            self._logger.info(
                f"{self._config.svc_name} :: Связь с коннектором {conn_id} восстановлена, "
                f"в историю тегов отправлено качество {CN_QUALITY_CONNECTION_RESTORED}."
            )
        else:
            self._logger.warning(
                f"{self._config.svc_name} :: Связь с коннектором {conn_id}: "
                f"запись качества {CN_QUALITY_CONNECTION_RESTORED} не удалась, "
                f"полная конфигурация не отправляется."
            )
        return wrote

    async def _connection_lost(self, mes: dict, routing_key: str | None = None) -> dict:
        """Обработка потери связи с коннектором по MQTT (в т.ч. LWT): публикация null с кодом качества в шину
        для записи в историю тегов (БД), без LDAP. Ожидается mes[\"id\"] или routing_key вида
        prsConnector.connection_lost.<conn_id>."""
        conn_id = mes.get("id")
        if not conn_id and routing_key and routing_key.startswith("prsConnector.connection_lost."):
            conn_id = routing_key.split(".", 2)[-1]
        if not conn_id:
            self._logger.warning(f"{self._config.svc_name} :: prsConnector.connection_lost без id.")
            return {}
        self._invalidate_connector_session(conn_id)
        self._mqtt_broker_conn_by_connector.pop(conn_id, None)
        if runtime_flags.platform_shutting_down:
            self._logger.debug(
                f"{self._config.svc_name} :: prsConnector.connection_lost для {conn_id} "
                f"игнорируется: остановка платформы (запись качества {CN_QUALITY_CONNECTION_LOST} не выполняется)."
            )
            return {}
        tag_ids = await self._load_connector_tag_ids_for_quality(conn_id)
        if tag_ids is None:
            self._logger.warning(
                f"{self._config.svc_name} :: Потеря связи с коннектором {conn_id}; "
                f"список тегов недоступен, качество {CN_QUALITY_CONNECTION_LOST} не записано."
            )
            return {}
        wrote = await self._write_connector_tags_quality(
            conn_id, CN_QUALITY_CONNECTION_LOST, tag_ids=tag_ids
        )
        if wrote:
            self._logger.info(
                f"{self._config.svc_name} :: Зафиксирована потеря связи с коннектором {conn_id}, "
                f"в историю тегов отправлено качество {CN_QUALITY_CONNECTION_LOST}."
            )
        else:
            self._logger.warning(
                f"{self._config.svc_name} :: Потеря связи с коннектором {conn_id}; "
                f"не удалось отправить качество {CN_QUALITY_CONNECTION_LOST} в шину (брокер недоступен?)."
            )
        return {}

    async def _send_config_to_connector(self, mes: dict, routing_key: str | None = None) -> dict:
        if mes.get("action") == "prsConnector.log_line":
            data = mes.get("data") or {}
            conn_id = data.get("id", "?")
            text = data.get("message", "")
            level_name = str(data.get("level") or "INFO").upper()
            if level_name not in ("TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"):
                level_name = "INFO"
            self._logger.log(level_name, f"{conn_id} :: {text}")
            if isinstance(conn_id, str) and len(conn_id) == 36:
                ts_raw = data.get("ts")
                try:
                    ts_int = int(ts_raw) if ts_raw is not None else None
                except (TypeError, ValueError):
                    ts_int = None
                self.append_connector_log_line(
                    conn_id, level=level_name, message=text, ts=ts_int
                )
            return {}

        if mes.get("action") == "prsConnector.command_output":
            data = mes.get("data") or {}
            conn_id = data.get("id", "?")
            if isinstance(conn_id, str) and len(conn_id) == 36:
                ts_raw = data.get("ts")
                try:
                    ts_int = int(ts_raw) if ts_raw is not None else int(t.now_int())
                except (TypeError, ValueError):
                    ts_int = int(t.now_int())
                exit_raw = data.get("exitCode")
                exit_code: int | None
                if exit_raw is None:
                    exit_code = None
                else:
                    try:
                        exit_code = int(exit_raw)
                    except (TypeError, ValueError):
                        exit_code = None
                err_msg = data.get("errorMessage")
                if err_msg is not None and not isinstance(err_msg, str):
                    err_msg = str(err_msg)
                entry = {
                    "ts": ts_int,
                    "command": (data.get("command") or "")[:2048],
                    "status": (data.get("status") or "")[:32],
                    "exitCode": exit_code,
                    "stdout": (data.get("stdout") or "")[:65536],
                    "stderr": (data.get("stderr") or "")[:65536],
                    "errorMessage": (err_msg[:8192] if err_msg else None),
                }
                self.append_connector_command_output(conn_id, entry)
            self._logger.info(
                "%s :: command_output %s status=%s",
                conn_id,
                (data.get("command") or "")[:120],
                data.get("status"),
            )
            return {}

        conn_id = mes["data"]["id"]
        res = await self._get_connector_data(conn_id=conn_id)
        if not res:
            self._logger.error(f"{self._config.svc_name} :: Отсутствует коннектор {conn_id}.")
            return {}
        if is_camera_connector(res.get("prsEntityTypeCode")) or config_is_camera(
            res.get("prsJsonConfigString")
        ):
            return {}

        session_epoch = self._connector_session_epoch.get(conn_id, 0)
        need_restore = conn_id not in self._connected_connectors
        tag_ids_before_config = set(self._connector_tag_ids.get(conn_id, ()))
        if need_restore:
            if not await self._persist_connection_restored(conn_id):
                return {}
            if not self._connector_session_is_current(conn_id, session_epoch):
                self._logger.warning(
                    f"{self._config.svc_name} :: Коннектор {conn_id}: потеря связи во время "
                    f"записи качества {CN_QUALITY_CONNECTION_RESTORED}, "
                    f"полная конфигурация не отправляется."
                )
                return {}
            tag_ids_before_config = set(self._connector_tag_ids.get(conn_id, ()))

        res["tags"] = {}
        mes_for_connector = {
            "action": "prsConnector.full_configuration",
            "data": res
        }

        tags = await self._hierarchy.search(payload={
            "base": conn_id,
            "scope": hierarchy.CN_SCOPE_SUBTREE,
            "filter": {
                "objectClass": ["prsConnectorTagData"]
            },
            "attributes": [
                "cn", "prsJsonConfigString"
            ]
        })

        for _, _, attrs in tags:
            tag_id = attrs["cn"][0]
            mes_for_connector["data"]["tags"][tag_id] = await self._get_tag_data(conn_id=conn_id, tag_id=tag_id)

        self._replace_connector_tag_cache(conn_id, mes_for_connector["data"]["tags"].keys())

        extra_tag_ids = set(mes_for_connector["data"]["tags"].keys()) - tag_ids_before_config
        if need_restore and extra_tag_ids:
            extra_ok = await self._write_connector_tags_quality(
                conn_id,
                CN_QUALITY_CONNECTION_RESTORED,
                wait_ack=True,
                tag_ids=extra_tag_ids,
            )
            if not extra_ok:
                self._logger.warning(
                    f"{self._config.svc_name} :: Коннектор {conn_id}: не удалось записать "
                    f"качество {CN_QUALITY_CONNECTION_RESTORED} для тегов, отсутствовавших "
                    f"в кэше до полной конфигурации; full_configuration не отправляется."
                )
                return {}

        if not self._connector_session_is_current(conn_id, session_epoch):
            self._logger.warning(
                f"{self._config.svc_name} :: Коннектор {conn_id}: потеря связи до отправки "
                f"полной конфигурации, сообщение full_configuration не публикуется."
            )
            return {}

        if need_restore:
            self._connected_connectors.add(conn_id)

        await self._post_message(mes=mes_for_connector, routing_key=f"prs2conn.{conn_id}")

        self._logger.info(f"{self._config.svc_name} :: Отправлена полная конфигурация коннектору {conn_id}.")
        return {}

    async def _broker_session_is_camera(self, conn_id: str) -> bool:
        """Камера держит MQTT только как признак связи, без кодов качества."""
        known = getattr(self, "_camera_presence_ids", None)
        if known is not None and conn_id in known:
            return True
        checker = getattr(self, "_is_camera", None)
        if checker is None:
            return False
        try:
            is_camera = bool(await checker(conn_id))
        except Exception as ex:
            self._logger.warning(
                f"{self._config.svc_name} :: Не удалось проверить, камера ли коннектор {conn_id}: {ex}."
            )
            return False
        if is_camera and known is not None:
            known.add(conn_id)
        return is_camera

    async def _on_broker_connection_event(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        async with message.process(ignore_processed=True):
            try:
                headers = _amqp_table_to_dict(dict(message.headers or {}))
                routing_key = message.routing_key or ""
                conn_id = connector_id_from_broker_connection_headers(headers)
                if not conn_id:
                    return
                identity = broker_connection_identity(headers)
                if routing_key == "connection.created":
                    self._mqtt_broker_conn_by_connector[conn_id] = identity
                    if await self._broker_session_is_camera(conn_id):
                        self._connected_connectors.add(conn_id)
                        self._logger.info(
                            f"{self._config.svc_name} :: Камера {conn_id} на связи "
                            f"(MQTT-сессия {identity})."
                        )
                    else:
                        self._logger.debug(
                            f"{self._config.svc_name} :: MQTT-сессия коннектора {conn_id} на брокере: {identity}."
                        )
                    return
                if routing_key != "connection.closed":
                    return
                current = self._mqtt_broker_conn_by_connector.get(conn_id)
                if current is not None and current != identity:
                    self._logger.debug(
                        f"{self._config.svc_name} :: Игнорировано устаревшее connection.closed "
                        f"коннектора {conn_id} ({identity}, актуальна {current})."
                    )
                    return
                if await self._broker_session_is_camera(conn_id):
                    known = getattr(self, "_camera_presence_ids", None)
                    if known is not None:
                        known.discard(conn_id)
                    self._connected_connectors.discard(conn_id)
                    self._mqtt_broker_conn_by_connector.pop(conn_id, None)
                    self._logger.info(
                        f"{self._config.svc_name} :: Камера {conn_id} без связи: MQTT-сессия закрыта."
                    )
                    return
                self._logger.info(
                    f"{self._config.svc_name} :: Брокер закрыл MQTT-сессию коннектора {conn_id}."
                )
                await self._connection_lost({"id": conn_id})
            except Exception as ex:
                self._logger.warning(
                    f"{self._config.svc_name} :: Ошибка обработки события брокера "
                    f"{message.routing_key}: {ex}."
                )

    async def _subscribe_broker_connection_events(self) -> None:
        self._broker_events_channel = await self._amqp_connection.channel()
        await self._broker_events_channel.set_qos(1)
        queue = await self._broker_events_channel.declare_queue(
            exclusive=True, durable=False, auto_delete=True
        )
        event_exchange = await self._broker_events_channel.declare_exchange(
            "amq.rabbitmq.event", aio_pika.ExchangeType.TOPIC, durable=True, passive=True
        )
        await queue.bind(event_exchange, routing_key="connection.created")
        await queue.bind(event_exchange, routing_key="connection.closed")
        await queue.consume(self._on_broker_connection_event)
        self._logger.info(
            f"{self._config.svc_name} :: Подписка на события брокера connection.created/closed."
        )

    def _rabbitmq_management_connections_settings(self) -> tuple[str, str]:
        amqp_url = (self._config.broker or {}).get("amqp_url", "")
        parsed = urlparse(amqp_url)
        host = parsed.hostname or os.getenv("RABBIT_HOST", "rabbitmq")
        port = os.getenv("RABBIT_UI_PORT", "15672")
        user = parsed.username or os.getenv("RABBITMQ_DEFAULT_USER", "guest")
        password = parsed.password or os.getenv("RABBITMQ_DEFAULT_PASS", "guest")
        url = f"http://{host}:{port}/api/connections"
        auth_token = base64.b64encode(f"{user}:{password}".encode()).decode()
        return url, auth_token

    @staticmethod
    def _fetch_rabbitmq_json(url: str, auth_token: str):
        request = Request(url, headers={"Authorization": f"Basic {auth_token}"})
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    async def _fetch_rabbitmq_management_connections(self) -> list:
        url, auth_token = self._rabbitmq_management_connections_settings()
        payload = await asyncio.to_thread(self._fetch_rabbitmq_json, url, auth_token)
        if not isinstance(payload, list):
            return []
        return payload

    async def _restore_connected_connectors_from_live_sessions(self) -> None:
        """После рестарта сервиса зелёный кружок ставится по живым MQTT-сессиям брокера.

        Не пишет качество 101 и не шлёт full_configuration: коннектор уже работает
        на существующей сессии и сам не повторяет getConfig.
        """
        try:
            connections = await self._fetch_rabbitmq_management_connections()
            allowed = {
                str(node).strip().lower()
                for node in (getattr(self._config, "nodes", None) or [])
                if node
            }
            restored: list[str] = []
            for conn_id in live_mqtt_connector_ids_from_management_connections(connections):
                if allowed and conn_id not in allowed:
                    continue
                # connection.closed мог прийти после подписки и до снимка API
                if self._connector_session_epoch.get(conn_id, 0) != 0:
                    continue
                if conn_id in self._connected_connectors:
                    continue
                self._connected_connectors.add(conn_id)
                restored.append(conn_id)

            if restored:
                self._logger.info(
                    f"{self._config.svc_name} :: Восстановлен статус MQTT-связи "
                    f"по живым сессиям: {restored}."
                )
        except Exception as ex:
            self._logger.warning(
                f"{self._config.svc_name} :: Не удалось восстановить статус MQTT-связи "
                f"по живым сессиям: {ex}."
            )

    async def on_startup(self) -> None:

        await super().on_startup()

        try:
            payload = {}
            if self._config.nodes: # type: ignore
                payload["id"] = self._config.nodes # type: ignore
                for conn_id in self._config.nodes:
                    await self._bind_conn(conn_id=conn_id, bind=True)
            else:
                await self._bind_conn(conn_id="*", bind=True)
            await self._subscribe_broker_connection_events()
            await self._restore_connected_connectors_from_live_sessions()
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: Ошибка инициализации сервиса коннекторов: {ex}")

    async def on_shutdown(self) -> None:
        channel = self._broker_events_channel
        self._broker_events_channel = None
        if channel is not None:
            try:
                await channel.close()
            except Exception:
                pass
        await super().on_shutdown()

    async def _bind_conn(self, conn_id: str, bind: bool = True):
        func = (self._amqp_consume_queue.unbind, self._amqp_consume_queue.bind)[bind]
        await func(exchange=self._exchange, routing_key=f"prsConnector.model.link_tag.{conn_id}")
        await func(exchange=self._exchange, routing_key=f"prsConnector.model.tag_link_updated.{conn_id}")
        await func(exchange=self._exchange, routing_key=f"prsConnector.model.unlink_tag.{conn_id}")
        await func(exchange=self._exchange, routing_key=f"prsConnector.model.tag_updated.{conn_id}")
        await func(exchange=self._exchange, routing_key=f"prsConnector.model.tag_deleted.{conn_id}")
        await func(exchange=self._exchange, routing_key=f"prsConnector.model.updated.{conn_id}")
        await func(exchange=self._exchange, routing_key=f"prsConnector.model.deleted.{conn_id}")
        await func(exchange=self._exchange, routing_key=f"prsConnector.connection_lost.{conn_id}")
        self._logger.info(f"{self._config.svc_name} :: Коннектор {conn_id} {('от', 'при')[bind]}вязан.")

    async def _deleting(self, mes: dict, routing_key: str | None = None):
        # удаление коннектора из модели:
        # делаем полную отвязку по этому коннектору
        conn_id = mes["id"]
        await self._bind_conn(conn_id, False)
        return {"response": True}

    async def _deleted(self, mes: dict, routing_key: str | None = None):
        deleted_conn_id = mes["id"]
        self._invalidate_connector_session(deleted_conn_id)
        self._connector_tag_ids.pop(deleted_conn_id, None)
        self._connector_session_epoch.pop(deleted_conn_id, None)
        self._mqtt_broker_conn_by_connector.pop(deleted_conn_id, None)
        self._connector_log_lines.pop(deleted_conn_id, None)
        self._connector_command_output_lines.pop(deleted_conn_id, None)
        payload = {
            "action": "prsConnector.deleted",
            "data": {
                "id": deleted_conn_id
            }
        }
        await self._post_message(mes=payload, routing_key=f"prs2conn.{deleted_conn_id}")

        return {"response": True}

    async def _updated(self, mes: dict, routing_key: str | None = None):
        conn_id = mes["id"]
        res = await self._get_connector_data(conn_id=conn_id)
        if not res:
            self._logger.error(f"{self._config.svc_name} :: Отсутствует коннектор {conn_id}.")
            return {}
        if is_camera_connector(res.get("prsEntityTypeCode")) or config_is_camera(
            res.get("prsJsonConfigString")
        ):
            return {"response": True}

        mes_for_connector = {
            "action": "prsConnector.connector_configuration",
            "data": res
        }
        await self._post_message(mes=mes_for_connector, routing_key=f"prs2conn.{conn_id}")
        self._logger.info(f"{self._config.svc_name} :: Отправлена конфигурация коннектору {conn_id}.")

        return {"response": True}

settings = ConnectorsMQTTAppSettings()

app = ConnectorsMQTTApp(settings=settings, title="ConnectorsApp")
