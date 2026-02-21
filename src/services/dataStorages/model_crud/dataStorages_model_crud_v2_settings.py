from src.common.model_crud_settings import ModelCRUDSettings


class DataStoragesModelCRUDV2Settings(ModelCRUDSettings):
    #: имя сервиса
    svc_name: str = "dataStorages_model_crud_v2"

    hierarchy: dict = {
        "node": "dataStorages",
        "class": "prsDataStorage",
        "parent_classes": "",
        "child_classes": [
            "prsDatastorageTagData",
            "prsDatastorageAlertData",
            "prsDatastorageOperation",
            "prsDatastorageOperationParameter",
        ],
    }

