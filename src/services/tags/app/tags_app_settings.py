from src.common.app_svc_settings import AppSvcSettings

class TagsAppSettings(AppSvcSettings):
    #: имя сервиса
    svc_name: str = "tags_app"
    
    hierarchy: dict = {
        #: класс экзмепляров сущности в иерархии
        "class": "prsTag"
    }
