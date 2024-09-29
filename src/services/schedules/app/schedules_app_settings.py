from src.common.svc_settings import SvcSettings

class SchedulesAppSettings(SvcSettings):
    #: имя сервиса
    svc_name: str = "schedules_app"
    api_version: str = "/v1"
    
    #: параметры, связанные с работой с иерархией
    hierarchy: dict = {
        #: имя узла в котором хранятся сущности в иерархии
        #: пример: tags, objects, ...
        "node": "schedules",
        #: класс экзмепляров сущности в иерархии
        "class": "prsSchedule"
    }
