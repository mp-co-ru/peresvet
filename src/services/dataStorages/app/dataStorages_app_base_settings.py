from typing import List
from src.common.app_svc_settings import AppSvcSettings

class DataStoragesAppBaseSettings(AppSvcSettings):
    #: имя сервиса
    svc_name: str = "dataStorages_app_base"
    
    # код типа хранилища: 0 - Postgresql, 1 - victoriametrics
    datastorage_type: int = 0
    
    # периодичность накопления кэша данных, секунды
    cache_data_period: int = 30

    hierarchy: dict = {
        #: имя узла для хранения сущностей в иерархии
        #: если узел не требуется, то пустая строка
        "node": "dataStorages",
        #: класс экзмепляров сущности в иерархии
        "class": "prsDataStorage",
        #: список через запятую родительских классов
        "parent_classes": ""
    }