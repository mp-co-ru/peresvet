from src.common.model_crud_settings import ModelCRUDSettings

class DataStoragesModelCRUDSettings(ModelCRUDSettings):
    #: имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = "dataStorages_model_crud"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://prs:Peresvet21@rabbitmq/"
    #: строка коннекта к OpenLDAP
    ldap_url: str = "ldap://ldap:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"

    #: обменник для публикаций
    publish: dict = {
        "main": {
            "name": "peresvet",
            "type": "direct",
            "routing_key": "dataStorages_model_crud_publish"
        }
    }

    consume: dict = {
        "queue_name": "dataStorages_model_crud_consume",
        "exchanges": {
            #: обменник, который публикует запросы от API_CRUD
            "main": {
                "name": "peresvet",
                "type": "direct",
                "routing_key": [
                    "dataStorages_model_crud_consume",
                    "dataStorages_api_crud_publish"
                ]
            }
        }
    }

    hierarchy: dict = {
        #: имя узла для хранения сущностей в иерархии
        #: если узел не требуется, то пустая строка
        "node": "dataStorages",
        #: класс экзмепляров сущности в иерархии
        "class": "prsDataStorage",
        #: список через запятую родительских классов
        "parent_classes": ""
    }
