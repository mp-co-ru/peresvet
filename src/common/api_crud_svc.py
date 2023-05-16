"""Модуль не содержит класса APICRUDSvc, так как все необходимые методы
реализованы в рамках базового класса :py:class:`svc.Svc`.

Модуль содержит классы, описывающие форматы входных данных для команд.
"""
import asyncio
import json
from typing import Annotated, List
from collections.abc import MutableMapping
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, validator
from aio_pika import Message
import aio_pika.abc
from fastapi import Depends

from svc import Svc
from settings import Settings

class NodeCreateAttributes(BaseModel):
    """Атрибуты для создания базового узла.
    """
    cn: str = Field(title="Имя узла")
    description: str = Field(None, title="Описание",
        description="Описание экземпляра.")
    prsJsonConfigString: str = Field(None, title="Конфигурация экземпляра.",
        description=(
            "Строка содержит, в случае необходимости, конфигурацию узла. "
            "Интерпретируется сервисом, управляющим сущностью, которой "
            "принадлежит экземпляр."
        ))
    prsActive: bool = Field(True, title="Флаг активности.",
        description=(
            "Определяет, активен ли экземпляр. Применяется, к примеру, "
            "для временного 'выключения' экземпляра на время, пока он ещё "
            "недонастроен."
        )
    )
    prsDefault: bool = Field(None, title="Сущность по умолчанию.",
        description=(
            "Если = ``True``, то данный экземпляр считается узлом по умолчанию "
            "в списке равноправных узлов данного уровня иерархии."
        )
    )
    prsEntityTypeCode: int = Field(None, title="Тип узла.",
        description=(
            "Атрибут используется для определения типа. К примеру, "
            "хранилища данных могут быть разных типов."
        )
    )
    prsIndex: int = Field(None, title="Индекс узла.",
        description=(
            "Если у узлов одного уровня иерархии проставлены индексы, то "
            "перед отдачей клиенту списка экземпляров они сортируются "
            "в соответствии с их индексами."
        )
    )

class NodeCreate(BaseModel):
    """Базовый класс для команды создания экземпляра сущности.
    """
    parentId: str = Field(None, title="Id родительского узла",
        description=(
            "Идентификатор родительского узла. "
            "Если используется в команде создания узла, то в случае "
            "отсутствия экзмепляр создаётся в базовом для данной "
            "сущности узле. "
            "При использовании в команде изменения узла трактуется как новый "
            "родительский узел."
        ))
    attributes: NodeCreateAttributes = Field(title="Атрибуты узла")

    @classmethod
    @validator('parentId', check_fields=False)
    def parentId_must_be_uuid_or_none(cls, v):
        if v is not None:
            try:
                UUID(v)
            except ValueError as ex:
                raise ValueError(f'parentId {v} должен быть в виде GUID') from ex
        return v

class NodeDelete(BaseModel):
    id: str | List[str] = Field(title="Идентификатор узла.",
        description=(
            "Идентификатор(-ы) удаляемого(изменяемого) узла "
            "должен быть в виде uuid."
        )
    )

    @classmethod
    @validator('id')
    def id_must_be_uuid(cls, v):
        try:
            values = []
            if isinstance(v, str):
                values.append(v)
            else:
                values = v

            for val in values:
                UUID(val)
        except ValueError as ex:
            raise ValueError(f'Id узла {val} должен быть в виде GUID') from ex
        return values

class NodeUpdate(NodeCreate):
    """Базовый класс для изменения узла
    """
    id: str = Field(title="Идентификатор изменяемого узла.",
                    description="Должен быть в формате GUID.")

    @classmethod
    @validator('id')
    def id_must_be_uuid(cls, v):
        try:
            values = []
            if isinstance(v, str):
                values.append(v)
            else:
                values = v

            for val in values:
                UUID(val)
        except ValueError as ex:
            raise ValueError(f'Id узла {val} должен быть в виде GUID') from ex
        return values

class NodeRead(BaseModel):
    id: str | List[str] = Field(
        None,
        title="Идентификатор(-ы) узлов.",
        description=(
            "Если уазан(-ы), то возвращаются данные по указанному(-ым) "
            "узлам. В этом случае ключи `scope`, `filter` не принимаются во "
            "внимание."
        )
    )
    base: str = Field(
        None,
        title="Базовый узел для поиска.",
        description="Если не указан, то поиск ведётся от главного узла иерархии."
    )
    deref: bool = Field(
        True,
        title="Флаг разыменования ссылок.",
        description="По умолчанию = true."
    )
    scope: int = Field(
        2,
        title="Масштаб поиска.",
        description=(
            "0 - получение данных по указанному в ключе `base` узлу;"
            "1 - поиск среди непосредственных потомков указанного в `base` узла;"
            "2 - поиск по всему дереву, начиная с указанного в `base` узла."
        )
    )
    filter: dict = Field(
         None,
         title=(
            "Словарь из атрибутов и их значений, из "
            "которых формируется фильтр для поиска."
         ),
         description=(
            "Значения одного атрибута объединяются логической операцией `ИЛИ`, "
            "затем значения для разных атрибутов объединяются операцией `И`."
         )
    )
    attributes: List[str] = Field(
        ["*"],
        title="Список атрибутов.",
        description=(
            "Список атрибутов, значения которых необходимо вернуть "
            "в ответе. По умолчанию - ['*'], то есть все атрибуты "
            "(кроме системных)."
        )
    )

class APICRUDSvc(Svc):

    _callback_queue: aio_pika.abc.AbstractRobustQueue

    def __init__(self, settings: Settings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

        self._callback_futures: MutableMapping[str, asyncio.Future] = {}


    async def _amqp_connect(self) -> None:
        await super()._amqp_connect()

        self._callback_queue = await self._amqp_channel.declare_queue(
            durable=True, exclusive=True
        )
        self._callback_queue.bind(
            exchange=self._pub_exchange,
            routing_key=self._callback_queue.name
        )

        await self._callback_queue.consume(self._on_rpc_response, no_ack=True)

    async def _on_rpc_response(
            self, message: aio_pika.abc.AbstractIncomingMessage
    ) -> None:
        if message.correlation_id is None:
            self._logger.error("У сообщения не выставлен параметр `correlation_id`")
            return
        future: asyncio.Future = self._callback_futures.pop(message.correlation_id, None)
        future.set_result(json.loads(message.body.decode()))

    async def _post_message(self, mes: dict, reply: bool = False) -> dict | None:
        body = json.dumps(mes, ensure_ascii=False).encode()
        if reply:
            correlation_id = str(uuid4())
            reply_to = self._callback_queue.name
            future = asyncio.get_running_loop().create_future()
            self._callback_futures[correlation_id] = future

        await self._pub_exchange.publish(
            message=Message(
                body=body, correlation_id=correlation_id, reply_to=reply_to
            )
        )
        if not reply:
            return

        return await future

    async def create(self, payload: NodeCreate) -> dict:
        body = {
            "action": "create",
            "data": payload.dict()
        }

        return await self._post_message(mes=body, reply=True)

    async def update(self, payload: NodeUpdate) -> dict:
        body = {
            "action": "update",
            "data": payload.dict()
        }

        return await self._post_message(mes=body, reply=False)

    async def read(self, payload: NodeRead) -> dict:
        body = {
            "action": "read",
            "data": payload.dict()
        }

        return await self._post_message(mes=body, reply=True)

    async def delete(self, payload: NodeDelete) -> dict:
        body = {
            "action": "delete",
            "data": payload.dict()
        }

        return await self._post_message(mes=body, reply=False)
