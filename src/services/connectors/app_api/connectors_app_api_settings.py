from src.common.api_crud_settings import APICRUDSettings

class ConnectorsAppAPISettings(APICRUDSettings):
    #: имя сервиса
    svc_name: str = "connectors_app_api"

    hierarchy: dict = {
        #: класс экземпляров сущности в
        #: пример: prsTag
        "class": "prsConnector"
    }
