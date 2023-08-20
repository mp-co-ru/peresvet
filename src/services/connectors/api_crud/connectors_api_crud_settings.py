from src.common.api_crud_settings import APICRUDSettings

class ConnectorsAPICRUDSettings(APICRUDSettings):

    #: имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = "connectors_api_crud"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://prs:Peresvet21@rabbitmq/"
    #: строка коннекта к OpenLDAP
    ldap_url: str = "ldap://ldap:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"

    #: обменник для публикаций
    publish: dict = {
        "main": {
                "name": "peresvet",
                "type": "direct",
                "routing_key": "connectors_api_crud_publish"
<<<<<<< HEAD
=======
        }
    }
    consume: dict = {
        "queue_name": "connectors_api_crud_consume",
        "exchanges": {
            "main": {
                #: имя обменника
                "name": "peresvet",
                #: тип обменника
                "type": "direct",
                #: привзяка для очереди
                "routing_key": ["connectors_api_crud_consume"]
            }
>>>>>>> d2074789837efdb871ee581824524cdc755f4ef1
        }
    }

    consume: dict = {
        "queue_name": "connectors_api_crud_consume",
        "exchanges": {
            "main": {
                "name": "peresvet",
                "type": "direct",
                "routing_key": ["connectors_api_crud_consume"]
            }
        }
    }