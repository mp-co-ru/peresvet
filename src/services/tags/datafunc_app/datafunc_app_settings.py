from src.common.app_svc_settings import AppSvcSettings


class DatafuncAppSettings(AppSvcSettings):
    #: имя сервиса
    svc_name: str = "datafunc_app"

    hierarchy: dict = {
        #: класс экземпляров сущности в
        #: пример: prsTag
        "class": "prsTag"
    }
