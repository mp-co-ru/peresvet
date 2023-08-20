from src.common.model_crud_settings import ModelCRUDSettings

class ConnectorsModelCRUDSettings(ModelCRUDSettings):
    #: имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = "connectors_model_crud"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://prs:Peresvet21@rabbitmq/"
    #: строка коннекта к OpenLDAP
    ldap_url: str = "ldap://ldap:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"

    #: обменник для публикаций
    publish: dict = {
        "main": {
            "name": "peresvet",
            "type": "direct",
<<<<<<< HEAD
            "routing_key": "connectors_model_crud_publish"
=======
            "routing_key": ["connectors_model_crud_publish"]
>>>>>>> d2074789837efdb871ee581824524cdc755f4ef1
        }
    }

    #: обменник, который публикует запросы от API_CRUD
    consume: dict = {
        "queue_name": "connectors_model_crud_consume",
        "exchanges": {
            "main": {
                "name": "peresvet",
                "type": "direct",
                "routing_key": [
                    "connectors_model_crud_consume",
                    "connectors_api_crud_publish"
<<<<<<< HEAD
                ]
=======
                    ]
>>>>>>> d2074789837efdb871ee581824524cdc755f4ef1
            }
        }
    }

    subscribe: dict = {}

    hierarchy: dict = {
        #: имя узла для хранения сущностей в иерархии
        #: если узел не требуется, то пустая строка
        "node": "connectors",
        #: класс экзмепляров сущности в иерархии
        "class": "prsConnector",
        #: список через запятую родительских классов
        "parent_classes": "",
        #: флаг создания узла ``cn=system`` внутри узла экземпляра сущности
        "create_sys_node": True
    }
