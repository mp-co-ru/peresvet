from src.common.api_crud_settings import APICRUDSettings

class DataStoragesAPICRUDSettings(APICRUDSettings):

    #: имя сервиса
    svc_name: str = "dataStorages_api_crud"
    hierarchy: dict = {
        #: класс экземпляров сущности в
        #: пример: prsTag
        "class": "prsDataStorage"
    }
