from typing import Dict, Any, List
import asyncio
from copy import deepcopy

from fastapi import FastAPI, HTTPException, Response
from ldap3 import BASE, DEREF_ALWAYS, DEREF_NEVER, SUBTREE, LEVEL

from app.svc.Services import Services as svc
from app.models.Tag import PrsTagEntry, PrsTagCreate
from app.models.DataStorage import PrsDataStorageEntry, PrsDataStorageCreate
from app.models.data_storages.vm import PrsVictoriametricsEntry
from app.models.data_storages.psql import PrsPostgreSQLEntry
from app.models.Data import PrsReqGetData, PrsReqSetData
from app.models.Connector import PrsConnectorCreate, PrsConnectorEntry
import app.times as times
from app.const import CNDataStorageTypes as CN_DS_T
from app.const import CNHTTPExceptionCodes as HEC

class PrsApplication(FastAPI):

    # list of attributes returned to connector
    connector_attrs: List[str] = [
        "prsSource", "prsValueTypeCode", "prsMaxDev", "prsValueScale"
    ]

    def __init__(self, **kwargs):
        super(PrsApplication, self).__init__(**kwargs)
        svc.set_logger()
        svc.set_ldap()
        svc.set_ws_pool()

    def _reg_data_storage_in_cache(self, ds: PrsDataStorageEntry):
        """
        Метод, заносящий в кэш хранилище данных.
        Вызывается при создании нового хранилища и при старте приложения.
        """
        svc.data_storages[ds.id] = ds
        if ds.data.attributes.prsDefault:
            svc.default_data_storage_id = ds.id

    async def set_data_storages(self):
        svc.logger.info("Start load datastorages...")

        found, _, res, _ = svc.ldap.get_read_conn().search(
            search_base=svc.config["LDAP_DATASTORAGES_NODE"],
            search_filter='(cn=*)', search_scope=LEVEL, dereference_aliases=DEREF_NEVER,
            attributes=['entryUUID', 'prsEntityTypeCode', 'prsDefault'])

        svc.logger.info(f"datastorages: {res}")

        if found:
            for item in res:
                attrs = dict(item['attributes'])
                ds_uuid = attrs['entryUUID']
                if attrs['prsEntityTypeCode'] == CN_DS_T.CN_DS_VICTORIAMETRICS:
                    new_ds = await PrsVictoriametricsEntry.create(id=ds_uuid)
                elif attrs['prsEntityTypeCode'] == CN_DS_T.CN_DS_POSTGRESQL:
                    new_ds = await PrsPostgreSQLEntry.create(id=ds_uuid)
                else:
                    svc.logger.info("Unsupported type of data storage {ds_uuid}.")
                    continue

                self._reg_data_storage_in_cache(new_ds)

        if svc.data_storages:
            if svc.default_data_storage_id is None:
                svc.default_data_storage_id = list(svc.data_storages.keys())[0]

        svc.logger.info("Хранилища данных загружены.")

    async def create_tag(self, payload: PrsTagCreate) -> PrsTagEntry:
        if not svc.data_storages:
            svc.logger.info("Невозможно создать тэг без зарегистрированных хранилищ данных.")
            raise HTTPException(HEC.CN_424, detail="Перед созданием тэга необходимо зарегистрировать хотя бы одно хранилище данных.")

        if payload.dataStorageId is None:
            payload.dataStorageId = svc.default_data_storage_id
        new_tag = PrsTagEntry(payload)

        await svc.data_storages[payload.dataStorageId].reg_tags(new_tag)

        if payload.connectorId is not None:
            connector = PrsConnectorEntry(id=payload.connectorId)
            await connector.reg_tags(new_tag)

        svc.logger.info(f"Тэг '{new_tag.data.attributes.cn}'({new_tag.id}) создан.")

        return new_tag

    async def create_dataStorage(self, payload: PrsDataStorageCreate) -> PrsDataStorageEntry:
        # если вновь создаваемое хранилище - хранилище по умолчанию,
        # то предыдущее хранилище по умолчанию нужно сделать обычным
        if payload.attributes.prsDefault:
            if svc.default_data_storage_id:
                svc.data_storages[svc.default_data_storage_id].modify({"prsDefault": False})

        # если хранилищ ещё нет, то первое создаваемое будет
        # хранилищем по умолчанию в любом случае
        if not svc.data_storages:
            if not payload.attributes.prsDefault:
                payload.attributes.prsDefault = True

        if payload.attributes.prsEntityTypeCode == CN_DS_T.CN_DS_VICTORIAMETRICS:
            new_ds = await PrsVictoriametricsEntry.create(data=payload)
        elif payload.attributes.prsEntityTypeCode == CN_DS_T.CN_DS_POSTGRESQL:
            new_ds = await PrsPostgreSQLEntry.create(data=payload)
        else:
            raise HTTPException(HEC.CN_422, detail="Поддерживается создание только зарегистрированных типов хранилищ.")

        self._reg_data_storage_in_cache(new_ds)

        svc.logger.info(f"Хранилище данных '{new_ds.data.attributes.cn}'({new_ds.id}) создано.")

        return new_ds

    async def read_dataStorage(self, id: str) -> PrsDataStorageEntry:
        ds = await PrsDataStorageEntry.create(id=id)
        return ds

    def read_tag(self, id: str) -> PrsTagEntry:
        return PrsTagEntry(id=id)

    def get_node_id_by_dn(self, dn: str) -> str:
        found, _, res, _ = svc.ldap.get_read_conn().search(
            search_base=dn, search_filter='(cn=*)', search_scope=BASE, dereference_aliases=DEREF_NEVER, attributes='entryUUID')
        if found:
            return res[0]['attributes']['entryUUID']
        else:
            return None

    def get_node_dn_by_id(self, id: str) -> str:
        found, _, res, _ = svc.ldap.get_read_conn().search(
            search_base=svc.config["LDAP_BASE_NODE"],
            search_filter=f"(entryUUID={id})",
            search_scope=SUBTREE,
            dereference_aliases=False,
            attributes='cn'
        )

        return res[0]['dn'] if found else None

    async def data_get(self, data: PrsReqGetData) -> dict:
        """
        Метод создаёт копии запроса для каждого хранилища данных,
        при этом в каждой копии сохраняются только те тэги, которые привязаны
        к данном хранилищу.
        Потом запросы на получение данных передаются параллельно всем
        хранилищам.
        """

        data_storages = {}
        tags = deepcopy(data.tagId)
        for tag_id in tags:
            data_storage_id = svc.tags[tag_id]['app']["dataStorageId"]
            if data_storages.get(data_storage_id) is None:
                data_storages[data_storage_id] = deepcopy(data)
                data_storages[data_storage_id].tagId = [tag_id]
            else:
                data_storages[data_storage_id].tagId.append(tag_id)

        tasks = [asyncio.create_task(
            svc.data_storages[key].data_get(value)) for key, value in data_storages.items()
        ]
        done, _ = await asyncio.wait(tasks)
        res = {
            "data": []
        }
        for task in done:
            value = task.result()
            res["data"].extend(value["data"])

        return res

    async def data_set(self, data: PrsReqSetData) -> Response:
        """
        Метод разбивает массив данных на несколько массивов: один массив - одно хранилище и раздаёт эти массивы на запись
        соответствующим хранилищам. Также создаёт метки времени, если их нет и конвертирует их в микросекунды.
        """
        now_ts = times.ts()
        # словарь значений для записи в разных хранилищах
        # имеет вид:
        # {
        #   "<data_storage_id>": {
        #        "<tag_id>": [(x, y, q)]
        #   }
        # }
        data_storages = {}
        for tag_item in data.data:
            data_storage_id = svc.tags[tag_item.tagId]['app']["dataStorageId"]
            if data_storages.get(data_storage_id) is None:
                data_storages[data_storage_id] = {}
            data_storages[data_storage_id].setdefault(tag_item.tagId, [])

            for data_item in tag_item.data:
                if data_item.x is None:
                    x = now_ts
                else:
                    x = times.ts(data_item.x)
                data_storages[data_storage_id][tag_item.tagId].append((x, data_item.y, data_item.q))

        tasks = [asyncio.create_task(
            svc.data_storages[key].data_set(value)) for key, value in data_storages.items()
        ]
        done, _ = await asyncio.wait(tasks)
        #TODO: подумать, как возвращать результат
        for task in done:
            value = task.result().status_code
            if value >= 400:
                return Response(status_code=value)

        return Response(status_code=204)

    def create_connector(self, payload: PrsConnectorCreate) -> PrsConnectorEntry:
        new_connector = PrsConnectorEntry(data=payload)
        svc.logger.info(f"Коннектор '{new_connector.data.attributes.cn}'({new_connector.id}) создан.")

        return new_connector

    def read_connector(self, id: str) -> PrsConnectorEntry:
        return PrsConnectorEntry(id=id)

    def response_to_connector(self, conn_id: str):
        conn = PrsConnectorEntry(id=conn_id)
        result = {
            "attributes": conn.data.attributes.dict(),
            "tags": []
        }
        tags = conn.read_tags()
        for tag in tags['tags']:
            tag_dict = {
                "id": tag.id,
                "attributes": {}
            }
            attrs = tag.data.attributes.dict()
            for attr in PrsApplication.connector_attrs:
                tag_dict["attributes"][attr] = attrs[attr]
            result['tags'].append(tag_dict)

        return result
