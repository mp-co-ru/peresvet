<<<<<<< HEAD
from src.common.svc_settings import SvcSettings

class ConnectorsAppSettings(SvcSettings):
=======
from src.common.app_svc_settings import AppSvcSettings

class ConnectorsAppSettings(AppSvcSettings):
    api_version: str = "/v1"
>>>>>>> peresvet/dev
    #: имя сервиса
    svc_name: str = "connectors_app"
        #: параметры, связанные с работой с иерархией
    hierarchy: dict = {
        #: имя узла в котором хранятся сущности в иерархии
        #: пример: tags, objects, ...
        "node": "connectors",
        #: класс экзмепляров сущности в
        #: пример: prsTag
        "class": "prsConnector"
    }
