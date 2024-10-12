from src.common.api_crud_settings import APICRUDSettings

class SchedulesAPICRUDSettings(APICRUDSettings):
    #: имя сервиса
    svc_name: str = "schedules_api_crud"
    
    hierarchy: dict = {
        #: класс экземпляров сущности в
        #: пример: prsTag
        "class": "prsSchedule"
    }