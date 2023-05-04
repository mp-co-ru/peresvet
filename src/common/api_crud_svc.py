from uuid import UUID
from pydantic import BaseModel, Field, validator, List

class NodeCreateAttributes(BaseModel):
    """Атрибуты для создания базового узла.
    """
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
            "Исли используется в команде создания узла, то в случае "
            "отсутствия экзмепляр создаётся в базовом для данной "
            "сущности узле. "
            "При использовании в команде изменения узла трактуется как новый "
            "родительский узел."
        ))
    attributes: NodeCreateAttributes = Field(NodeCreateAttributes(),
        title="Атрибуты узла"
    )

    @classmethod
    @validator('parentId', check_fields=False)
    def parentId_must_be_uuid_or_none(cls, v):
        if v is not None:
            try:
                UUID(v)
            except ValueError as ex:
                raise ValueError('parentId должен быть в виде uuid') from ex
        return v

class NodeDelete(BaseModel):
    id: str = Field(title="Идентификатор узла.",
        description=(
            "Идентификатор удаляемого(изменяемого) узла "
            "должен быть в виде uuid."
        )
    )

    @classmethod
    @validator('id')
    def id_must_be_uuid(cls, v):
        try:
            UUID(v)
        except ValueError as ex:
            raise ValueError('id должен быть в виде uuid') from ex
        return v

class NodeUpdate(NodeCreate, NodeDelete):
    pass
