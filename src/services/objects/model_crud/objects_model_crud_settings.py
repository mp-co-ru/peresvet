from src.common.model_crud_settings import ModelCRUDSettings

class ObjectsModelCRUDSettings(ModelCRUDSettings):
    #: имя сервиса
    svc_name: str = "objects_model_crud"
    
    hierarchy: dict = {
        #: имя узла для хранения сущностей в иерархии
        #: если узел не требуется, то пустая строка
        "node": "objects",
        #: класс экзмепляров сущности в иерархии
        "class": "prsObject",
        #: список через запятую родительских классов
        "parent_classes": "prsObject",
        #: флаг создания узла ``cn=system`` внутри узла экземпляра сущности
        "create_sys_node": True
    }
