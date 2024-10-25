from src.common.app_svc_settings import AppSvcSettings

class MethodsAppSettings(AppSvcSettings):
    #: имя сервиса
    svc_name: str = "methods_app"
    
    hierarchy: dict = {
        #: класс экзмепляров сущности в иерархии
        "class": "prsMethod"
    }