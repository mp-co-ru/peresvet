from src.common.app_svc_settings import AppSvcSettings

class AlertsAppSettings(AppSvcSettings):

    #: имя сервиса
    svc_name: str = "alerts_app"

    hierarchy: dict = {
        #: класс экзмепляров сущности в иерархии
        "class": "prsAlert"
    }