from src.common.api_crud_settings import APICRUDSettings

class DatafuncAppAPISettings(APICRUDSettings):
    #: имя сервиса
    svc_name: str = "datafunc_app_api"
    #: версия API
    api_version: str = "/v1"
    
    hierarchy: dict = {
        #: класс экземпляров сущности в
        #: пример: prsTag
        "class": "prsTag"
    }
    