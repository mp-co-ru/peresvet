from typing import List

from src.services.dataStorages.app.dataStorages_app_base_settings import DataStoragesAppBaseSettings


class DataStoragesAppIntegrationalPostgreSQLSettings(DataStoragesAppBaseSettings):
    #: имя сервиса
    svc_name: str = "dataStorages_app_integrational_postgresql"

    # код типа хранилища (prsDataStorage.prsEntityTypeCode)
    # 2 - integrational (PostgreSQL)
    datastorage_type: int = 2

    # в этом параметре указываются коды хранилищ, которые будет обслуживать данный сервис
    # если коды не указаны, то будут обслуживаться все хранилища заданного типа
    datastorages_id: List[str] = []

    # периодичность сброса historian-кэша не используется, но оставим по умолчанию
    cache_data_period: int = 3600

