from src.common.api_crud_settings import APICRUDSettings

class TagsAPICRUDSettings(APICRUDSettings):

    #: имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = "tags_api_crud"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://prs:Peresvet21@rabbitmq/"

    #: обменник для публикаций
    publish: dict = {
        "main": {
            "name": "peresvet",
            "type": "direct",
            "routing_key": "tags_api_crud_publish"
        }
    }
    consume: dict = {
        "queue_name": "tags_api_crud_consume",
        "exchanges": {
            "main": {
                #: имя обменника
                "name": "peresvet",
                #: тип обменника
                "type": "direct",
                #: привзяка для очереди
                "routing_key": ["tags_api_crud_consume"]
            }
        }
    }
