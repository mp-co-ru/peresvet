"""
Модуль содержит классы, описывающие входные данные для команд CRUD для тегов
<<<<<<< HEAD
и класс сервиса ``tags_api_crud_svc``\.
=======
и класс сервиса ``tags_api_crud_svc``.
>>>>>>> peresvet/dev
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
<<<<<<< HEAD

class TagsApp(AppSvc):
    """Сервис работы с тегами.
    
=======
from src.common.times import ts

class TagsApp(AppSvc):
    """Сервис работы с тегами.

>>>>>>> peresvet/dev
    Формат ожидаемых сообщений

    """

    def __init__(self, settings: TagsAppSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _add_app_handlers(self):
        self._handlers[f"{self._config.hierarchy['class']}.app_api.data_get.*"] = self.data_get
        self._handlers[f"{self._config.hierarchy['class']}.app_api.data_set.*"] = self.data_set

<<<<<<< HEAD
    async def data_get(self, mes: dict, routing_key: str = None) -> dict:
        
=======
    async def data_get(self, mes: dict, routing_key: str | None = None) -> dict:

>>>>>>> peresvet/dev
        self._logger.debug(f"{self._config.svc_name} :: Data get mes: {mes}")

        new_payload = copy.deepcopy(mes)
        tag_ids = new_payload.pop("tagId")
        final_res = {
            "data": []
        }
        for tag_id in tag_ids:

            res = await self._get_tag_cache_key_value(tag_id, "prsActive")
<<<<<<< HEAD
            if not res:
                self._logger.error(f"{self._config.svc_name} :: Нет тега c id = '{tag_id}'.")
                continue
            if not res[0]:
=======
            if res is None:
                self._logger.error(f"{self._config.svc_name} :: Нет тега c id = '{tag_id}'.")
                continue
            if not res:
>>>>>>> peresvet/dev
                self._logger.warning(f"{self._config.svc_name} :: Тег '{tag_id}' неактивен.")
                continue

            new_payload["tagId"] = [tag_id]

            res = await self._post_message(new_payload, reply=True, routing_key=f"{self._config.hierarchy['class']}.app.data_get.{tag_id}")
            if res is None:
                self._logger.error(f"{self._config.svc_name} :: Нет обработчика для получения данных тега '{tag_id}'.")
            else:
                final_res["data"] += res["data"]

        return final_res

    async def _get_tag_cache_key_value(self, tag_id: str, key: str):
<<<<<<< HEAD
        # результат возврщаем в виде массива
        # если возвращаем False, это означает, что такого тега нет
        try:
            res = await self._cache.get(f"{tag_id}.{self._config.svc_name}", key).exec()
        except:
            # сам кэш есть, но нет такого ключа
            res = [None]
        
        if res[0] is None:
            res = await self._make_tag_cache(tag_id)
            # если метод перестроения кэша возвращает False - значит, нет такого узла
            if not res:
                return False
            
            res = await self._cache.get(f"{tag_id}.{self._config.svc_name}", key).exec()

        if res[0] == 'null':
            res = [None]
        
        return res

    async def data_set(self, mes: dict, routing_key: str = None) -> None:

=======
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

    async def data_set(self, mes: dict, routing_key: str | None = None) -> None:

        now_ts = ts()
>>>>>>> peresvet/dev
        for tag_item in mes["data"]:
            tag_id = tag_item['tagId']

            self._logger.debug(f"{self._config.svc_name} :: Запись данных тега '{tag_id}'")

            res = await self._get_tag_cache_key_value(tag_id, "prsActive")
<<<<<<< HEAD
            if not res:
                self._logger.error(f"{self._config.svc_name} :: Нет тега c id = '{tag_id}'.")
                continue
            if not res[0]:
                self._logger.warning(f"{self._config.svc_name} :: Тег '{tag_id}' неактивен.")
                continue
            
=======
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
            for data_item in tag_item["data"]:
                data_item_len = len(data_item)

>>>>>>> peresvet/dev
            res = await self._post_message({"data": [tag_item]}, reply=False,
                routing_key=f"{self._config.hierarchy['class']}.app.data_set.{tag_item['tagId']}"
            )
            if res is None:
                self._logger.error(f"{self._config.svc_name} :: Нет обработчика для записи данных тега '{tag_item['tagId']}'.")

    async def _delete_tag_cache(self, tag_id: str):
<<<<<<< HEAD
        await self._cache.delete(f"{tag_id}.{self._config.svc_name}").exec()
=======
        async with self._cache.get_redis() as r:
            await r.json().delete(f"{tag_id}.{self._config.svc_name}")
>>>>>>> peresvet/dev

    async def _make_tag_cache(self, tag_id: str):
        await self._delete_tag_cache(tag_id=tag_id)

        res = await self._hierarchy.search({
            "id": tag_id,
            "attributes": ["prsActive"]
        })
        if not res:
            return False
<<<<<<< HEAD
        
        active = res[0][2]["prsActive"][0] == 'TRUE'
        res = await self._cache.set(name=f"{tag_id}.{self._config.svc_name}", obj={"prsActive": active}).exec()
        return res[0]
=======

        active = res[0][2]["prsActive"][0] == 'TRUE'
        async with self._cache.get_redis() as r:
            res = await r.json().set(name=f"{tag_id}.{self._config.svc_name}", path="$", obj={"prsActive": active})
        return res
>>>>>>> peresvet/dev

    async def _updated(self, mes: dict, routing_key: str = None):
        # просто удалим кэш тега
        # при попытке чтения/записи данных кэш будет создан
        await self._delete_tag_cache(mes["id"])
<<<<<<< HEAD
    
=======

>>>>>>> peresvet/dev
    async def _deleted(self, mes: dict, routing_key: str = None):
        await self._delete_tag_cache(mes["id"])

settings = TagsAppSettings()

app = TagsApp(settings=settings, title="`TagsApp` service")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
