from src.common.svc_settings import SvcSettings

class TagsAppAPISettings(SvcSettings):

    #: имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = "tags_app_api"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://prs:Peresvet21@rabbitmq/"

    #: версия API
    api_version: str = "/v1"

    #: строка коннекта к OpenLDAP
    ldap_url: str = "ldap://ldap:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"

    #: обменник для публикаций
    publish: dict = {
        "main": {
            "name": "peresvet",
            "type": "direct",
            "routing_key": "tags_app_api_publish"
        }
    }
    consume: dict = {
        "queue_name": "tags_app_api_consume",
        "exchanges": {
            "main": {
                #: имя обменника
                "name": "peresvet",
                #: тип обменника
                "type": "direct",
                #: привзяка для очереди
                "routing_key": ["tags_app_api_consume"]
            }
        }
    }
