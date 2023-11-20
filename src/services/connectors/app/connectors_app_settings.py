from src.common.svc_settings import SvcSettings

class ConnectorsAppSettings(SvcSettings):
    #: имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = "connectors_app"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://prs:Peresvet21@rabbitmq/"
    #: строка коннекта к OpenLDAP
    ldap_url: str = "ldap://ldap:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"
    #: версия API
    api_version: str = "/v1"

    #: обменник для публикаций
    publish: dict = {
        "main": {
            "name": "peresvet",
            "type": "direct",
            "routing_key": "connectors_app_publish"
        }
    }

    #: обменник, который публикует запросы от API_CRUD
    consume: dict = {
        "queue_name": "connectors_app_consume",
        "exchanges": {
            "main": {
                "name": "peresvet",
                "type": "direct",
                "routing_key": [
                        "connectors_app_consume",
                        "tags_app_api_publish"
                    ]
            }
        }
    }

    #: параметры, связанные с работой с иерархией
    hierarchy: dict = {
        #: имя узла в котором хранятся сущности в иерархии
        #: пример: tags, objects, ...
        "node": "",
        #: класс экзмепляров сущности в
        #: пример: prsTag
        "class": "",
    }
