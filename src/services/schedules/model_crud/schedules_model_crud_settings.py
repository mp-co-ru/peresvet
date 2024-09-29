from src.common.model_crud_settings import ModelCRUDSettings

class SchedulesModelCRUDSettings(ModelCRUDSettings):
    #: имя сервиса
    svc_name: str = "schedules_model_crud"
    
    hierarchy: dict = {
        #: имя узла для хранения сущностей в иерархии
        #: если узел не требуется, то пустая строка
        "node": "schedules",
        #: класс экзмепляров сущности в иерархии
        "class": "prsSchedule",
        #: список через запятую родительских классов
        "parent_classes": "",
        #: флаг создания узла ``cn=system`` внутри узла экземпляра сущности
        "create_sys_node": True
    }
