import sys
import os
import json
import asyncio
import numbers
import copy
from abc import ABC, abstractmethod
from typing import Any, List, Tuple

import redis.asyncio as redis
import pandas as pd
from pandas.api.types import is_numeric_dtype
import numpy as np

sys.path.append(".")

from src.common import app_svc
from src.services.dataStorages.app.dataStorages_app_base_settings import DataStoragesAppBaseSettings

from src.common.hierarchy import (
    CN_SCOPE_BASE, CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE
)
import src.common.times as t
from src.common.tag_data_points import tag_data_points_json_safe
from src.common.consts import (
    CNTagValueTypes as TVT,
    Order
)
from src.common.virtual_method_lookup import find_active_virtual_method_id

def linear_interpolated(start_point: Tuple[int, Any],
                        end_point: Tuple[int, Any],
                        x: int):
    """ Получение линейно интерполированного значения по двум точкам.
    Если в качестве координат `y` переданы нечисловые значения, возвращается
    start_point[1]

    :param start_point: Кортеж координат начальной точки
    :type start_point: Tuple[int, Any]
    :param end_point: Кортеж координат конечной точки
    :type end_point: Tuple[int, Any]
    :param x: координата x точки, для которой надо получить интерполированное значение
    :type x: int
    :param return_type: Тип возвращаемого значения
    :type return_type: int

    :return: Интерполированное значение
    :rtype: Any
    """
    x0, y0 = start_point
    x1, y1 = end_point
    if not isinstance(y0, numbers.Number) or not isinstance(y1, numbers.Number):
        return y0

    if y0 == y1:
        return y0

    if x0 == x1:
        return y0

    return (x-x0)/(x1-x0)*(y1-y0)+y0

class DataStoragesAppBase(app_svc.AppSvc, ABC):
    """Базовый класс для хранилищ данных.
    Реализует общую логику: работа с кэшем, поддержка нескольких экземпляров
    хранилища одного типа и т.д.

    Для работы данному классу требуется информация о тегах.
    Правильное поведение - запрос через брокер сообщений данных о теге, но
    пока сделаем, чтобы класс сам брал из иерархии нужные данные.

    Класс реализует кэш json-вида.

    "<tag_id1>.<service_name>": {
        "prsActive": true,
        "prsUpdate": true,
        "prsValueTypeCode": 1,
        "prsStep": false,
        "dss": {
            "dsId1": {}, # prsStore
            "dsId2": {}
        },
        "data": [(x, y, q)]
    }
    "<ds_id1>.<service_name>": {
        "prsActive": True,
        "tags": ["<tag_id1>", "<tag_id2>"]
    }

1) Кэш тегов строится по мере того, как происходит обращение
   записи/чтения к тегу
2) Кэш для баз данных вообще не строится
3) Каждый экземпляр сервиса создаёт свою уникальную очередь,
   которая подписывается на изменения поддерживаемых данным
   сервисом баз данных. В случае удаления базы не забываем эту убрать и
   подписку.
4) В случае создания новой базы её должен подхватить сервис, у которого
   не конкретизированы в конфигурации поддерживаемые им базы.
   Следствие: если у какого-то сервиса указана поддерживаемая им база(-ы),
   то у всех сервисов этого типа должны быть тоже указаны базы. Так как
   возможна ситуация:
   а) в модели две базы одного типа;
   б) есть два сервиса одного типа, у одного указана первая база, у второго
      ничего не указано, поэтому
   в) первый сервис поддерживает одну, указанную ему, базу, а второй - обе.
   В принципе, это не ошибка...
5) При выполнении команды linkTag кэш тега не строится для упрощения кода:
   кэш построится при первом обращении к тегу.
6) Данные кэша разделены на два ключа, чтобы можно было установить время
   жизни ключа "<service_name>:<tag_id1>". Ключ же "<service_name>" служит
   для хранения данных. Данные же будут удаляться при сбросе кэша в базу.
7) Сброс кэша в базу: сначала читаем список всех тегов базы из ldap, потом
   ищем данные уже в кэше.
8) UnlinkTag, тем не менее, удаляет ключ из "<service_name>:<dsId1>",
   предварительно сбросив кэш в базу.

    Args:
        settings (DataStoragesAppBaseSettings): Параметры конфигурации
    """

    def __init__(
            self, settings: DataStoragesAppBaseSettings, *args, **kwargs
        ):
        super().__init__(settings, *args, **kwargs)

        # словарь коннектов к хранилищам. имеет вид:
        # {
        #    "<ds_id>": <connection_pool>
        # }
        self._connection_pools = {}
    def _add_app_handlers(self):
        self._handlers["prsTag.app.data_get.*"] = self._tag_get
        self._handlers["prsTag.app.data_set.*"] = self._tag_set
        self._handlers["prsTag.model.updated.*"] = self._tag_updated
        self._handlers["prsTag.model.deleted.*"] = self._tag_deleted
        self._handlers["prsAlert.app.alarm_acked.*"] = self._alarm_ack
        self._handlers["prsAlert.app.alarm_on.*"] = self._alarm_on
        self._handlers["prsAlert.app.alarm_off.*"] = self._alarm_off
        self._handlers["prsAlert.model.deleted.*"] = self._alert_deleted
        self._handlers["prsDataStorage.model.link_tag.*"] = self._link_tag
        self._handlers["prsDataStorage.model.unlink_tag.*"] = self._unlink_tag
        self._handlers["prsDataStorage.model.link_alert.*"] = self._link_alert
        self._handlers["prsDataStorage.model.unlink_alert.*"] = self._unlink_alert
        self._handlers["prsMethod.model.created"] = self._prs_method_model_touch_tag_subscription
        self._handlers["prsMethod.model.updated.*"] = self._prs_method_model_touch_tag_subscription
        self._handlers["prsMethod.model.deleted.*"] = self._prs_method_model_deleted

    async def _bind_tag(self, tag_id: str, bind: bool) -> None:
        """
        Привязка тега для прослушивания.
        """
        self._logger.debug(f"{self._config.svc_name} :: Привязка очереди для тега {tag_id}.")

        if bind:
            await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=f"prsTag.app.data_get.{tag_id}")
            await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=f"prsTag.app.data_set.{tag_id}")
            await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=f"prsTag.model.updated.{tag_id}")
            await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=f"prsTag.model.deleted.{tag_id}")
        else:
            await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key=f"prsTag.app.data_get.{tag_id}")
            await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key=f"prsTag.app.data_set.{tag_id}")
            await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key=f"prsTag.model.updated.{tag_id}")
            await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key=f"prsTag.model.deleted.{tag_id}")

    async def _tag_linked_to_datastorage(self, tag_id: str) -> bool:
        """В модели есть prsDatastorageTagData для тега (история в БД)."""
        try:
            ds_root = await self._hierarchy.get_node_id("cn=dataStorages,cn=prs")
        except Exception:
            return False
        res = await self._hierarchy.search(
            {
                "base": ds_root,
                "scope": CN_SCOPE_SUBTREE,
                "filter": {"cn": [tag_id], "objectClass": ["prsDatastorageTagData"]},
                "attributes": ["cn"],
                "deref": False,
            }
        )
        return bool(res)

    async def _sync_parent_tag_data_get_subscription(self, parent_tag_id: str) -> None:
        """Подписка prsTag.app.data_get.<tag> нужна и для тегов с историей, и для виртуальных (prsEntityTypeCode=1)."""
        if not parent_tag_id:
            return
        need = await find_active_virtual_method_id(self._hierarchy, parent_tag_id) is not None
        need = need or await self._tag_linked_to_datastorage(parent_tag_id)
        try:
            await self._bind_tag(parent_tag_id, need)
        except Exception as ex:
            self._logger.error(
                f"{self._config.svc_name} :: Ошибка привязки prsTag.app.data_get для тега '{parent_tag_id}': {ex}"
            )

    async def _prs_method_model_touch_tag_subscription(self, mes: dict, routing_key: str | None = None) -> None:
        method_id = mes.get("id")
        if not method_id:
            return
        try:
            parent, _ = await self._hierarchy.get_parent(method_id)
        except Exception:
            return
        if parent:
            await self._sync_parent_tag_data_get_subscription(parent)

    async def _prs_method_model_deleted(self, mes: dict, routing_key: str | None = None) -> None:
        parent = mes.get("parentId")
        if parent:
            await self._sync_parent_tag_data_get_subscription(parent)
            return
        method_id = mes.get("id")
        if not method_id:
            return
        try:
            p, _ = await self._hierarchy.get_parent(method_id)
        except Exception:
            return
        if p:
            await self._sync_parent_tag_data_get_subscription(p)

    async def _bind_all_virtual_method_parent_tags(self) -> None:
        """После старта: привязка data_get для родителей активных виртуальных методов (без привязки к хранилищу)."""
        try:
            rows = await self._hierarchy.search(
                {
                    "filter": {"objectClass": ["prsMethod"], "prsActive": ["TRUE"]},
                    "attributes": ["prsEntityTypeCode", "cn"],
                }
            )
        except Exception as ex:
            self._logger.warning(f"{self._config.svc_name} :: Не удалось найти методы для привязки виртуальных тегов: {ex}")
            return
        seen: set[str] = set()
        for row in rows or []:
            attrs = row[2]
            raw = attrs.get("prsEntityTypeCode", ["0"])
            try:
                if int(raw[0]) != 1:
                    continue
            except Exception:
                continue
            mid = row[0]
            try:
                parent, _ = await self._hierarchy.get_parent(mid)
            except Exception:
                continue
            if not parent or parent in seen:
                continue
            seen.add(parent)
            await self._sync_parent_tag_data_get_subscription(parent)

    async def _bind_alert(self, alert_id: str, bind: bool) -> None:
        """
        Привязка тревоги для прослушивания.
        """
        self._logger.debug(f"{self._config.svc_name} :: Привязка очереди для тревоги {alert_id}.")

        # изменения в модели нас не интересуют: если тревога становится неактивной, то просто не будет
        # сообщений об изменении её состояния
        # хотя может быть изменено имя таблицы, в которой хранятся данные по тревоге
        # TODO: обрабатывать попытки изменить имя таблицы
        if bind:
            await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=f"prsAlert.app.alarm_acked.{alert_id}")
            await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=f"prsAlert.app.alarm_on.{alert_id}")
            await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=f"prsAlert.app.alarm_off.{alert_id}")
            await self._amqp_consume_queue.bind(exchange=self._exchange, routing_key=f"prsAlert.model.deleted.{alert_id}")
        else:
            await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key=f"prsAlert.app.alarm_acked.{alert_id}")
            await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key=f"prsAlert.app.alarm_on.{alert_id}")
            await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key=f"prsAlert.app.alarm_off.{alert_id}")
            await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key=f"prsAlert.model.deleted.{alert_id}")

    async def _bind_ds(self, ds_id: str, bind: bool = True):
        func = (self._amqp_consume_queue.unbind, self._amqp_consume_queue.bind)[bind]
        await func(exchange=self._exchange, routing_key=f"prsDataStorage.model.link_tag.{ds_id}")
        await func(exchange=self._exchange, routing_key=f"prsDataStorage.model.unlink_tag.{ds_id}")
        await func(exchange=self._exchange, routing_key=f"prsDataStorage.model.link_alert.{ds_id}")
        await func(exchange=self._exchange, routing_key=f"prsDataStorage.model.unlink_alert.{ds_id}")
        await func(exchange=self._exchange, routing_key=f"prsDataStorage.model.updating.{ds_id}")
        await func(exchange=self._exchange, routing_key=f"prsDataStorage.model.may_update.{ds_id}")
        await func(exchange=self._exchange, routing_key=f"prsDataStorage.model.may_delete.{ds_id}")
        await func(exchange=self._exchange, routing_key=f"prsDataStorage.model.deleting.{ds_id}")

    async def _is_supported_ds_type(self, ds_type: int | None) -> bool:
        return ds_type is not None and int(ds_type) == int(self._config.datastorage_type)

    def _safe_json_attr(self, ldap_attr, default=None):
        if not ldap_attr:
            return default
        raw = ldap_attr[0] if isinstance(ldap_attr, list) else ldap_attr
        if raw is None:
            return default
        if isinstance(raw, (dict, list, int, float, bool)):
            return raw
        if isinstance(raw, str):
            s = raw.strip()
            if s == "":
                return default
            try:
                return json.loads(s)
            except Exception:
                return raw
        return raw

    def _configured_ds_ids(self) -> list[str]:
        # Primary source (current contract): AppSvcSettings.nodes
        nodes = getattr(self._config, "nodes", None)
        if isinstance(nodes, list) and nodes:
            return [str(x) for x in nodes if x]
        # Backward compatibility for legacy configs.
        legacy = getattr(self._config, "datastorages_id", None)
        if isinstance(legacy, list) and legacy:
            return [str(x) for x in legacy if x]
        return []

    async def _get_ds_info(self, ds_id: str) -> dict | None:
        payload = {
            "id": [ds_id],
            "attributes": ["prsEntityTypeCode", "prsJsonConfigString", "prsActive"],
            "deref": False,
        }
        ds = await self._hierarchy.search(payload=payload)
        if not ds:
            return None
        attrs = ds[0][2]
        ds_type_raw = attrs.get("prsEntityTypeCode")
        try:
            ds_type = int(ds_type_raw[0]) if ds_type_raw and ds_type_raw[0] is not None else None
        except Exception:
            ds_type = None
        return {"attrs": attrs, "type": ds_type}

    async def _remove_supported_ds(self, ds_id: str) -> None:
        if ds_id not in self._connection_pools:
            return
        # unbind ds-level handlers
        await self._bind_ds(ds_id, False)

        # unbind tags/alerts we previously bound (if cache exists)
        try:
            async with self._cache.get_redis() as r:
                cached = await r.json().get(f"{ds_id}.{self._config.svc_name}")
                if isinstance(cached, dict):
                    for tag_id in cached.get("tags") or []:
                        await self._bind_tag(str(tag_id), False)
                    for alert_id in cached.get("alerts") or []:
                        await self._bind_alert(str(alert_id), False)
                await r.json().delete(f"{ds_id}.{self._config.svc_name}")
        except Exception:
            # cache may be unavailable during shutdown; don't fail hard
            pass

        pool = self._connection_pools.pop(ds_id, None)
        # close pool if driver supports it (asyncpg pool has close())
        try:
            if pool is not None and hasattr(pool, "close"):
                maybe = pool.close()
                if asyncio.iscoroutine(maybe):
                    await maybe
        except Exception:
            pass

    async def _add_supported_ds(self, ds_id: str) -> None:

        """Метод добавляет в список поддерживаемых хранилищ новое.

        Args:
            ds_id (str): _description_
        """
        ds_info = await self._get_ds_info(ds_id)
        if ds_info is None:
            return

        if not await self._is_supported_ds_type(ds_info["type"]):
            return

        ds_attrs = ds_info["attrs"]

        # If already supported, do nothing.
        if ds_id in self._connection_pools:
            return

        # привяжемся к сообщениям, касающимся изменениям хранилища ---------------------------------
        await self._bind_ds(ds_id, True)
        # ----------------------------------------------------------------------------------------
        if ds_attrs["prsActive"][0] == "TRUE":
            # если хранилище активно, то подсоединимся к нему
            connected = False
            while not connected:
                try:
                    self._connection_pools[ds_id] = await self._create_connection_pool(
                        json.loads(ds_attrs["prsJsonConfigString"][0])
                    )
                    self._logger.info(f"{self._config.svc_name} :: Связь с базой данных {ds_id} установлена.")
                    connected = True
                except Exception as ex:
                    self._logger.error(f"{self._config.svc_name} :: Ошибка связи с базой данных '{ds_id}': {ex}")
                    await asyncio.sleep(5)


        payload = {
            "base": ds_id,
            "filter": {
                "objectClass": ["prsDatastorageTagData"]
            },
            "attributes": ["cn"]
        }

        ds_cache = {
            "prsActive": ds_attrs["prsActive"][0] == "TRUE",
            "prsJsonConfigString": json.loads(ds_attrs["prsJsonConfigString"][0]),
            "tags": [],
            "alerts": []
        }

        tags = await self._hierarchy.search(payload)
        for tag in tags:
            await self._bind_tag(tag[2]["cn"][0], True)
            ds_cache["tags"].append(tag[2]["cn"][0])

        # Startup prewarm: build per-tag cache for all linked tags for faster first reads.
        if ds_cache["tags"]:
            prewarm = await asyncio.gather(
                *[self._create_tag_cache(tag_id) for tag_id in ds_cache["tags"]],
                return_exceptions=True,
            )
            for tag_id, res in zip(ds_cache["tags"], prewarm):
                if isinstance(res, Exception):
                    self._logger.error(
                        f"{self._config.svc_name} :: Ошибка предзаполнения кэша тега {tag_id}: {res}"
                    )

        payload = {
            "base": ds_id,
            "filter": {
                "objectClass": ["prsDatastorageAlertData"]
            },
            "attributes": ["cn"]
        }
        alerts = await self._hierarchy.search(payload)
        for alert in alerts:
            await self._bind_alert(alert[2]["cn"][0], True)
            ds_cache["alerts"].append(alert[2]["cn"][0])

        async with self._cache.get_redis() as r:
            await r.json().set(name=f"{ds_id}.{self._config.svc_name}", path="$", obj=ds_cache)

    async def on_startup(self) -> None:

        await super().on_startup()

        # сделаем перепривязку очереди, так как слушать будем только нужные сообщения
        # группа сообщений, где вместо * передается id тега или тревоги --------------------------
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsTag.app.data_get.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsTag.app.data_set.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsTag.model.updating.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsTag.model.updated.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsTag.model.deleting.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsTag.model.deleted.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsAlert.app.alarm_acked.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsAlert.app.alarm_on.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsAlert.app.alarm_off.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsAlert.model.deleting.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsAlert.model.deleted.*")
        # ----------------------------------------------------------------------------------------

        # группа сообщений, где вместо * передается id хранилища ---------------------------------
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsDataStorage.model.link_tag.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsDataStorage.model.unlink_tag.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsDataStorage.model.link_alert.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsDataStorage.model.unlink_alert.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsDataStorage.model.may_update.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsDataStorage.model.updating.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsDataStorage.model.deleting.*")
        await self._amqp_consume_queue.unbind(exchange=self._exchange, routing_key="prsDataStorage.model.may_delete.*")
        # Важно: bindings prsMethod.model.* нужны постоянно, чтобы при создании/изменении
        # метода оперативно (пере)привязывать prsTag.app.data_get.<tag> для виртуальных тегов.
        # ----------------------------------------------------------------------------------------

        try:
            payload = {}
            configured_ids = self._configured_ds_ids()
            if configured_ids:
                payload["id"] = configured_ids
            else:
                ds_node_id = await self._hierarchy.get_node_id("cn=dataStorages,cn=prs")
                payload = {
                    "base": ds_node_id,
                    "filter": {
                        "prsEntityTypeCode": [self._config.datastorage_type],
                        "objectClass": ["prsDataStorage"]
                    }
                }

            loop = asyncio.get_event_loop()
            dss = await self._hierarchy.search(payload=payload)
            for ds in dss:
                await self._add_supported_ds(ds[0])

            await self._bind_all_virtual_method_parent_tags()

            loop.call_later(self._config.cache_data_period, lambda: asyncio.create_task(self._write_cache_data()))

        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: Ошибка инициализации хранилища: {ex}")

    async def _alert_deleted(self, mes: dict, routing_key: str = None):
        await self._bind_alert(mes['id'], False)
        await self._delete_alert_cache(mes['id'])

        payload = {
            "base": None,
            "filter": {
                "objectClass": ["prsDatastorageAlertData"],
                "cn": [mes['id']]
            },
            "attributes": ["prsStore"]
        }
        for ds_id in self._connection_pools.keys():
            payload["base"] = ds_id
            alert_data = await self._hierarchy.search(payload=payload)
            if alert_data:
                await self._hierarchy.delete(alert_data[0][0])

    async def _tag_updated(self, mes: dict, routing_key: str = None):
        pass

    async def _tag_deleted(self, mes: dict, routing_key: str = None):
        self._logger.debug(f"{self._config.svc_name} :: Удаление тега. routing key: {routing_key}; mes: {mes}.")

        await self._bind_tag(mes['id'], False)
        await self._delete_tag_cache(mes['id'])

        payload = {
            "base": None,
            "filter": {
                "objectClass": ["prsDatastorageTagData"],
                "cn": [mes['id']]
            },
            "attributes": ["prsStore"]
        }
        for ds_id in self._connection_pools.keys():
            payload["base"] = ds_id
            tag_data = await self._hierarchy.search(payload=payload)
            if tag_data:
                # TODO: перенести в dataStorages_model!!!
                await self._hierarchy.delete(tag_data[0][0])

    async def created(self, mes: dict, routing_key: str = None) -> None:
        # команда добавления новой базы данных
        # если в конфигурации сервиса указаны конкретные id баз для поддержки,
        # то эта ситуация отслеживается в методе _reject_message

        if self._configured_ds_ids():
            return
        await self._add_supported_ds(mes["id"])

    async def _created(self, mes: dict, routing_key: str | None = None):
        return await self.created(mes, routing_key=routing_key)

    async def updating(self, mes: dict, routing_key: str = None) -> None:
        # обновление атрибутов хранилища
        # привязка/отвязка тегов и тревог выполняется
        # методами link/unlink
        # необслуживаемые хранилища отсекаются методом reject_message
        ds_id = mes["id"]
        ds_info = await self._get_ds_info(ds_id)
        if ds_info is None:
            return

        if not await self._is_supported_ds_type(ds_info["type"]):
            # if we previously supported it, drop it
            await self._remove_supported_ds(ds_id)
            return

        if ds_id not in self._connection_pools:
            # became supported due to type change
            await self._add_supported_ds(ds_id)
            return

        payload = {
            "id": ds_id,
            "attributes": ["prsActive", "prsJsonConfigString"]
        }
        ds_data = await self._hierarchy.search(payload=payload)
        if not ds_data:
            self._logger.error(f"{self._config.svc_name} :: В модели нет данных по хранилищу {ds_id}")
            return

        self._connection_pools[ds_id] = None

        connected = False
        while not connected:
            try:
                self._connection_pools[ds_id] = await self._create_connection_pool(json.loads(ds_data[0][2]["prsJsonConfigString"][0]))
                self._logger.info(f"{self._config.svc_name} :: Связь с базой данных {ds_id} установлена.")
                connected = True
            except Exception as ex:
                self._logger.error(f"{self._config.svc_name} :: Ошибка связи с базой данных '{ds_id}': {ex}")
                await asyncio.sleep(5)

        return {"response": True}

    async def updated(self, mes: dict, routing_key: str | None = None):
        # type changes are applied after update; use this event to rebalance ownership
        ds_id = mes.get("id")
        if not ds_id:
            return {"response": True}
        ds_info = await self._get_ds_info(ds_id)
        if ds_info is None:
            return {"response": True}

        if await self._is_supported_ds_type(ds_info["type"]):
            if ds_id not in self._connection_pools:
                await self._add_supported_ds(ds_id)
        else:
            await self._remove_supported_ds(ds_id)
        return {"response": True}

    async def _updated(self, mes: dict, routing_key: str | None = None):
        return await self.updated(mes, routing_key=routing_key)

    async def deleted(self, mes: dict, routing_key: str | None = None):
        ds_id = mes.get("id")
        if ds_id:
            await self._remove_supported_ds(ds_id)
        return {"response": True}

    async def _deleted(self, mes: dict, routing_key: str | None = None):
        return await self.deleted(mes, routing_key=routing_key)

    async def _updating(self, mes: dict, routing_key: str | None = None):
        return await self.updating(mes, routing_key=routing_key)

    async def deleting(self, mes: dict, routing_key: str = None) -> None:
        # удаление хранилища
        # операция, неподдерживаемая Community версией
        pass

    async def _deleting(self, mes: dict, routing_key: str | None = None):
        return await self.deleting(mes, routing_key=routing_key)

    async def _alarm_on(self, mes: dict, routing_key: str = None) -> None:
        pass

    async def _alarm_ack(self, mes: dict, routing_key: str = None) -> None:
        pass

    async def _alarm_off(self, mes: dict, routing_key: str = None) -> None:
        """Факт пропадания тревоги.

        Args:
            mes (dict): {
                "action": "alerts.alrmOff",
                "data": {
                    "alertId": "alert_id",
                    "x": 123
                }
            }
        """
        pass

    async def _reject_message(self, mes: dict) -> bool:

        """
        # отсечём необрабатываемые сообщения:
        # если создано хранилище необслуживаемого типа
        if mes["action"] == "dataStorages.created":
            # если указан список поддерживаемых хранилищ
            if self._config.datastorages_id:
                return True

            payload = {
                "id": mes["id"],
                "attributes": ["prsEntityTypeCode"]
            }
            ds_res = await self._hierarchy.search(payload=payload)
            if not ds_res:
                self._logger.error(
                    f"{self._config.svc_name} :: В модели отсутствует хранилище {mes['data']['id']}"
                )
                return True

            if int(ds_res[0][2]["prsEntityTypCode"][0]) != \
                self._config.datastorage_type:
                return True

        # ...если приходят другие сообщения относительно необслуживаемых
        # хранилищ
        if mes["action"] in [
            "dataStorages.linkTag", "dataStorages.unlinkTag"
            "dataStorages.linkAlert", "dataStorages.unlinkAlert"
            ]:
            return not mes["dataStorageId"] in self._connection_pools.keys()

        if mes["action"] in [
            "dataStorages.updated",
            "dataStorages.deleted"
        ]:
            return not mes["id"] in self._connection_pools.keys()
        """
        return False

    @abstractmethod
    async def _create_store_name_for_new_tag(self,
            ds_id: str, tag_id: str) -> dict | None:
        """Метод, создающий имя для нового места хранения данных тега.

        Args:
            ds_id (str): id хранилища
            tag_id (_type_): id тега

        Returns:
            dict: json с описанием хранилища тега
        """
        pass

    async def _check_store_name_for_new_tag(self, ds_id: str, store: dict) -> bool:
        """Метод проверяет на корректность имя хранилища для нового тега,
        переданное клиентом.

        Args:
            store (dict): новое хранилище для тега

        Returns:
            bool: флаг корректности нового имени
        """
        return True

    @abstractmethod
    async def _create_store_for_tag(self, tag_id: str, ds_id: str, store: dict) -> None:
        pass

    @abstractmethod
    async def _create_store_name_for_new_alert(self,
            ds_id: str, alert_id: str) -> dict | None:
        """Метод, создающий имя для нового места хранения данных тревоги.

        Args:
            ds_id (str): id хранилища
            alert_id (_type_): id тревоги

        Returns:
            dict: json с описанием хранилища тревоги
        """
        pass

    async def _check_store_name_for_new_alert(self, ds_id: str, store: dict) -> bool:
        """Метод проверяет на корректность имя хранилища для новой тревоги, переданное клиентом.

        Args:
            store (dict): новое хранилище для тревоги

        Returns:
            bool: флаг корректности нового имени
        """
        return True

    @abstractmethod
    async def _create_store_for_alert(self, alert_id: str, ds_id: str, store: dict) -> None:
        pass

    async def _link_tag(self, mes: dict, routing_key: str = None) -> dict | None:
        """Метод привязки тега к хранилищу.
        В сообщении может приходить атрибут prsStore: пользователь знает,
        как организовать хранение данных для тега
        (как назвать метрику, таблицу и т.д.),
        иначе хранилище само организовывает место для хранения данных тега.

        Args:
            mes (dict):
                {
                    "tagId": "tag_id",
                    "attributes": {
                        "prsStore": {}
                }

        """

        tag_id = mes["tagId"]
        ds_id = mes["dataStorageId"]
        if ds_id not in self._connection_pools.keys():
            self._logger.error(f"{self._config.svc_name} :: Хранилища {ds_id} нет в списке поддерживаемых.")
            return

        store = None
        if mes.get("attributes"):
            store = mes["attributes"].get("prsStore")
        if store is not None:
            check = await self._check_store_name_for_new_tag(ds_id=ds_id, store=store)
            if not check:
                self._logger.error(f"{self._config.svc_name} :: '{store}' не подходит для хранения данных тега '{tag_id}'.")
                return {"prsStore": None}
        else:
            store = await self._create_store_name_for_new_tag(ds_id=ds_id, tag_id=tag_id)

        await self._create_store_for_tag(tag_id=tag_id, ds_id=ds_id, store=store)

        await self._bind_tag(tag_id, True)

        async with self._cache.get_redis() as r:
            await r.json().arrappend(f"{ds_id}.{self._config.svc_name}", "tags", tag_id)

        return {"prsStore": store}

    async def _link_alert(self, mes: dict, routing_key: str = None) -> dict:
        """Метод привязки тревоги к хранилищу.
        Атрибут ``prsStore`` должен быть вида
        ``{"tableName": "<some_table>"}`` либо отсутствовать

        Args:
            mes (dict): {
                "alertId": "alert_id",
                "dataStorageId": "ds_id",
                "attributes": {
                    "prsStore": {"tableName": "<some_table>"}
            }

        """

        alert_id = mes["alertId"]
        ds_id = mes['dataStorageId']
        if ds_id not in self._connection_pools.keys():
            self._logger.error(f"{self._config.svc_name} :: Хранилища {ds_id} нет в списке поддерживаемых.")
            return

        store = None
        if mes.get("attributes"):
            store = mes["attributes"].get("prsStore")
        if store is not None:
            check = await self._check_store_name_for_new_alert(ds_id=ds_id, store=store)
            if not check:
                self._logger.error(f"{self._config.svc_name} :: '{store}' не подходит для хранения данных тревоги '{alert_id}'.")
                return {"prsStore": None}
        else:
            store = await self._create_store_name_for_new_alert(ds_id=ds_id, alert_id=alert_id)

        await self._create_store_for_alert(alert_id=alert_id, ds_id=ds_id, store=store)

        await self._bind_alert(alert_id, True)

        async with self._cache.get_redis() as r:
            await r.json().arrappend(f"{ds_id}.{self._config.svc_name}", "alerts", alert_id)

        return {"prsStore": store}

    async def _unlink_alert(self, mes: dict, routing_key: str = None) -> None:
        pass

    async def _unlink_tag(self, mes: dict, routing_key: str = None) -> None:
        pass

    @abstractmethod
    async def _write_tag_data_to_db(
            self, tag_id: str) -> None:

        # метод, переопределяемый в классах-потомках
        # записывает данные одного тега в хранилище
        pass

    async def _write_cache_data(self, tag_ids: list[str] = None) -> None:
        """Функция сбрасывает кэш данных тегов в базу для поддерживаемых
        баз данных если tag_ids - пустой список, то сбрасываются
        все теги из кэша иначе - только те, которые в списке.

        При сбросе кэша не проверяется активность/неактивность ни тегов, ни
        хранилищ: сам вызов этой функции может инициироваться переводом
        тега или хранилища в неактивное состояние.

        Args:
            tag_ids (str], optional): список тегов.
        """

        self._logger.debug(f"Запись кэша данных в хранилища для тегов {tag_ids}...")
        scheduled = False
        try:
            async with self._cache.get_redis() as r:
                if not tag_ids:
                    # если пустой список тегов, это значит, что сбрасывается весь кэш,
                    # то есть происходит запуск процедуры по расписанию
                    scheduled = True
                    tag_ids = set()

                    for ds_id in self._connection_pools.keys():
                        # определим, активна ли база
                        res = await r.json().get(
                            f"{ds_id}.{self._config.svc_name}", "prsActive", "tags"
                        )
                        if res is None:
                            self._logger.error(f"{self._config.svc_name} :: Нет кэша для хранилища {ds_id}")
                            continue
                        if not res["prsActive"]:
                            self._logger.info(
                                f"{self._config.svc_name} :: Хранилище {ds_id} неактивно."
                            )
                            continue
                        tag_ids = tag_ids.union(set(res["tags"]))

                async with r.pipeline() as pipe:
                    for tag_id in tag_ids:
                        res = await pipe.json().get(
                            f"{tag_id}.{self._config.svc_name}", "prsActive"
                        ).json().arrlen(
                            f"{tag_id}.{self._config.svc_name}", "data"
                        ).execute()
                        if res[0] is None:
                            # если нет кэша у тега
                            if not await self._create_tag_cache(tag_id):
                                # если path != $, то возвращается одно значение
                                # если элемент не найден, то это значение = -1
                                index = await r.json().arrindex(
                                    f"{ds_id}.{self._config.svc_name}", "tags", tag_id
                                )

                                if index > -1:
                                    await r.json().arrpop(f"{ds_id}.{self._config.svc_name}", "tags", index)

                        # если тег активен и у него есть данные в кэше
                        if res[0] and res[1] > 0:
                            await self._write_tag_data_to_db(tag_id)

        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: Ошибка записи данных в базу: {ex}")

        loop = asyncio.get_event_loop()

        if scheduled:
            loop.call_later(self._config.cache_data_period, lambda: asyncio.create_task(self._write_cache_data()))

    async def _tag_set(self, mes: dict, routing_key: str = None) -> dict:
        """Запись точек в Redis-кэш тега.

        Должен возвращать JSON-совместимый dict: иначе при RPC ``reply=True``
        в ответ уйдёт ``null``, а ``tags_app`` воспримет это как отсутствие
        обработчика (424), хотя запись в кэш уже выполнена.

        Args:
            mes (dict): {
                "data": [
                    {
                        "tagId": "<some_id>",
                        "data": [(x,y,q)]
                    }
                ]
            }
        """
        result_items: list[dict] = []
        try:
            self._logger.debug(f"Tag set: {mes}")

            for tag_item in mes["data"]:
                tag_id = tag_item["tagId"]

                # проверим, активен ли тег и активны ли хранилища
                async with self._cache.get_redis() as r:
                    res = await r.json().get(f"{tag_id}.{self._config.svc_name}")

                    if res is None:
                        # если нет кэша у тега
                        cache = await self._create_tag_cache(tag_id)
                    else:
                        cache = res
                    if not cache["prsActive"]:
                        self._logger.info(f"{self._config.svc_name} :: Тег {tag_id} неактивен, данные не записываются.")
                    else:
                        await r.json().arrappend(
                            f"{tag_id}.{self._config.svc_name}",
                            "data", *tag_item["data"]
                        )
                        self._logger.info(f"{self._config.svc_name} :: Кэш тега {tag_id} обновлён.")
                        result_items.append(
                            {
                                "tagId": tag_id,
                                "data": tag_data_points_json_safe(
                                    list(tag_item["data"])
                                ),
                            }
                        )

        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: Ошибка обновления данных в кэше: {ex}")
        if result_items:
            return {"data": result_items}
        return {}

    async def _create_tag_cache(self, tag_id: str) -> dict | bool | None:
        """Функция подготовки кэша с данными о теге.

        Возвращаем всегда сформированный кэш целиком, независимо от того, был
        тег в кэше или ещё нет.

        Кэш для тега всегда строится на основании данных из иерархии. Текущие
        данные в кэше не учитываются, это повышает достоверность данных в кэше.

        Формат кэша:
        {
            "prsActive": true,
            "prsUpdate": true,
            "prsValueTypeCode": 1,
            "prsStep": false,
            "dss": {
                "dsId1": {}, # prsStore
                "dsId2": {}
            },
            "data": [(x, y, q)]
        }

        Args:
            tag_id (str): id тега, для которого формируем кэш
        Returns:
            dict | None: сформированный кэш тега
        """

        # получим атрибуты тега ---------------------------
        payload = {
            "id": tag_id,
            "attributes": [
                "prsActive",
                "prsUpdate",
                "prsValueTypeCode",
                "prsStep"
            ]
        }
        res = await self._hierarchy.search(payload=payload)
        if not res:
            return False
        tag_attrs = res[0][2]
        # ------------------------------------------------

        # подготовим первоначальный кэш тега из атрибутов ---
        tag_cache = {
            "prsActive": tag_attrs["prsActive"][0] == "TRUE",
            "prsUpdate": tag_attrs["prsUpdate"][0] == "TRUE",
            "prsValueTypeCode": int(tag_attrs["prsValueTypeCode"][0]),
            "prsStep": tag_attrs["prsStep"][0] == "TRUE",
            "dss": {},
            "data": []
        }

        # попробуем найти привязку тега к хранилищу ------------
        for ds_id in self._connection_pools.keys():
            payload = {
                "base": ds_id,
                "scope": CN_SCOPE_SUBTREE,
                "filter": {
                    "cn": [tag_id],
                    "objectClass": ["prsDatastorageTagData"]
                },
                "deref": False,
                "attributes": ["prsStore"]
            }
            res = await self._hierarchy.search(payload=payload)
            if res:
                tag_cache["dss"][ds_id] = self._safe_json_attr(res[0][2].get("prsStore"), default=None)
        # ------------------------------------------------------------

        try:
            async with self._cache.get_redis() as r:
                await r.json().set(name=f"{tag_id}.{self._config.svc_name}", path="$", obj=tag_cache)
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: {ex}")

        return tag_cache

    async def _delete_tag_cache(self, tag_id: str):
        try:
            async with self._cache.get_redis() as r:
                await r.json().delete(f"{tag_id}.{self._config.svc_name}")
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: {ex}")

    async def _find_active_virtual_method_id(self, tag_id: str) -> str | None:
        return await find_active_virtual_method_id(self._hierarchy, tag_id)

    async def _read_virtual_method_response(self, tag_id: str, mes: dict) -> dict | None:
        """None — читать из хранилища как обычно. Иначе ответ виртуального метода или ошибка."""
        ctx = mes.get("evalContextTagId")
        if ctx is not None and str(ctx) == str(tag_id):
            # Вложенный data_get при разборе параметров виртуального метода для того же тега:
            # иначе повторный virtual_data_get и двойной вызов пользовательского метода.
            return None
        mid = await self._find_active_virtual_method_id(tag_id)
        if not mid:
            return None
        crm = {k: v for k, v in mes.items() if k != "evalContextTagId"}
        res = await self._post_message(
            mes={"tagId": tag_id, "methodId": mid, "clientRequest": crm},
            reply=True,
            routing_key="prsMethod.app.virtual_data_get",
        )
        if res is None:
            return {"error": {"code": 424, "message": "Сервис методов недоступен для виртуального чтения."}}
        if isinstance(res, dict) and res.get("error"):
            return res
        if not isinstance(res, dict) or "data" not in res:
            return {"error": {"code": 500, "message": "Некорректный ответ виртуального метода."}}
        return res

    async def _create_alert_cache(self, alert_id: str) -> dict | bool | None:
        """Функция подготовки кэша с данными о тревоге.

        Возвращаем всегда сформированный кэш целиком, независимо от того, была
        тревога в кэше или ещё нет.

        Кэш для тревоги всегда строится на основании данных из иерархии. Текущие
        данные в кэше не учитываются, это повышает достоверность данных в кэше.

        Формат кэша:
        {
            "dss": {
                "dsId1": {}, # prsStore
                "dsId2": {}
            }
        }

        Args:
            alert_id (str): id тревоги, для которой формируем кэш

        Returns:
            dict | None: сформированный кэш тега
        """

        # подготовим первоначальный кэш тревоги ----------------
        alert_cache = {
            "dss": {}
        }

        # попробуем найти привязку тега к хранилищу ------------
        for ds_id in self._connection_pools.keys():
            payload = {
                "base": ds_id,
                "scope": CN_SCOPE_SUBTREE,
                "filter": {
                    "cn": [alert_id],
                    "objectClass": ["prsDatastorageAlertData"]
                },
                "deref": False,
                "attributes": ["prsStore"]
            }
            res = await self._hierarchy.search(payload=payload)
            if res:
                alert_cache["dss"][ds_id] = self._safe_json_attr(res[0][2].get("prsStore"), default=None)
        # ------------------------------------------------------------

        try:
            async with self._cache.get_redis() as r:
                await r.json().set(
                    name=f"{alert_id}.{self._config.svc_name}", path="$", obj=alert_cache, nx=True
                )
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: {ex}")

        return alert_cache

    async def _delete_alert_cache(self, alert_id: str):
        try:
            async with self._cache.get_redis() as r:
                await r.json().delete(f"{alert_id}.{self._config.svc_name}")
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: {ex}")

    async def _create_connection_pool(self, config: dict) -> Any:
        """Метод создаёт пул коннектов к базе.
        Конфигурация базы передаётся в словаре config.
        Каждый класс для специфического хранилища переопределяет этот метод

        Args:
            config (dict): _description_
        """
        pass

    async def _tag_get(self, mes: dict, routing_key: str = None) -> dict:
        """_summary_

        Args:
            mes (dict): {
                "tagId": [str],
                "start": int,
                "finish": int,
                "maxCount": int,
                "format": bool,
                "actual": bool,
                "value": Any,
                "count": int,
                "timeStep": int
            }

        Returns:
            _type_: _description_
        """

        # TODO: разобраться, как читать данные, если тег привязан к разным хранилищам

        self._logger.debug(f"Чтение данных: {mes}")

        accumulated: dict = {"data": []}
        remaining_tag_ids: list[str] = []
        for tag_id in mes["tagId"]:
            vres = await self._read_virtual_method_response(tag_id, mes)
            if vres is None:
                remaining_tag_ids.append(tag_id)
                continue
            if vres.get("error"):
                return vres
            for item in vres.get("data") or []:
                accumulated["data"].append(item)

        mes = {**mes, "tagId": remaining_tag_ids}
        if not remaining_tag_ids:
            self._logger.debug(f"Получение данных (виртуальные теги): {accumulated}")
            return accumulated

        mes.pop("evalContextTagId", None)

        tasks: dict = {}

        await self._write_cache_data(remaining_tag_ids)

        for tag_id in mes["tagId"]:
            # Если ключ actual установлен в true, ключ timeStep не учитывается
            if mes["actual"] or (mes["value"] is not None \
            and len(mes["value"]) > 0):
                mes["timeStep"] = None

            if mes["actual"]:
                tasks[tag_id]= asyncio.create_task(
                    self._data_get_actual(
                        tag_id,
                        mes["start"],
                        mes["finish"],
                        mes["count"],
                        mes["value"]
                    )
                )

            elif mes["timeStep"] is not None:
                tasks[tag_id]= asyncio.create_task(
                        self._data_get_interpolated(
                            tag_id,
                            mes["start"], mes["finish"],
                            mes["count"], mes["timeStep"]
                        )
                    )

            elif mes["start"] is None and \
                mes["count"] is None and \
                (mes["value"] is None or len(mes["value"]) == 0):
                tasks[tag_id] = asyncio.create_task(
                        self._data_get_one(
                            tag_id,
                            mes["finish"]
                        )
                    )

            else:
                # Множество значений
                tasks[tag_id]= asyncio.create_task(
                        self._data_get_many(
                            tag_id,
                            mes["start"],
                            mes["finish"],
                            mes["count"]
                        )
                    )

            if not tasks:
                self._logger.debug(f"Нет возвращаемых данных.")
                return accumulated

            for tag_id, task in tasks.items():
                # задачи нельзя выполнять параллельно - возникает ошибка при одновременном обращении к кэшу
                await task

                tag_data = task.result()

                if not mes["actual"] and \
                    (
                        mes["value"] is not None and \
                        len(mes["value"]) > 0
                    ):
                    tag_data = self._filter_data(
                        tag_data,
                        mes["value"],
                        self._tags[tag_id]['value_type'],
                        self._tags[tag_id]['step']
                    )
                    if mes["from_"] is None:
                        tag_data = [tag_data[-1]]

                excess = False
                if mes["maxCount"] is not None:
                    excess = len(tag_data) > mes["maxCount"]

                    if excess:
                        if mes["maxCount"] == 0:
                            tag_data = []
                        elif mes["maxCount"] == 1:
                            tag_data = tag_data[:1]
                        elif mes["maxCount"] == 2:
                            tag_data = [tag_data[0], tag_data[-1]]
                        else:
                            new_tag_data = tag_data[:mes["maxCount"] - 1]
                            new_tag_data.append(tag_data[-1])
                            tag_data = new_tag_data

                '''
                if mes["format"]:
                    svc.format_data(tag_data, data.format)
                '''
                new_item = {
                    "tagId": tag_id,
                    "data": tag_data
                }
                if mes["maxCount"]:
                    new_item["excess"] = excess
                accumulated["data"].append(new_item)

            self._logger.debug(f"Получение данных: {accumulated}")

        return accumulated

    def _filter_data(
            self, tag_data: List[tuple], value: List[Any], tag_type_code: int,
            tag_step: bool) -> List[tuple]:
        def estimate(x1: int, y1: int | float, x2: int, y2: int | float, y: int | float) -> int:
            '''
            Функция принимает на вход две точки прямой и значение, координату X которого возвращает.
            '''
            k = (y2 - y1)/(x2 - x1)
            b = y2 - k * x2

            x = round((y - b) / k)

            return x


        res = []
        if tag_step or tag_type_code not in [0, 1]:
            for item in tag_data:
                if tag_type_code == 4:
                    y = json.loads(item[1])
                else:
                    y = item[1]
                if y in value:
                    res.append(item)
        else:
            for i in range(1, len(tag_data)):
                x1 = tag_data[i - 1][0]
                x2 = tag_data[i][0]
                y1 = tag_data[i - 1][1]
                y2 = tag_data[i][1]
                if x1 == x2:
                    continue
                if y1 in value:
                    res.append(tag_data[i - 1])
                else:
                    if y1 is None or y2 is None:
                        continue
                    for val in value:
                        if val is None:
                            continue
                        if tag_type_code == 0 and isinstance(val, float):
                            continue
                        if ((y1 > val and y2 < val) or (y1 < val and y2 > val)):
                            x = estimate(x1, y1, x2, y2, val)
                            res.append((x, val, None))
            if tag_data[-1][1] in value:
                res.append(tag_data[-1])
        return res

    async def _data_get_interpolated(self,
                                     tag_id: str,
                                     start: int,
                                     finish: int,
                                     count: int,
                                     time_step: int) -> List[tuple]:
        """ Получение интерполированных значений с шагом time_step
        """
        tag_data = await self._data_get_many(tag_id,
            start or (finish - time_step * (count - 1)),
            finish, None
        )
        # Создание ряда таймстэмпов с шагом `time_step`
        time_row = self._timestep_row(time_step, count, start, finish)

        if not tag_data:
            return [(x, None, None) for x in time_row]

        return self._interpolate(tag_data, time_row)

    def _interpolate(self, raw_data: List[tuple], time_row: List[int]) -> List[tuple]:
        """ Получение линейно интерполированных значений для ряда ``time_row`` по
        действительным значениям из БД (``raw_data``)

        :param raw_data: Реальные значения из БД
        :type raw_data: List[Dict]

        :param time_row: Временной ряд, для которого надо рассчитать значения
        :type time_row: List[int]

        :return:
        :rtype: List[Dict]
        """

        # Разбиение списка ``raw_data`` на подсписки по значению None
        # Если ``raw_data`` не имеет None, получается список [raw_data]
        none_indexes = [idx for idx, val in enumerate(raw_data) if val[1] is None]
        size = len(raw_data)
        if none_indexes:
            splitted_by_none = [raw_data[i: j+1] for i, j in
                zip([0] + none_indexes, none_indexes +
                ([size] if none_indexes[-1] != size else []))]
        else:
            splitted_by_none = [raw_data]

        data = []  # Результирующий список
        for period in splitted_by_none:
            if len(period) == 1:
                continue

            key_x = lambda d: d[0]
            min_ts = min(period, key=key_x)[0]
            max_ts = max(period, key=key_x)[0]
            is_last_period = period == splitted_by_none[-1]

            # В каждый подсписок добавляются значения из ряда ``time_row``
            period = [(ts, None, None) \
                      for ts in time_row if min_ts <= ts < max_ts] + period
            period.sort(key=key_x)

            if not is_last_period:
                period.pop()

            # Расширенный подсписок заворачивается в DataFrame и индексируется по 'x'
            df = pd.DataFrame(
                period,
                index=[r[0] for r in period]
            ).drop_duplicates(subset=0, keep='last')

            # линейная интерполяция значений 'y' в датафрейме для числовых тэгов
            # заполнение NaN полей ближайшими не-NaN для нечисловых тэгов
            df[[0, 1]] = df[[0, 1]].interpolate(
                method=('pad', 'index')[is_numeric_dtype(df[1])]
            )

            # None-значения 'q' заполняются ближайшим не-None значением сверху
            df[2].fillna(method='ffill', inplace=True)

            # Удаление из датафрейма всех элементов, чьи 'x' не принадлежат ``time_row``
            df = df.loc[df[0].isin(time_row)]
            df[[1, 2]] = df[[1, 2]].replace({np.nan: None})

            # Преобразование получившегося датафрейма и добавление значений к
            # результирующему списку
            data += df.to_dict('split')['data']

        return data

    def _timestep_row(self,
                      time_step: int,
                      limit: int,
                      since: int,
                      till: int) -> List[int]:
        """ Возвращает временной ряд с шагом `time_step`

        :param time_step: Размер временного шага
        :type time_step: int
        :param limit: количество записей
        :type limit: int
        :param since: Точка начала отсчета
        :type since: int
        :param till: Точка окончания
        :type till: int

        :return: Ряд целых чисел длиной `limit` с шагом `time_step`
        :rtype: List[int]
        """

        if (since is None or till is None) and limit is None:
            raise AttributeError('Отсутствует параметр "count"')

        start_point = till
        time_step = -time_step
        if since is not None:
            start_point = since
            time_step = -time_step
            limit = min(
                int((till - since) / time_step) + 1,
                (limit, float('inf'))[limit is None]
            )

        row = []
        for i in range(0, limit):
            val = start_point + i * time_step
            if val < 0 or (till is not None and val > till):
                break
            row.append(val)

        if since is None:
            row.reverse()
        return row

    def _last_point(self, x: int, data: List[tuple]) -> Tuple[int, Any]:
        return (x, list(filter(lambda rec: rec[0] == x, data))[-1][1])

    async def _data_get_one(self,
                            tag_id: str,
                            finish: int) -> List[dict]:
        """ Получение значения на текущую метку времени
        """
        async with self._cache.get_redis() as r:
            tag_cache = await r.json().get(
                f"{tag_id}.{self._config.svc_name}", "prsStep", "prsValueTypeCode"
            )
        if tag_cache is None:
            self._logger.error(f"{self._config.svc_name} :: Тег {tag_id} отсутствует в кэше.")
            return []
        step = tag_cache["prsStep"]
        value_type_code = tag_cache["prsValueTypeCode"]

        tag_data = await self._read_data(
            tag_id=tag_id, start=None, finish=finish, count=1,
            one_before=False, one_after=not step, order=Order.CN_DESC
        )

        if not tag_data:
            if finish is not None:
                return [(finish, None, None)]

        x0 = tag_data[0][0]
        y0 = tag_data[0][1]
        try:
            x1, y1 = self._last_point(tag_data[1][0], tag_data)
            if not step:
                y = linear_interpolated(
                        (x0, y0), (x1, y1), finish
                    )
                if value_type_code == 0:
                    y = round(y)
                tag_data[0] = (tag_data[0][0], y, tag_data[0][2])

            # TODO: избавиться от этого try/except логикой приложения, т.к.
            # try/except отнимает слишком много времени

            tag_data.pop()

        except IndexError:
            # Если в выборке только одна запись и `to` меньше, чем `x` этой записи...
            if x0 > finish:
                tag_data[0] = (tag_data[0][0], None, None)
        finally:
            tag_data[0] = (finish, tag_data[0][1], tag_data[0][2])

        return tag_data

    async def _data_get_many(self,
                             tag_id: str,
                             start: int,
                             finish: int,
                             count: int = None) -> List[dict]:

        async with self._cache.get_redis() as r:
            tag_cache = await r.json().get(
                f"{tag_id}.{self._config.svc_name}", "prsStep"
            )
        if tag_cache is None:
            self._logger.error(f"{self._config.svc_name} :: Тег {tag_id} отсутствует в кэше.")
            return []
        step = tag_cache

        tag_data = await self._read_data(
            tag_id, start, finish,
            (Order.CN_DESC if count is not None and start is None else Order.CN_ASC),
            count, True, True, None
        )
        if not tag_data:
            return []

        x0 = tag_data[0][0]
        y0 = tag_data[0][1]

        if start is not None:
            if x0 > start:
                # Если `from_` раньше времени первой записи в выборке
                tag_data.insert(0, (start, None, None))

            if len(tag_data) == 1:
                if x0 < start:
                    tag_data[0] = (start, tag_data[0][1], tag_data[0][2])
                    tag_data.append((finish, y0, tag_data[0][2]))
                return tag_data

            x1, y1 = self._last_point(tag_data[1][0], tag_data)
            if x1 == start:
                # Если время второй записи равно `from`,
                # то запись "перед from" не нужна
                tag_data.pop(0)

            if x0 < start < x1:
                tag_data[0] = (start, tag_data[0][1], tag_data[0][2])
                if step:
                    tag_data[0] = (tag_data[0][0], y0, tag_data[0][2])
                else:
                    tag_data[0] = (tag_data[0][0], linear_interpolated((x0, y0), (x1, y1), start), tag_data[0][2])

        if finish is not None:
            # (xn; yn) - запись "после to"
            xn = tag_data[-1][0]
            yn = tag_data[-1][1]

            # (xn_1; yn_1) - запись перед значением `to`
            try:
                xn_1, yn_1 = self._last_point(tag_data[-2][0], tag_data)
            except IndexError:
                xn_1 = -1
                yn_1 = None

            if xn_1 == finish:
                # Если время предпоследней записи равно `to`,
                # то запись "после to" не нужна
                tag_data.pop()

            if xn_1 < finish < xn:
                if step:
                    y = yn_1
                else:
                    y = linear_interpolated(
                        (xn_1, yn_1), (xn, yn), finish
                    )
                tag_data[-1] = (finish, y, tag_data[-2][2])

            if finish > xn:
                tag_data.append((finish, yn, tag_data[-1][2]))

        #if all((finish is None, now_ms > tag_data[-1][1])):
        if finish > tag_data[-1][0]:
            tag_data.append((finish, tag_data[-1][1], tag_data[-1][2]))

        tag_data = self._limit_data(tag_data, count, start, finish)
        return tag_data

    async def _data_get_actual(self, tag_id: str, start: int, finish: int,
            count: int, value: Any = None):

        order = Order.CN_ASC
        if start is None:
            order = Order.CN_DESC
            count = (1, count)[bool(count)]

        raw_data = await self._read_data(
            tag_id, start, finish, order, count, False, False, value
        )

        return raw_data

    @abstractmethod
    async def _read_data(self, tag_id: str, start: int, finish: int,
        order: int, count: int, one_before: bool, one_after: bool, value: Any = None):

        pass

    def _limit_data(self,
                    tag_data: List[dict],
                    count: int,
                    start: int,
                    finish: int):
        """ Ограничение количества записей в выборке.
        Если задан параметр ``since``, возвращается ``limit`` первых записей списка.
        Если ``since`` не задан (None), но задан ``till``, возвращается
        ``limit`` последних записей списка

        :param tag_data: исходная выборка, массив словарей {'x': int, 'y': Any, 'q': int}
        :type tag_data: List[Dict]

        :param limit: количество записей в выборке
        :type limit: int

        :param since: нижняя граница выборки
        :type since: int

        :param till: верхняя граница выборки
        :type till: int
        """
        if not count:
            return tag_data
        if start:
            return tag_data[:count]
        if finish:
            return tag_data[-count:]
        return tag_data
