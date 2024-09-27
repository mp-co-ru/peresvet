from src.common.api_crud_settings import APICRUDSettings

class AlertsAPICRUDSettings(APICRUDSettings):

    #: имя сервиса
    svc_name: str = "alerts_api_crud"
    entity: str = "alerts"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://prs:Peresvet21@rabbitmq/"

    #: обменник для публикаций
    publish: dict = {
        "main": {
            "name": "peresvet",
            "type": "direct",
            "routing_key": "alerts_api_crud_publish"
        }
    }
    consume: dict = {
        "queue_name": "alerts_api_crud_consume",
        "exchanges": {
            "main": {
                #: имя обменника
                "name": "peresvet",
                #: тип обменника
                "type": "direct",
                #: привзяка для очереди
                "routing_key": ["alerts_api_crud_consume"]
            }
        }
    }
