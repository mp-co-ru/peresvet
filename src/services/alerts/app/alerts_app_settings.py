from src.common.svc_settings import SvcSettings

class AlertsAppSettings(SvcSettings):

    #: имя сервиса
    svc_name: str = "alerts_app"

    hierarchy: dict = {
        #: класс экзмепляров сущности в иерархии
        "class": "prsAlert"
    }

    nodes: list[str] = []
    