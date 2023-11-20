from src.common.model_crud_settings import ModelCRUDSettings

class SchedulesModelCRUDSettings(ModelCRUDSettings):
    #: имя сервиса
    svc_name: str = "schedules_model_crud"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://prs:Peresvet21@rabbitmq/"
    #: строка коннекта к OpenLDAP
    ldap_url: str = "ldap://ldap:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"

    ##: обменник для публикаций
    publish: dict = {
        "main": {
            "name": "peresvet",
            "type": "direct",
            "routing_key": ["schedules_model_crud_publish"]
        }
    }

    #: обменник, который публикует запросы от API_CRUD
    consume: dict = {
        "queue_name": "schedules_model_crud_consume",
        "exchanges": {
            "main": {
                "name": "peresvet",
                "type": "direct",
                "routing_key": [
                    "schedules_model_crud_consume",
                    "schedules_api_crud_publish"
                ]
            }
        }
    }

    hierarchy: dict = {
        #: имя узла для хранения сущностей в иерархии
        #: если узел не требуется, то пустая строка
        "node": "schedules",
        #: класс экзмепляров сущности в иерархии
        "class": "prsSchedule",
        #: список через запятую родительских классов
        "parent_classes": "",
        #: флаг создания узла ``cn=system`` внутри узла экземпляра сущности
        "create_sys_node": True
    }
