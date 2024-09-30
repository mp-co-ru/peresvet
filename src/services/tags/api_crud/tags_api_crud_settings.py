from src.common.api_crud_settings import APICRUDSettings

class TagsAPICRUDSettings(APICRUDSettings):
    #: имя сервиса
    svc_name: str = "tags_api_crud"
    
    hierarchy: dict = {
        #: класс экземпляров сущности в
        #: пример: prsTag
        "class": "prsTag"
    }
    