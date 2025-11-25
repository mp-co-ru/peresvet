from src.common.model_crud_settings import ModelCRUDSettings

class DataStoragesModelCRUDSettings(ModelCRUDSettings):
    #: имя сервиса
    svc_name: str = "dataStorages_model_crud"
    
    hierarchy: dict = {
        #: имя узла для хранения сущностей в иерархии
        #: если узел не требуется, то пустая строка
        "node": "dataStorages",
        #: класс экзмепляров сущности в иерархии
        "class": "prsDataStorage",
        #: список через запятую родительских классов
<<<<<<< HEAD
        "parent_classes": ""
=======
        "parent_classes": "",
        "child_classes": ["prsDatastorageTagData", "prsDatastorageAlertData"]
>>>>>>> peresvet/dev
    }
