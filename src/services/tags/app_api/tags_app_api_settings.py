from src.common.api_crud_settings import APICRUDSettings

class TagsAppAPISettings(APICRUDSettings):
    #: имя сервиса
    svc_name: str = "tags_app_api"

    hierarchy: dict = {
        #: класс экземпляров сущности в
        #: пример: prsTag
        "class": "prsTag"
    }
    