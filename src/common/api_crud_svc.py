"""
Модуль содержит классы, описывающие форматы входных данных для команд,
а также класс APICRUDSvc - базовый класс для всех сервисов
<сущность>_api_crud.
"""
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, validator

from src.common.base_svc import BaseSvc
from src.common.api_crud_settings import APICRUDSettings

def valid_uuid(id: str | list[str]) -> str | list[str]:
    """Валидатор идентификаторов.
    Идентификатор должен быть в виде GUID.
    """
    if id is not None:
        try:
            if isinstance(id, str):
                UUID(id)
            else:
                for item in id:
                    UUID(item)
        except ValueError as ex:
            raise ValueError('id должен быть в виде GUID') from ex
    return id


class NodeAttributes(BaseModel):
    """Атрибуты для создания базового узла.
    """
    cn: str = Field(None, title="Имя узла")
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
    attributes: NodeAttributes = Field({}, title="Атрибуты узла")

    validate_id = validator('parentId', allow_reuse=True)(valid_uuid)

class NodeDelete(BaseModel):
    """Базовый класс, описывающий параметры
    команды для удаления узла.
    """
    id: str | list[str] = Field(title="Идентификатор(-ы) узла.",
        description=(
            "Идентификатор(-ы) удаляемого(изменяемого) узла "
            "должен быть в виде uuid."
        )
    )

    validate_id = validator('id', allow_reuse=True)(valid_uuid)

    @validator('id')
    @classmethod
    def make_id_as_array(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [v]
        return v

class NodeUpdate(NodeCreate):
    """Базовый класс для изменения узла
    """
    id: str = Field(title="Идентификатор изменяемого узла.",
                    description="Должен быть в формате GUID.")

    validate_id = validator('parentId', 'id', allow_reuse=True)(valid_uuid)

class NodeRead(BaseModel):
    """Базовый класс, описывающий параметры для команды
    поиска/чтения узлов.
    """

    id: str | list[str] = Field(
        None,
        title="Идентификатор(-ы) узлов.",
        description=(
            "Если уазан(-ы), то возвращаются данные по указанному(-ым) "
            "узлам. В этом случае ключи `base`, `scope`, `filter` "
            "не принимаются во внимание."
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
    attributes: list[str] = Field(
        ['*'],
        title="Список атрибутов.",
        description=(
            "Список атрибутов, значения которых необходимо вернуть "
            "в ответе. По умолчанию - ['*'], то есть все атрибуты "
            "(кроме системных)."
        )
    )

    validate_id = validator('id', 'base', allow_reuse=True)(valid_uuid)

class NodeCreateResult(BaseModel):
    """Результат выполнения команды создания узла.
    """
    id: str

class OneNodeInReadResult(BaseModel):
    id: str = Field(title="Id узла.")
    attributes: dict = Field(title="Атрибуты узла")

class NodeReadResult(BaseModel):
    data: list[OneNodeInReadResult] = Field(title="Список узлов")

class APICRUDSvc(BaseSvc):

    # так как сообщения, создаваемые сервисами каждой сущности
    # начинаются с имени этой сущности, то
    # каждый сервис-наследник класса APICRUDSvc должен
    # определить "свои" CRUD-сообщения в этом словаре
    # к примеру, для сервиса TagsAPICRUDSvc:
    # {
    #   "create": "tags.create",
    #   "read": "tags.read",
    #   "update": "tags.update",
    #   "delete": "tags.delete"
    # }
    _outgoing_commands = {
        "create": "create",
        "read": "read",
        "update": "update",
        "delete": "delete"
    }

    def __init__(self, settings: APICRUDSettings, *args, **kwargs):
        super().__init__(settings, *args, **kwargs)

        self.api_version = settings.api_version

    async def create(self, payload: NodeCreate) -> dict:
        body = {
            "action": self._outgoing_commands["create"],
            "data": payload.model_dump()
        }

        return await self._post_message(mes=body, reply=True)

    async def update(self, payload: NodeUpdate) -> dict:
        body = {
            "action": self._outgoing_commands["update"],
            "data": payload.model_dump()
        }

        return await self._post_message(mes=body, reply=False)

    async def read(self, payload: NodeRead) -> dict:
        body = {
            "action": self._outgoing_commands["read"],
            "data": payload.model_dump()
        }

        return await self._post_message(mes=body, reply=True)

    async def delete(self, payload: NodeDelete) -> dict:
        body = {
            "action": self._outgoing_commands["delete"],
            "data": payload.model_dump()
        }

        return await self._post_message(mes=body, reply=False)
