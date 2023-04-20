# базовый класс для управления экземплярами сущностей в иерархии
# по умолчанию, каждая сущность может иметь "свой" узел в иерархрии
# для создания в нём "своей" иерархии; но это необязательно
from typing import Annotated

from fastapi import Depends, FastAPI

from settings import Settings

class BaseModelCRUD(FastAPI):

    def __init__(self, **kwargs):
        super(BaseModelCRUD, self).__init__(**kwargs)
        svc.set_logger()
        svc.set_ldap()
        svc.set_ws_pool()
