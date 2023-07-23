from src.common.api_crud_settings import APICRUDSettings

class ObjectsAPICRUDSettings(APICRUDSettings):

    #: версия API
    api_version: str = "/v1"

    #: имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = "objects_api_crud"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://prs:Peresvet21@rabbitmq/"

    #: обменник для публикаций
    publish: dict = {
        "main": {
            "name": "peresvet",
            "type": "direct",
            "routing_key": "objects_api_crud_publish"
        }
    }
    consume: dict = {
        "queue_name": "objects_api_crud_consume",
        "exchanges": {
            "main": {
                #: имя обменника
                "name": "peresvet",
                #: тип обменника
                "type": "direct",
                #: привзяка для очереди
                "routing_key": ["objects_api_crud_consume"]
            }
        }
    }
