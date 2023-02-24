import json
import copy
from typing import Dict, Union

import aiohttp
from fastapi import Response

from pydantic import validator, root_validator
from urllib.parse import urlparse

from app.models.DataStorage import PrsDataStorageEntry, PrsDataStorageCreate
from app.models.Tag import PrsTagEntry
from app.svc.Services import Services as svc

'''
class PrsVictoriametricsCreate(PrsDataStorageCreate):

    @root_validator
    # этот валидатор должен быть в классах конкретных хранилищ
    @classmethod
    def check_config(cls, values):

        def uri_validator(x):
            result = urlparse(x)
            return all([result.scheme, result.netloc])

        attrs = values.get('attributes')
        if not attrs:
            raise ValueError((
                "При создании хранилища необходимо задать атрибуты."
            ))

        config = attrs.get('prsJsonConfigString')

        if not config:
            raise ValueError((
                "Должна присутствовать конфигурация (атрибут prsJsonConfigString)."
            ))
            #TODO: методы класса создаются при импорте, поэтому jsonConfigString = None
            # и возникает ошибка

        if isinstance(config, str):
            config = json.loads(config)

        put_url = config.get['putUrl']
        get_url = config.get['getUrl']

        if uri_validator(put_url) and uri_validator(get_url):
            return values

        raise ValueError((
            "Конфигурация (атрибут prsJsonConfigString) для Victoriametrics должна быть вида:\n"
            "{'putUrl': 'http://<server>:<port>/api/put', 'getUrl': 'http://<server>:<port>/api/v1/export'}"
        ))
'''

class PrsVictoriametricsEntry(PrsDataStorageEntry):

    def __init__(self, **kwargs):
        super(PrsVictoriametricsEntry, self).__init__(**kwargs)

        if isinstance(self.data.attributes.prsJsonConfigString, dict):
            js_config = self.data.attributes.prsJsonConfigString
        else:
            js_config = json.loads(self.data.attributes.prsJsonConfigString)
        self.put_url = js_config['putUrl']
        self.get_url = js_config['getUrl']

        #self.session = None
        self.session = aiohttp.ClientSession()

    def _format_tag_data_store(self, tag: PrsTagEntry) -> None | Dict:
        if tag.data.attributes.prsStore:
            data_store = json.loads(tag.data.attributes.prsStore)
        else:
            data_store = {}
        if data_store.get('metric') is None:
            data_store['metric'] = (tag.data.attributes.cn, tag.data.attributes.cn[0])[isinstance(tag.data.attributes.cn, list)] # cn is array of str!

            # имя метрики не может начинаться с цифр и не может содержать дефисов
            if tag.id == data_store['metric']:
                data_store['metric'] = f"t_{data_store['metric'].replace('-', '_')}"

        return data_store

    async def connect(self) -> int:
        #if self.session is None:
        #    self.session = aiohttp.ClientSession()
        async with self.session.get(f"{self.get_url}?match[]=vm_free_disk_space_bytes") as response:
            return response.status

    async def data_set(self, data):
        # data:
        # {
        #        "<tag_id>": [(x, y, q)]
        # }
        #
        # method forms archive:
        # [
        #     {
        #         "metric": "sys.cpu.nice",
        #         "timestamp": 1346846400,
        #         "value": 18,
        #         "tags": {
        #            "host": "web01",
        #            "dc": "lga"
        #         }
        #     },
        #     {
        #         "metric": "sys.cpu.nice",
        #         "timestamp": 1346846400,
        #         "value": 9,
        #         "tags": {
        #            "host": "web02",
        #            "dc": "lga"
        #         }
        #     }
        # ]

        formatted_data = []
        for key, item in data.items():
            # формат prsStore у тэга:
            #
            #   {
            #        "metric": "metric_name",
            #        "tags": {
            #            "t1": "v1",
            #            "t2": "v2"
            #        }
            #    }
            tag_metric = svc.get_tag_cache(key, "data_storage")
            for data_item in item:
                x, y, _ = data_item
                tag_metric['value'] = y
                tag_metric['timestamp'] = round(x / 1000)
                formatted_data.append(copy.deepcopy(tag_metric))

        resp = await self.session.post(self.put_url, json=formatted_data)

        svc.logger.debug(f"Set data status: {resp.status}")

        return Response(status_code=resp.status)
