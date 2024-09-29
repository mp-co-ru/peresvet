from src.common.svc_settings import SvcSettings

class ConnectorsAppSettings(SvcSettings):
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
