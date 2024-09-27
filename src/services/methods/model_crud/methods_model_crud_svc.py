import sys
import copy

sys.path.append(".")

from src.common import model_crud_svc
from src.common import hierarchy
from src.services.methods.model_crud.methods_model_crud_settings import MethodsModelCRUDSettings

class MethodsModelCRUD(model_crud_svc.ModelCRUDSvc):
    """Сервис работы с тегами в иерархии.

    Подписывается на очередь ``tags_api_crud`` обменника ``tags_api_crud``\,
    в которую публикует сообщения сервис ``tags_api_crud`` (все имена
    указываются в переменных окружения).

    Формат ожидаемых сообщений

    """

    _outgoing_commands = {
        "created": "methods.created",
        "mayUpdate": "methods.mayUpdate",
        "updating": "methods.updating",
        "updated": "methods.updated",
        "mayDelete": "methods.mayDelete",
        "deleting": "methods.deleting",
        "deleted": "methods.deleted"
    }

    def __init__(self, settings: MethodsModelCRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

    def _set_incoming_commands(self) -> dict:
        return {
            "methods.create": self._create,
            "methods.read": self._read,
            "methods.update": self._update,
            "methods.delete": self._delete,
        }
    
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
            self._logger.error(f"В методе {new_id} отсутствует узел `system`.")
            return

        system_node_id = system_node[0][0]

        # создадим список инициаторов расчёта
        initiatedBy_node_id = await self._hierarchy.add(
            system_node_id,
            {"cn": ["initiatedBy"]}
        )

        mes_data = mes["data"]
        parent_node = mes_data["parentId"]
        initiators = mes_data.get("initiatedBy")
        if (initiators is not None):
            if (parent_node in initiators):
                res = {
                    "id": None,
                    "error": {
                        "code": 400,
                        "message": "ParentId не может быть в списке 'initiatedBy'."
                    }
                }

                return res


        if mes["data"].get("initiatedBy"):
            for initiator_id in mes["data"]["initiatedBy"]:
                await self._hierarchy.add(
                    initiatedBy_node_id,
                    {"cn": [initiator_id]}
                )
        # создадим узлы-параметры
        parameters_node_id = await self._hierarchy.add(
            system_node_id,
            {"cn": ["parameters"]}
        )
        if mes["data"].get("parameters"):
            for parameter in mes["data"]["parameters"]:
                parameter["attributes"]["objectClass"] = ["prsMethodParameter"]
                await self._hierarchy.add(
                    parameters_node_id,
                    parameter["attributes"]
                )

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
        if (not ("initiatedBy" in mes["data"].keys()) and
            not ("parameters" in mes["data"].keys())):
            return
        
        if "initiatedBy" in mes["data"].keys():
            initiatedBy_node = await self._hierarchy.search(payload={
                "base": mes["data"]["id"],
                "scope": hierarchy.CN_SCOPE_SUBTREE,
                "filter": {
                    "cn": ["initiatedBy"]
                },
                "attributes": ["cn"]
            })
            if initiatedBy_node:
                initiatedBy_node_id = initiatedBy_node[0][0]
                await self._hierarchy.delete(initiatedBy_node_id)

        if "parameters" in mes["data"].keys():
            parameters_node = await self._hierarchy.search(payload={
                "base": mes["data"]["id"],
                "scope": hierarchy.CN_SCOPE_SUBTREE,
                "filter": {
                    "cn": ["parameters"]
                },
                "attributes": ["cn"]
            })
            if parameters_node:
                parameters_node_id = parameters_node[0][0]
                await self._hierarchy.delete(parameters_node_id)

        await self._further_create(mes, mes["data"]["id"])

settings = MethodsModelCRUDSettings()

app = MethodsModelCRUD(settings=settings, title="TagsModelCRUD")
