from src.common.app_svc_settings import AppSvcSettings

class MethodsAppSettings(AppSvcSettings):
    #: имя сервиса
    svc_name: str = "methods_app"
<<<<<<< HEAD
    
    hierarchy: dict = {
        #: класс экзмепляров сущности в иерархии
        "class": "prsMethod"
=======

    hierarchy: dict = {
        #: класс экзмепляров сущности в иерархии
        "class": "prsMethod"
    }

    log: dict = {
        "level": "DEBUG",
        "file_name": "log/peresvet.log",
        "retention": 10,
        "rotation": "5 MB"
>>>>>>> peresvet/dev
    }