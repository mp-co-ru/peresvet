from src.common.app_svc_settings import AppSvcSettings

class SchedulesAppSettings(AppSvcSettings):
    #: имя сервиса
    svc_name: str = "schedules_app"
    
    #: параметры, связанные с работой с иерархией
    hierarchy: dict = {
        #: класс экзмепляров сущности в иерархии
        "class": "prsSchedule"
    }
    