from src.common.model_crud_settings import ModelCRUDSettings

class TagsModelCRUDSettings(ModelCRUDSettings):
    #: имя сервиса
    svc_name: str = "tags_model_crud"
    
    hierarchy: dict = {
        #: имя узла для хранения сущностей в иерархии
        #: если узел не требуется, то пустая строка
        "node": "tags",
        #: класс экзмепляров сущности в иерархии
        "class": "prsTag",
        #: список через запятую родительских классов
        "parent_classes": "prsObject",
        #: флаг создания узла ``cn=system`` внутри узла экземпляра сущности
        "create_sys_node": True
    }
