from src.common.base_svc_settings import BaseSvcSettings

class ConnectorsAppSettings(BaseSvcSettings):

    #: имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = "connectors_app"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://prs:Peresvet21@rabbitmq/"

    #: обменник для публикаций
    publish: dict = {
        "main": {
            "name": "connectors_app",
            "type": "direct",
            "routing_key": "connectors_app"
        }
    }

    #: обменник, который публикует  для публикаций
    tags_model_crud_exchange: dict = {
        "main": {
            "name": "tags_model_crud",
            "type": "direct",
            "queue_name": "tags_api_crud",
            # "routing_key": "connectors_api_crud" # Вопрос как сделать динамическим этот параметр
        }
    }
