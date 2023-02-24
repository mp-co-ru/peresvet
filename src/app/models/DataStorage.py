import asyncio
from typing import List, Union, Dict
import json

from urllib.parse import urlparse
from pydantic import validator, Field, root_validator
from ldap3 import LEVEL, DEREF_SEARCH, ALL_ATTRIBUTES
from fastapi import Response

from app.svc.Services import Services as svc
from app.models.ModelNode import PrsModelNodeCreateAttrs, PrsModelNodeEntry, PrsModelNodeCreate
from app.models.Tag import PrsTagEntry
from app.const import CNDataStorageTypes
from app.models.Data import PrsReqGetData
import app.times as t

class PrsDataStorageCreateAttrs(PrsModelNodeCreateAttrs):
    """
    Атрибуты сущности `dataStorage`.
    Используются при создании/изменении/получении хранилищ данных.
    """
    prsEntityTypeCode: int = Field(0, title='Код типа сущности',
        description=(
            '- 0 - PostgreSQL\n'
            '- 1 - Victoriametrics'
        )
    )

    prsDefault: bool = Field(False, title='Флаг хранилища данных по умолчанию',
        description=(
            'Каждое вновь добавляемое хранилище данных становится '
            'хранилищем по умолчанию. '
        )
    )

    prsJsonConfigString: Dict | str | None = Field({
            "dsn": "postgres://postgres:postgres@localhost:5432/postgres"
        }, title="Строка с json-конфигурацией.",
        description=(
            'Атрибут может содержать строку с json-конфигурацией для сущности. Подробней - в документации на каждую сущность.'
        ))

    @root_validator
    # этот валидатор должен быть в классах конкретных хранилищ
    @classmethod
    def check_config(cls, values):

        def uri_validator(x):
            result = urlparse(x)
            return all([result.scheme, result.netloc])

        type_code = values.get('prsEntityTypeCode')
        config = values.get('prsJsonConfigString')

        if not config:
            raise ValueError((
                "Должна присутствовать конфигурация хранилища данных (атрибут prsJsonConfigString)."
            ))
            #TODO: методы класса создаются при импорте, поэтому jsonConfigString = None
            # и возникает ошибка

        if isinstance(config, str):
            config = json.loads(config)

        if type_code == 1:
            put_url = config.get('putUrl')
            get_url = config.get('getUrl')

            if uri_validator(put_url) and uri_validator(get_url):
                return values

            raise ValueError((
                "Конфигурация (атрибут prsJsonConfigString) для Victoriametrics должна быть вида:\n"
                "{'putUrl': 'http://<server>:<port>/api/put', 'getUrl': 'http://<server>:<port>/api/v1/export'}"
            ))
        elif type_code == 0:
            dsn = config["dsn"]
            if uri_validator(dsn):
                return values
            raise ValueError((
                "Конфигурация (атрибут prsJsonConfigString) для PostgreSQL должна быть вида:\n"
                "{'dsn': 'postgres://<user>:<password>@<host>:<port>/<database>?<option>=<value>'"
            ))

        raise ValueError((
            "Неизвестный тип хранилища данных."
        ))

#TODO: Валидацию переносить в класс Prs...Create!!!

class PrsDataStorageCreate(PrsModelNodeCreate):
    """Request /tags/ POST"""
    attributes: PrsDataStorageCreateAttrs = Field(PrsDataStorageCreateAttrs(),
        title=(
            'Атрибуты хранилища данных'
        )
    )

    @validator('parentId', check_fields=False, always=True)
    @classmethod
    def parentId_must_be_none(cls, v):
        if v is not None:
            raise ValueError('parentId must be null for dataStorage')
        return v

class PrsDataStorageEntry(PrsModelNodeEntry):
    '''Базовый класс для всех хранилищ'''
    objectClass: str = 'prsDataStorage'
    payload_class = PrsDataStorageCreate
    default_parent_dn: str = svc.config["LDAP_DATASTORAGES_NODE"]

    @classmethod
    async def create(cls, *args, **kwargs):
        inst = cls(*args, **kwargs)
        await inst._post_init()
        return inst

    async def _post_init(self):
        await self._read_tags()

    def __init__(self, **kwargs):
        super(PrsDataStorageEntry, self).__init__(**kwargs)

        self.tags_node = f"cn=tags,{self.dn}"
        self.alerts_node = f"cn=alerts,{self.dn}"

    def _format_tag_cache(self, tag: PrsTagEntry) -> None | str | Dict:
        # метод возращает данные, которые будут использоваться в качестве
        # кэша для тэга
        return json.loads(tag.data.attributes.prsStore)

    def _format_tag_data_store(self, tag: PrsTagEntry) -> None | Dict:
        # метод возвращает место хранения тэга внутри хранилища

        res = tag.data.attributes.prsStore
        if res is not None:
            try:
                res = json.loads(tag.data.attributes.prsStore)
            except json.JSONDecodeError as _:
                pass

        return res

    async def _read_tags(self):

        result, _, response, _ = svc.ldap.get_read_conn().search(
            search_base=self.tags_node,
            search_filter='(cn=*)', search_scope=LEVEL,
            dereference_aliases=DEREF_SEARCH,
            attributes=[ALL_ATTRIBUTES, 'entryUUID'])
        if not result:
            svc.logger.info(f"Нет привязанных тэгов к хранилищу '{self.data.attributes.cn}'")
            return

        for item in response:
            tag_entry = PrsTagEntry(id=str(item['attributes']['entryUUID']))

            svc.set_tag_cache(tag_entry, "data_storage", self._format_tag_cache(tag_entry))

        svc.logger.info(f"Тэги, привязанные к хранилищу `{self.data.attributes.cn}`, прочитаны.")

    async def connect(self):
        pass

    async def data_set(self, data):
        pass

    async def data_get(self, data: PrsReqGetData) -> Response:
        pass

    def _add_subnodes(self) -> None:
        data = PrsModelNodeCreate(attributes={
            "cn": "tags"
        })
        data.parentId = self.id
        PrsModelNodeEntry(data=data)

        data.attributes.cn = 'alerts'
        PrsModelNodeEntry(data=data)

    async def create_tag_store(self, tag: PrsTagEntry):
        # метод вызывается при создании тега
        pass

    async def reg_tags(self, tags: PrsTagEntry | str | List[str] | List[PrsTagEntry]):
        # метод регистрирует в хранилище новые тэги

        if isinstance(tags, (str, PrsTagEntry)):
            tags = [tags]

        for tag in tags:
            if isinstance(tag, str):
                tag_entry = PrsTagEntry(id=tag)
            else:
                tag_entry = tag
            svc.ldap.add_alias(parent_dn=self.tags_node, aliased_dn=tag_entry.dn, name=tag_entry.id)

            tag_store = self._format_tag_data_store(tag_entry)
            if (tag_entry.data.attributes.prsStore is None) or (not tag_store == tag_entry.data.attributes.prsStore):
                tag_entry.modify({
                    "prsStore": json.dumps(tag_store)
                })

            await self.create_tag_store(tag_entry)

            tag_cache = self._format_tag_cache(tag_entry)
            svc.set_tag_cache(tag_entry, "data_storage", tag_cache)
