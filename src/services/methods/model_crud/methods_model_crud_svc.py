import sys
import copy

sys.path.append(".")

from src.common import model_crud_svc
from src.common import hierarchy
from src.common import model_copy
from src.services.methods.model_crud.methods_model_crud_settings import MethodsModelCRUDSettings

class MethodsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с методами в иерархии.

    Формат ожидаемых сообщений

    """

    def __init__(self, settings: MethodsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_handlers(self):
        super()._set_handlers()
        self._handlers["prsMethod.api_crud.copy"] = self._copy_method
        self._add_app_handlers()

    async def _copy_method(self, mes: dict, routing_key: str | None = None) -> dict:
        source_id = mes.get("sourceId")
        parent_id = mes.get("parentId")
        if not source_id or not parent_id:
            return {"error": {"code": 422, "message": "Должны быть заданы sourceId и parentId."}}
        return await model_copy.copy_single_method(
            self._hierarchy,
            self._post_message,
            source_id=source_id,
            new_parent_id=parent_id,
            subtree_ids=frozenset(),
            id_map={},
        )

    def _add_app_handlers(self):
        self._handlers["prsTag.model.deleted.*"] = self._delete_initiator
        self._handlers["prsSchedule.model.deleted.*"] = self._delete_initiator

    async def _delete_initiator(self, mes: dict, routing_key: str):
        deleted_id = mes['id']
        obj_class = routing_key.split('.')[0]

        # отпишемся от событий инициатора
        await self._amqp_consume_queue.unbind(
            exchange=self._exchange,
            routing_key=f"{obj_class}.model.deleted.{deleted_id}"
        )

        # сообщим методам, что инициатор удалился, чтобы они могли отписаться от событий...
        async with self._cache.get_redis() as r:
            initiator_cache = await r.json().get(f"{deleted_id}.{self._config.svc_name}")

            if initiator_cache is None:
                self._logger.error(f"{self._config.svc_name} :: Нет кэша для удалённого инициатора {deleted_id}.")
                return
            # удалим кэш
            await r.json().delete(f"{deleted_id}.{self._config.svc_name}")

        for method_id in initiator_cache:
            payload = {
                "base": method_id,
                "filter": {"cn": deleted_id},
                "attributes": ["cn"]
            }
            initiator = await self._hierarchy.search(payload=payload)
            if initiator:
                await self._hierarchy.delete(initiator[0][0])
                await self._post_message(
                    mes={"id": method_id},
                    routing_key=f"{self._config.hierarchy['class']}.model.updated.{method_id}"
                )
            else:
                self._logger.error(f"{self._config.svc_name} :: Нет данных по инициатору '{deleted_id}' для метода '{method_id}'.")

    async def _make_method_cache(self, method_id: str):
        """Создаёт кэш метода для всех его инициаторов."""
        initiators = await self._get_method_initiators(method_id)

        if not initiators:
            return

        async with self._cache.get_redis() as r:
            for initiator_id, initiator_data in initiators:
                obj_class = initiator_data["objectClass"][0]

                # если есть кэш для этого инициатора, добавляем метод
                # если нет, создаём
                initiator_cache = await r.json().get(f"{initiator_id}.{self._config.svc_name}")
                if initiator_cache is None:
                    await r.json().set(
                        name=f"{initiator_id}.{self._config.svc_name}",
                        path="$",
                        obj=[method_id]
                    )
                else:
                    # если path=$, то возвращается массив
                    # если элемент не найден, то первый элемент массива = -1
                    index = await r.json().arrindex(
                        f"{initiator_id}.{self._config.svc_name}", "$", method_id  # type: ignore[arg-type]
                    )

                    if index[0] == -1:
                        await r.json().arrappend(
                            f"{initiator_id}.{self._config.svc_name}", "$", method_id
                        )

                # подписываемся на событие удаления инициатора
                await self._amqp_consume_queue.bind(
                    exchange=self._exchange,
                    routing_key=f"{obj_class}.model.deleted.{initiator_id}"
                )

    async def _get_method_initiators(self, method_id: str) -> list[tuple[str, dict]]:
        """Получает список инициаторов для метода.

        Returns:
            list[tuple[str, dict]]: Список кортежей (initiator_id, initiator_data)
        """
        payload = {
            "base": method_id,
            "filter": {"cn": ["initiatedBy"]},
            "attributes": ["cn"]
        }
        initiatedBy_result = await self._hierarchy.search(payload=payload)

        if not initiatedBy_result:
            self._logger.warning(
                f"{self._config.svc_name} :: Не найден узел 'initiatedBy' для метода '{method_id}'."
            )
            return []

        initiatedBy_id = initiatedBy_result[0][0]
        payload = {
            "base": initiatedBy_id,
            "scope": hierarchy.CN_SCOPE_ONELEVEL,
            "filter": {"cn": ["*"]},
            "attributes": ["cn"]
        }
        initiators = await self._hierarchy.search(payload=payload)

        result = []
        for initiator in initiators:
            initiator_id = initiator[2]["cn"][0]
            payload = {"id": initiator_id, "attributes": ["objectClass"]}
            initiator_data = await self._hierarchy.search(payload=payload)
            if initiator_data:
                result.append((initiator_id, initiator_data[0][2]))

        return result

    async def _remove_method_from_initiator_cache(
        self, r, initiator_id: str, method_id: str, obj_class: str
    ) -> bool:
        """Удаляет метод из кэша инициатора и очищает кэш, если он пуст.

        Returns:
            bool: True если кэш был удалён, False иначе
        """
        initiator_cache = await r.json().get(f"{initiator_id}.{self._config.svc_name}")

        if not initiator_cache or initiator_cache[0] is None:
            return False

        index = 0
        try:
            index = initiator_cache.index(method_id)
        except ValueError:
            return False

        await r.json().arrpop(
            f"{initiator_id}.{self._config.svc_name}", "$", index
        )

        # Проверяем, остались ли ещё методы в кэше
        updated_cache = await r.json().get(f"{initiator_id}.{self._config.svc_name}")
        if not updated_cache or not updated_cache[0]:
            # Кэш пуст, удаляем его и отписываемся от событий
            await self._amqp_consume_queue.unbind(
                exchange=self._exchange,
                routing_key=f"{obj_class}.model.deleted.{initiator_id}"
            )
            await r.json().delete(f"{initiator_id}.{self._config.svc_name}")
            return True

        return False

    async def _delete_method_cache(self, ids: str | list[str]):
        """Удаляет метод(ы) из кэша инициаторов.

        Args:
            ids: ID метода или список ID методов
        """
        method_ids = [ids] if isinstance(ids, str) else ids

        async with self._cache.get_redis() as r:
            for method_id in method_ids:
                initiators = await self._get_method_initiators(method_id)

                for initiator_id, initiator_data in initiators:
                    obj_class = initiator_data["objectClass"][0]
                    await self._remove_method_from_initiator_cache(
                        r, initiator_id, method_id, obj_class
                    )

    async def _further_create(self, mes: dict, new_id: str) -> None:
        system_node = await self._hierarchy.search(payload={
            "base": new_id,
            "scope": hierarchy.CN_SCOPE_ONELEVEL,
            "filter": {
                "cn": ["system"]
            },
            "attributes": ["cn"]
        })
        if not system_node:
            self._logger.error(f"{self._config.svc_name} :: В методе {new_id} отсутствует узел 'system'.")
            return

        system_node_id = system_node[0][0]

        # создадим список инициаторов расчёта
        initiatedBy_node_id = await self._hierarchy.add(
            system_node_id,
            {"cn": ["initiatedBy"]}
        )

        parent_node_id, _ = await self._hierarchy.get_parent(new_id)
        initiators = mes.get("initiatedBy")
        if (initiators is not None):
            if (parent_node_id in initiators):
                res = {
                    "id": None,
                    "error": {
                        "code": 400,
                        "message": "ParentId не может быть в списке 'initiatedBy'."
                    }
                }

                return res

            for initiator_id in mes["initiatedBy"]:
                await self._hierarchy.add(
                    initiatedBy_node_id,
                    {"cn": [initiator_id]}
                )

        # создадим узлы-параметры
        parameters_node_id = await self._hierarchy.add(
            system_node_id,
            {"cn": ["parameters"]}
        )
        if mes.get("parameters"):
            for parameter in mes["parameters"]:
                parameter["attributes"]["objectClass"] = ["prsMethodParameter"]
                await self._hierarchy.add(
                    parameters_node_id,
                    parameter["attributes"]
                )

        payload = {
            "id": new_id,
            "attributes": ["prsActive"]
        }
        method_active = await self._hierarchy.search(payload=payload)
        if method_active[0][2]["prsActive"][0] == 'TRUE':
            await self._make_method_cache(new_id)

    async def _further_read(self, mes: dict, search_result: dict) -> dict:
        # добавим в результат параметры и initiatedBy
        new_result = {
            "data": []
        }

        for method_item in search_result["data"]:
            new_method_item = copy.deepcopy(method_item)
            new_method_item["initiatedBy"] = []
            new_method_item["parameters"] = []

            # TODO: переработать, т.к. получать DN, потом составлять новый - плохая практика
            method_dn = await self._hierarchy.get_node_dn(new_method_item["id"])

            # ищем инициаторов
            initiated_by_node_dn = f"cn=initiatedBy,cn=system,{method_dn}"
            payload = {
                "base": initiated_by_node_dn,
                "scope": 1,
                "filter": {"cn": ["*"]},
                "attributes": ["cn"]
            }
            initiators = await self._hierarchy.search(payload)
            for initiator in initiators:
                new_method_item["initiatedBy"].append(initiator[2]["cn"][0])

            # ищем параметры
            parameters_node_dn = f"cn=parameters,cn=system,{method_dn}"
            payload = {
                "base": parameters_node_dn,
                "scope": 1,
                "filter": {"objectClass": ["prsMethodParameter"]},
                "attributes": ["cn", "description", "prsActive", "prsIndex", "prsJsonConfigString"]
            }
            parameters = await self._hierarchy.search(payload)
            for parameter in parameters:
                new_method_item["parameters"].append({
                    "attributes": parameter[2]
                })

            new_result["data"].append(new_method_item)
        return new_result

    async def _further_update(self, mes: dict) -> None:
        if "initiatedBy" in mes.keys():
            await self._delete_method_cache(mes['id'])
            # просто переделаем весь список инициаторов
            initiatedBy_node = await self._hierarchy.search(
                payload={"base": mes['id'], "filter": {"cn": ["initiatedBy"]}, "attributes": ["cn"]}
            )
            if not initiatedBy_node:
                self._logger.error(f"{self._config.svc_name} :: Не найден узел 'initiatedBy' для метода '{mes['id']}'.")
                return
            await self._hierarchy.delete(initiatedBy_node[0][0])

        if "parameters" in mes.keys():
            parameters_node = await self._hierarchy.search(payload={
                "base": mes["id"],
                "scope": hierarchy.CN_SCOPE_SUBTREE,
                "filter": {
                    "cn": ["parameters"]
                },
                "attributes": ["cn"]
            })
            if parameters_node:
                parameters_node_id = parameters_node[0][0]
                await self._hierarchy.delete(parameters_node_id)

        await self._further_create(mes, mes["id"])

    async def _get_methods(self):
        payload = {
            "filter": {"objectClass": ["prsMethod"], "prsActive": ["TRUE"]},
            "attributes": ["cn"]
        }
        methods = await self._hierarchy.search(payload=payload)
        for method in methods:
            await self._make_method_cache(method[0])

    async def _delete(self, mes: dict, routing_key: str = None) -> None:
        await self._delete_method_cache(mes['id'])
        await super()._delete(mes)

    async def on_startup(self) -> None:
        await super().on_startup()

        await self._amqp_consume_queue.unbind(self._exchange, "prsTag.model.deleted.*")
        await self._amqp_consume_queue.unbind(self._exchange, "prsSchedule.model.deleted.*")
        try:
            await self._get_methods()
        except Exception as ex:
            self._logger.error(f"{self._config.svc_name} :: {ex}")

settings = MethodsModelCRUDSettings()

app = MethodsModelCRUD(settings=settings, title="TagsModelCRUD")
