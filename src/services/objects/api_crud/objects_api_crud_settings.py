from src.common.api_crud_settings import APICRUDSettings

class ObjectsAPICRUDSettings(APICRUDSettings):
    #: версия API
    api_version: str = "/v1"

    #: имя сервиса
    svc_name: str = "objects_api_crud"
        
