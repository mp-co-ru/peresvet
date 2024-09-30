from src.common.model_crud_settings import ModelCRUDSettings

class AlertsModelCRUDSettings(ModelCRUDSettings):
    #: имя сервиса
    svc_name: str = "alerts_model_crud"
    
    hierarchy: dict = {
        #: имя узла для хранения сущностей в иерархии
        #: если узел не требуется, то пустая строка
        "node": "",
        #: класс экзмепляров сущности в иерархии
        "class": "prsAlert",
        #: список через запятую родительских классов
        "parent_classes": "prsTag",
        #: флаг создания узла ``cn=system`` внутри узла экземпляра сущности
        "create_sys_node": True
    }
