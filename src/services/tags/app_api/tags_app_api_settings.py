from src.common.api_crud_settings import APICRUDSettings

class TagsAppAPISettings(APICRUDSettings):

    #: имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = "tags_app_api"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://prs:Peresvet21@rabbitmq/"

    #: обменник для публикаций
    publish: dict = {
        "main": {
            "name": "tags",
            "type": "direct",
            "routing_key": "tags_app_api_publish"
        }
    }
    consume: dict = {
        "queue_name": "tags_app_api_consume",
        "exchanges": {
            "main": {
                #: имя обменника
                "name": "tags",
                #: тип обменника
                "type": "direct",
                #: привзяка для очереди
                "routing_key": ["tags_app_api_consume"]
            }
        }
    }
