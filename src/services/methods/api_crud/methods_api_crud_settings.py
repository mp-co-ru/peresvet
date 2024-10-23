from src.common.api_crud_settings import APICRUDSettings

class MethodsAPICRUDSettings(APICRUDSettings):
    #: имя сервиса
    svc_name: str = "methods_api_crud"
    
    hierarchy: dict = {
        #: класс экземпляров сущности в
        #: пример: prsTag
        "class": "prsMethod"
    }
