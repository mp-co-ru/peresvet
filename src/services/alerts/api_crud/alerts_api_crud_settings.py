from src.common.api_crud_settings import APICRUDSettings

class AlertsAPICRUDSettings(APICRUDSettings):

    #: имя сервиса
    svc_name: str = "alerts_api_crud"
    hierarchy: dict = {
        #: класс экземпляров сущности в
        #: пример: prsTag
        "class": "prsAlert"
    }
    