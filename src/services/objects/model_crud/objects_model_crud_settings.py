from src.common.model_crud_settings import ModelCRUDSettings

class ObjectsModelCRUDSettings(ModelCRUDSettings):
    #: имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = "objects_model_crud"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://prs:Peresvet21@rabbitmq/"
    #: строка коннекта к OpenLDAP
    ldap_url: str = "ldap://ldap:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"

    #: обменник для публикаций
    publish: dict = {
        "main": {
            "name": "peresvet",
            "type": "direct",
            "routing_key": ["objects_model_crud_publish"]
        }
    }

    #: обменник, который публикует запросы от API_CRUD
    consume: dict = {
        "queue_name": "objects_model_crud_consume",
        "exchanges": {
            "main": {
                "name": "peresvet",
                "type": "direct",
                "routing_key": [
                    "objects_model_crud_consume",
                    "objects_api_crud_publish"
                ]
            }
        }
    }

    subscribe: dict = {}

    hierarchy: dict = {
        #: имя узла для хранения сущностей в иерархии
        #: если узел не требуется, то пустая строка
        "node": "objects",
        #: класс экзмепляров сущности в иерархии
        "class": "prsObject",
        #: список через запятую родительских классов
        "parent_classes": "prsObject",
        #: флаг создания узла ``cn=system`` внутри узла экземпляра сущности
        "create_sys_node": True
    }
