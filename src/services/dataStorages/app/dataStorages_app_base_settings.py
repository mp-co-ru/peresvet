from typing import List
from src.common.svc_settings import SvcSettings

class DataStoragesAppBaseSettings(SvcSettings):
    #: имя сервиса
    svc_name: str = "dataStorages_app_base"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://prs:Peresvet21@rabbitmq/"
    
    # код типа хранилища: 0 - Postgresql, 1 - victoriametrics
    datastorage_type: int = 0
    # в этом параметре указываются коды хранилищ, которые будет обслуживать
    # данный сервис
    # если коды не указаны, то будут обслуживаться все хранилища заданного типа
    datastorages_id: List[str] = []

    # периодичность накопления кэша данных, секунды
    cache_data_period: int = 30
