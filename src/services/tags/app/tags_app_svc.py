"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
и класс сервиса ``tags_api_crud_svc``.
"""
import sys
import copy

try:
    import uvicorn
except ModuleNotFoundError as _:
    pass

sys.path.append(".")

from src.common.app_svc import AppSvc
from src.common.consts import CNTagValueTypes as TVT
from src.services.tags.app.tags_app_settings import TagsAppSettings
from src.common.tag_data_points import coerce_tag_data_items_for_data_set, normalize_point_xyq
from src.common.json_rpc_sanitize import to_redis_json_scalar
from src.common.tag_max_line_dev import (
    filter_data_points_for_storage,
    parse_prs_max_line_dev_from_ldap_attrs,
)

class TagsApp(AppSvc):
    """Сервис работы с тегами.

    Формат ожидаемых сообщений

    """

    def _add_app_handlers(self):
        self._handlers[f"{self._config.hierarchy['class']}.app_api.data_get.*"] = self.data_get
        self._handlers[f"{self._config.hierarchy['class']}.app_api.data_set.*"] = self.data_set

    async def data_get(self, mes: dict, routing_key: str | None = None) -> dict:

        self._logger.debug(f"{self._config.svc_name} :: Data get mes: {mes}")

        new_payload = copy.deepcopy(mes)
        tag_ids = new_payload.pop("tagId")
        final_res = {
            "data": []
        }
        for tag_id in tag_ids:

            res = await self._get_tag_cache_key_value(tag_id, "prsActive")
            if res is None:
                self._logger.error(f"{self._config.svc_name} :: Нет тега c id = '{tag_id}'.")
                continue
            if not res:
                self._logger.warning(f"{self._config.svc_name} :: Тег '{tag_id}' неактивен.")
                continue

            new_payload["tagId"] = [tag_id]

            res = await self._post_message(new_payload, reply=True, routing_key=f"{self._config.hierarchy['class']}.app.data_get.{tag_id}")
            if res is None:
                self._logger.error(f"{self._config.svc_name} :: Нет обработчика для получения данных тега '{tag_id}'.")
            elif isinstance(res, dict) and res.get("error"):
                return res
            else:
                final_res["data"] += res["data"]

        return final_res

    async def _get_tag_cache_key_value(self, tag_id: str, key: str):
        # если возвращаем False, это означает, что такого тега нет

        # TODO: неправильно! если тега нет, надо возвращать None
        # т.к. False может быть значением тега
        async with self._cache.get_redis() as r:
            try:
                res = await r.json().get(f"{tag_id}.{self._config.svc_name}", key)
            except:
                # сам кэш есть, но нет такого ключа
                res = None

            if res is None:
                res = await self._make_tag_cache(tag_id)
                # если метод перестроения кэша возвращает False - значит, нет такого узла
                if not res:
                    return None

                res = await r.json().get(f"{tag_id}.{self._config.svc_name}", key)

            if res == 'null':
                res = None

            return res

    @staticmethod
    def _unwrap_redis_json_root(val):
        if isinstance(val, list) and len(val) == 1:
            return val[0]
        return val

    async def _ensure_tag_data_set_cache(self, tag_id: str) -> dict | None:
        """Полный кэш тега в Redis для ``data_set``: активность, тип, prsMaxLineDev, последнее принятое y/q."""
        key = f"{tag_id}.{self._config.svc_name}"
        async with self._cache.get_redis() as r:
            try:
                doc = await r.json().get(key, "$")
            except Exception:
                doc = None
        doc = self._unwrap_redis_json_root(doc)
        if isinstance(doc, dict):
            need_refresh = (
                "prsValueTypeCode" not in doc
                or "prsMaxLineDev" not in doc
                or "prsLastAcceptedQ" not in doc
            )
        else:
            need_refresh = True
        if not need_refresh:
            return doc

        last_y = doc.get("prsLastAcceptedY") if isinstance(doc, dict) else None
        last_q = doc.get("prsLastAcceptedQ") if isinstance(doc, dict) else None
        hres = await self._hierarchy.search(
            {
                "id": tag_id,
                "attributes": ["prsActive", "prsValueTypeCode", "prsMaxLineDev"],
            }
        )
        if not hres:
            return None
        attrs = hres[0][2]
        new_doc = {
            "prsActive": attrs["prsActive"][0] == "TRUE",
            "prsValueTypeCode": int(attrs["prsValueTypeCode"][0]),
            "prsMaxLineDev": parse_prs_max_line_dev_from_ldap_attrs(attrs),
            "prsLastAcceptedY": last_y,
            "prsLastAcceptedQ": last_q,
        }
        async with self._cache.get_redis() as r:
            await r.json().set(name=key, path="$", obj=new_doc)
        return new_doc

    async def data_set(self, mes: dict, routing_key: str | None = None) -> dict:
        common_payload = {}
        result_items: list[dict] = []
        for key, value in mes.items():
            if key != "data":
                common_payload[key] = value

        for tag_item in mes["data"]:
            tag_id = tag_item['tagId']

            self._logger.debug(f"{self._config.svc_name} :: Запись данных тега '{tag_id}'")

            tag_proc = await self._ensure_tag_data_set_cache(tag_id)
            if tag_proc is None:
                self._logger.error(f"{self._config.svc_name} :: Нет тега c id = '{tag_id}'.")
                continue
            if not tag_proc["prsActive"]:
                self._logger.warning(f"{self._config.svc_name} :: Тег '{tag_id}' неактивен.")
                continue

            normalized_data: list = []
            for data_item in coerce_tag_data_items_for_data_set(tag_item.get("data")):
                p = normalize_point_xyq(data_item)
                if isinstance(p, tuple) and len(p) == 3:
                    x, y, q = p
                    normalized_data.append((x, y, q))
                else:
                    normalized_data.append(data_item)

            vt = int(tag_proc["prsValueTypeCode"])
            max_dev = float(tag_proc.get("prsMaxLineDev") or 0)
            prev_y = tag_proc.get("prsLastAcceptedY")
            prev_q = tag_proc.get("prsLastAcceptedQ")

            tag_params = tag_item.get("params") if isinstance(tag_item.get("params"), dict) else None
            # Табличный (интеграционный) тег: при пустом ``data`` всё равно одна логическая запись
            # (операция по умолчанию в хранилище). Параметры — в ``data[i].params``; у HTTP POST
            # ``/v1/data/`` на корне тела только ``data`` (см. ``AllData``). Доп. ключи на корне
            # ``mes`` возможны у других издателей в шину — тогда они попадут в ``common_payload``.
            params_only_set = vt == int(TVT.CN_TABLE) and not normalized_data
            if params_only_set:
                accepted = [normalize_point_xyq([])]
                new_last_y, new_last_q = prev_y, prev_q
            else:
                accepted, new_last_y, new_last_q = filter_data_points_for_storage(
                    normalized_data, vt, max_dev, prev_y, prev_q
                )
            if not accepted:
                self._logger.debug(
                    f"{self._config.svc_name} :: Тег '{tag_id}': все точки отсеяны правилами записи (prsMaxLineDev / качество / тип)."
                )
                continue

            new_tag_item = {
                "tagId": tag_id,
                "data": accepted,
            }
            if tag_params:
                new_tag_item["params"] = tag_params

            payload = dict(common_payload)
            top_level_params = payload.pop("params", None)
            merged_rpc_params: dict = {}
            if isinstance(top_level_params, dict):
                merged_rpc_params.update(top_level_params)
            if tag_params:
                merged_rpc_params.update(tag_params)
            if merged_rpc_params:
                payload["params"] = merged_rpc_params
            payload["data"] = [new_tag_item]

            res = await self._post_message(payload, reply=True,
                routing_key=f"{self._config.hierarchy['class']}.app.data_set.{tag_item['tagId']}"
            )
            if res is None:
                self._logger.error(f"{self._config.svc_name} :: Нет обработчика для записи данных тега '{tag_item['tagId']}'.")
                return {"error": {"code": 424, "message": f"Нет обработчика для записи данных тега '{tag_item['tagId']}'."}}
            if isinstance(res, dict) and res.get("error"):
                return res
            if isinstance(res, dict) and not res.get("error"):
                async with self._cache.get_redis() as r:
                    rk = f"{tag_id}.{self._config.svc_name}"
                    await r.json().set(
                        rk,
                        "$.prsLastAcceptedY",
                        to_redis_json_scalar(new_last_y),
                    )
                    await r.json().set(
                        rk,
                        "$.prsLastAcceptedQ",
                        to_redis_json_scalar(new_last_q),
                    )
            if isinstance(res, dict):
                returned = res.get("data")
                # Тело с ``data`` нужно только для табличных (интеграционных) тегов —
                # там хранилище может вернуть идентификатор новой строки. Остальные типы:
                # успех без тела (``{}``) или ``error``.
                if vt == int(TVT.CN_TABLE) and isinstance(returned, list) and returned:
                    result_items.extend(returned)
        if result_items:
            return {"data": result_items}
        return {}

    async def _delete_tag_cache(self, tag_id: str):
        async with self._cache.get_redis() as r:
            await r.json().delete(f"{tag_id}.{self._config.svc_name}")

    async def _make_tag_cache(self, tag_id: str):
        await self._delete_tag_cache(tag_id=tag_id)

        res = await self._hierarchy.search(
            {
                "id": tag_id,
                "attributes": ["prsActive", "prsValueTypeCode", "prsMaxLineDev"],
            }
        )
        if not res:
            return False

        attrs = res[0][2]
        active = attrs["prsActive"][0] == "TRUE"
        doc = {
            "prsActive": active,
            "prsValueTypeCode": int(attrs["prsValueTypeCode"][0]),
            "prsMaxLineDev": parse_prs_max_line_dev_from_ldap_attrs(attrs),
            "prsLastAcceptedY": None,
            "prsLastAcceptedQ": None,
        }
        async with self._cache.get_redis() as r:
            res = await r.json().set(
                name=f"{tag_id}.{self._config.svc_name}", path="$", obj=doc
            )
        return res

    async def on_startup(self) -> None:
        await super().on_startup()

    async def on_shutdown(self) -> None:
        await super().on_shutdown()

    async def _updated(self, mes: dict, routing_key: str = None):
        # просто удалим кэш тега
        # при попытке чтения/записи данных кэш будет создан
        await self._delete_tag_cache(mes["id"])
    async def _deleted(self, mes: dict, routing_key: str = None):
        await self._delete_tag_cache(mes["id"])

settings = TagsAppSettings()

app = TagsApp(settings=settings, title="`TagsApp` service")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
