from src.common.api_crud_settings import APICRUDSettings

class ObjectsAPICRUDSettings(APICRUDSettings):
    #: имя сервиса
    svc_name: str = "objects_api_crud"

    hierarchy: dict = {
        #: класс экземпляров сущности в
        #: пример: prsTag
        "class": "prsObject"
    }
        
