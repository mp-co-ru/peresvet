from typing import List
from src.services.dataStorages.app.dataStorages_app_base_settings import DataStoragesAppBaseSettings

class DataStoragesAppPostgreSQLSettings(DataStoragesAppBaseSettings):
    #: имя сервиса
    svc_name: str = "dataStorages_app_postgresql"
    
    # код типа хранилища: 0 - Postgresql, 1 - victoriametrics
    datastorage_type: int = 0
    # в этом параметре указываются коды хранилищ, которые будет обслуживать
    # данный сервис
    # если коды не указаны, то будут обслуживаться все хранилища заданного типа
    datastorages_id: List[str] = []
    
    hierarchy: dict = {
        #: имя узла для хранения сущностей в иерархии
        #: если узел не требуется, то пустая строка
        "node": "dataStorages",
        #: класс экзмепляров сущности в иерархии
        "class": "prsDataStorage",
        #: список через запятую родительских классов
        "parent_classes": ""
    }

    # периодичность накопления кэша данных, секунды
    cache_data_period: int = 100

