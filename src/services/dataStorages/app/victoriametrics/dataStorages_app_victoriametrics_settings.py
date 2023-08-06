from typing import List
from src.common.svc_settings import SvcSettings

class DataStoragesAppVictoriametricsSettings(SvcSettings):
    #: имя сервиса
    svc_name: str = "dataStorages_app_victoriametrics"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://prs:Peresvet21@rabbitmq/"

    # описание обменников, в которые сервис будет публиковать свои сообщения
    # наиболее часто это всего один обменник, описанный в ключе "main"
    # информацию об обменниках и сообщениях см. в документации на каждый
    # конкретный сервис
    publish: dict = {
        #: главный обменник
        "main": {
            #: имя обменника
            "name": "peresvet",
            #: тип обменника
            "type": "direct",
            #: routing_key, с которым будут публиковаться сообщения,
            # вычисляется во время работы сервиса: это - tag_id или alert_id
            #"routing_key": ["dataStorages_app_postgresql"]
        }
    }

    # описание обменников, из которых сервис получает сообщения
    # информацию об обменниках и сообщениях см. в документации на каждый
    # конкретный сервис
    consume: dict = {
        "queue_name": "dataStorages_app_victoriametrics_consume",
        "exchanges": {
            "main": {
                #: имя обменника
                "name": "peresvet",
                #: тип обменника
                "type": "direct",
                #: привязка для очереди
                "routing_key": ["dataStorages_model_crud_publish"]
            },
            "tags": {
                "name": "peresvet",
                "type": "direct",
                #: привязка для очереди
                # привязка вычисляется во время работы сервиса
            },
            "alerts": {
                "name": "peresvet",
                "type": "direct",
                #: привязка для очереди
                # привязка вычисляется во время работы сервиса
            }
        }
    }

    #: строка коннекта к OpenLDAP
    ldap_url: str = "ldap://ldap:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"

    """
    subscribe: dict = {
         # сущность, уведомления об изменение/удаление узлов которой
         # требуются сервису
         '''
         "<сущность_2>": {
            # в этот обменник сервис будет посылать сообщение "subscribe"
            "publish": {
               "name": "<сущность_2>",
               "type": "direct",
               "routing_key": "<сущность_2>_model_crud_consume"
            },
            # обменник, из которого сервис будет получать уведомления об
            # изменениях узлов
            # (к этому обменнику, с указанным routing_key будет привязана
            # главная очередь сервиса с управляющими командами)
            "consume": {
               "name": "<сущность_2>",
               "type": "direct",
               "routing_key": "<сущность_2>_model_crud_publish"
            }
         }
         '''
      }
    """

    # код типа хранилища: 0 - Postgresql, 1 - victoriametrics
    datastorage_type: int = 1
    # в этом параметре указываются коды хранилищ, которые будет обслуживать
    # данный сервис
    # если коды не указаны, то будут обслуживаться все хранилища заданного типа
    datastorages_id: List[str] = []
