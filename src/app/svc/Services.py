import os
import copy
from logging import Logger
from typing import Dict, Any, List
from ldap3 import LEVEL, DEREF_NEVER
from app.svc.logger.PrsLogger import PrsLogger
import app.svc.ldap.ldap_db as ld
from app.svc.websockets.PrsWebsocketConnectionManager import PrsWebsocketConnectionManager
import app.times as t

class Services:
    default_base_node: str = 'cn=prs'

    logger: Logger
    ldap: ld.PrsLDAP
    ws_pool: PrsWebsocketConnectionManager

    config = {
        "LDAP_BASE_NODE": os.getenv("LDAP_BASE_NODE", default_base_node),
        "LDAP_TAGS_NODE": f"cn=tags,{os.getenv('LDAP_BASE_NODE', default_base_node)}",
        "LDAP_DATASTORAGES_NODE": f"cn=dataStorages,{os.getenv('LDAP_BASE_NODE', default_base_node)}",
        "LDAP_CONNECTORS_NODE": f"cn=connectors,{os.getenv('LDAP_BASE_NODE', default_base_node)}",
        "LDAP_OBJECTS_NODE": f"cn=objects,{os.getenv('LDAP_BASE_NODE', default_base_node)}",
    }

    """
    Datastorages cache:
    {
        "<ds_id>": <class PrsDataStorageEntry ..>
    }
    """
    data_storages: Dict[str, Any] = {}
    default_data_storage_id: str = None
    """
    Tags cache:
    {
        "<tag_id>": {
            "app": {
                "dataStorageId": "<ds_id>"
            }
            "data_storage": Any(some_value)
        }
    }
    Кэшем пользуется не только само приложение, но и разные сущности.
    То есть к ключу с id тэга сущности могут привязывать свои кэши.
    Для этого они вызывают метод set_tag_cache.
    Для получения нужного значения - get_tag_cache.
    Для удобства примем, что каждая сущность создаёт кэш с ключом, имя которого - похоже на имя сущности, а значение - любое нужное сущности.
    Приложение создаёт ключ "app", PrsDataStorageEntry создает ключ "data_storage"...

    """
    tags: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def set_ws_pool(cls):
        cls.ws_pool = PrsWebsocketConnectionManager()

    @classmethod
    def set_logger(cls):
        cls.logger = PrsLogger.make_logger()

    @classmethod
    def set_ldap(cls):
        cls.logger.debug(f'LDAP. host: {os.getenv("LDAP_HOST")}, port: {int(os.getenv("LDAP_PORT"))}, user: {os.getenv("LDAP_USER")}, pwd: {os.getenv("LDAP_PASSWORD")}')
        cls.ldap = ld.PrsLDAP(os.getenv("LDAP_HOST"), int(os.getenv("LDAP_PORT")), os.getenv("LDAP_USER"), os.getenv("LDAP_PASSWORD"))

    @classmethod
    def set_tag_cache(cls, tag: Any, key: str = None, value: Any = None):
        """
        Метод используется приложением и разными сущностями для формирования кэша тэгов.
        Методу передаётся PrsTagEntry, чтобы приложение могло сформировать свои кэши для тэга.
        Для того, чтобы при старте приложения не читать два раза все тэги, формируя кэш тэгов в приложении
        и кэши тэгов в хранилищах данных, общий для всех кэш тэгов в приложении формируется при старте приложения
        во время считывания хранилищ данных: они вызывают этот метод, что приводит к формированию кэша тэгов.
        """
        cls.tags.setdefault(tag.id, {"app": {"dataStorageId": tag.data.dataStorageId}})
        if key:
            cls.tags[tag.id][key] = value

    @classmethod
    def get_tag_cache(cls, tag_id: str, key: str) -> Any:
        if cls.tags.get(tag_id) is not None:
            return copy.deepcopy(cls.tags[tag_id].get(key))
        else:
            return None

    @classmethod
    def format_data(cls, data: List[Dict], format_: bool | str = False) -> None:
        if not format_:
            return

        for item in data:
            item['x'] = t.int_to_local_timestamp(item['x'])
