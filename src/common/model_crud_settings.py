"""
Модуль содержит класс-конфигурацию для сервиса, работающего с экземплярами
сущности в иерархии.
"""

from src.common.svc_settings import SvcSettings

class ModelCRUDSettings(SvcSettings):

    #: обменник, публикующий сообщения, на которые подписывается сервис
    api_crud_exchange: dict = {
        "name": "",
        "type": "direct",
        "queue_name": "",
        "routing_key": ""
    }

    #: параметры, связанные с работой с иерархией
    hierarchy: dict = {
        #: имя узла для хранения сущностей в иерархии
        #: пример: tags, objects, ...
        #: если узел не требуется, то пустая строка
        "node": "",
        #: класс экзмепляров сущности в
        #: пример: prsTag
        "class": "",
        #: список через запятую родительских классов
        "parent_classes": "",
        #: флаг создания узла ``cn=system`` внутри узла экземпляра сущности
        "create_sys_node": False
    }
