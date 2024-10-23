from src.common.model_crud_settings import ModelCRUDSettings

class ConnectorsModelCRUDSettings(ModelCRUDSettings):
    #: имя сервиса
    svc_name: str = "connectors_model_crud"
    hierarchy: dict = {
        #: имя узла для хранения сущностей в иерархии
        #: если узел не требуется, то пустая строка
        "node": "connectors",
        #: класс экзмепляров сущности в иерархии
        "class": "prsConnector",
        #: список через запятую родительских классов
        "parent_classes": "",
        #: флаг создания узла ``cn=system`` внутри узла экземпляра сущности
        "create_sys_node": True
    }
