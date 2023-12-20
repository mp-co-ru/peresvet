from src.common.svc_settings import SvcSettings

class RetranslatorAppSettings(SvcSettings):
    #: имя сервиса
    svc_name: str = "retranslator_app"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://prs:Peresvet21@rabbitmq/"
    rabbitmq_api_url: str = "http://rabbitmq:15672/api"
    #: строка коннекта к OpenLDAP
    ldap_url: str = "ldap://ldap:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"
    tags_app_url: str = "http://nginx/v1/data/"

    #: обменник для публикаций
    publish: dict = {
        "main": {
            "name": "peresvet",
            "type": "direct",
            "routing_key": "retranslator_app_publish"
        }
    }

    consume: dict = {
        "queue_name": "retranslator_app_consume",
        "exchanges": {
            "main": {
                "name": "peresvet",
                "type": "direct",
                "routing_key": ["retranslator_app_consume",
                                 "tags_app_publish"
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
