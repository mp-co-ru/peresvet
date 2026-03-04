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
from src.services.tags.app.tags_app_settings import TagsAppSettings
from src.common.times import ts
from src.common.tag_data_points import normalize_point_xyq

class TagsApp(AppSvc):
    """Сервис работы с тегами.

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: TagsAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

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

    async def data_set(self, mes: dict, routing_key: str | None = None) -> dict:
        common_payload = {}
        for key, value in mes.items():
            if key != "data":
                common_payload[key] = value

        for tag_item in mes["data"]:
            tag_id = tag_item['tagId']

            self._logger.debug(f"{self._config.svc_name} :: Запись данных тега '{tag_id}'")

            res = await self._get_tag_cache_key_value(tag_id, "prsActive")
            if res is None:
                self._logger.error(f"{self._config.svc_name} :: Нет тега c id = '{tag_id}'.")
                continue
            if not res:
                self._logger.warning(f"{self._config.svc_name} :: Тег '{tag_id}' неактивен.")
                continue

            # проверим количество элементов в каждом массиве
            new_tag_item = {
                "tagId": tag_id,
                "data": []
            }
            tag_params = tag_item.get("params") if isinstance(tag_item.get("params"), dict) else None
            if tag_params:
                new_tag_item["params"] = tag_params

            for data_item in tag_item["data"]:
                p = normalize_point_xyq(data_item)
                if isinstance(p, tuple) and len(p) == 3:
                    x, y, q = p
                    new_tag_item["data"].append((x, y, q))
                else:
                    # оставим как есть, чтобы downstream сервисы могли вернуть ошибку/лог
                    new_tag_item["data"].append(data_item)

            payload = dict(common_payload)
            # For data_set, params are per-tag (`data[i].params`).
            # Top-level params are intentionally ignored.
            payload.pop("params", None)
            if tag_params:
                payload["params"] = dict(tag_params)
            payload["data"] = [new_tag_item]

            res = await self._post_message(payload, reply=True,
                routing_key=f"{self._config.hierarchy['class']}.app.data_set.{tag_item['tagId']}"
            )
            if res is None:
                self._logger.error(f"{self._config.svc_name} :: Нет обработчика для записи данных тега '{tag_item['tagId']}'.")
                return {"error": {"code": 424, "message": f"Нет обработчика для записи данных тега '{tag_item['tagId']}'."}}
            if isinstance(res, dict) and res.get("error"):
                return res
        return {}

    async def _delete_tag_cache(self, tag_id: str):
        async with self._cache.get_redis() as r:
            await r.json().delete(f"{tag_id}.{self._config.svc_name}")

    async def _make_tag_cache(self, tag_id: str):
        await self._delete_tag_cache(tag_id=tag_id)

        res = await self._hierarchy.search({
            "id": tag_id,
            "attributes": ["prsActive"]
        })
        if not res:
            return False

        active = res[0][2]["prsActive"][0] == 'TRUE'
        async with self._cache.get_redis() as r:
            res = await r.json().set(name=f"{tag_id}.{self._config.svc_name}", path="$", obj={"prsActive": active})
        return res

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
