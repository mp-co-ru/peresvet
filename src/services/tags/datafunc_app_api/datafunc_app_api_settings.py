from src.common.svc_settings import SvcSettings

class DatafuncAppAPISettings(SvcSettings):
    #: имя сервиса
    svc_name: str = "datafunc_app_api"
    #: версия API
    api_version: str = "/v1"
    