from src.common.app_svc_settings import AppSvcSettings

class ConnectorsMQTTAppSettings(AppSvcSettings):
    api_version: str = "/v1"
    #: имя сервиса
    svc_name: str = "connectors_mqtt_app"
        #: параметры, связанные с работой с иерархией
    hierarchy: dict = {
        #: имя узла в котором хранятся сущности в иерархии
        #: пример: tags, objects, ...
        "node": "connectors",
        #: класс экзмепляров сущности в
        #: пример: prsTag
        "class": "prsConnector"
    }
