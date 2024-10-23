from src.common.model_crud_settings import ModelCRUDSettings

class MethodsModelCRUDSettings(ModelCRUDSettings):
    #: имя сервиса
    svc_name: str = "methods_model_crud"
    
    hierarchy: dict = {
        #: имя узла для хранения сущностей в иерархии
        #: если узел не требуется, то пустая строка
        "node": "",
        #: класс экзмепляров сущности в иерархии
        "class": "prsMethod",
        #: список через запятую родительских классов
        "parent_classes": "prsTag,prsAlert",
        #: флаг создания узла ``cn=system`` внутри узла экземпляра сущности
        "create_sys_node": True
    }    