from src.common.model_crud_settings import ModelCRUDSettings

class TagsCRUDSettings(ModelCRUDSettings):
    #: имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = "tags_model_crud"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://guest:guest@localhost/"
    #: строка коннекта к OpenLDAP
    ldap_url: str = "ldap://localhost:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"

    #: обменник для публикаций
    pub_exchange_name: str = "tags_model_crud"
    pub_exchange_type: str = "direct"
    pub_routing_key: str = "tags_model_crud"

    #: обменник, который публикует запросы от API_CRUD
    api_crud_exchange_name: str = "tags_api_crud"
    api_crud_exchange_type: str = "direct"
    api_crud_queue_name: str = "tags_api_crud"
    api_crud_routing_key: str = "tags_api_crud"

    #: имя узла для хранения сущностей в иерархии
    #: если узел не требуется, то пустая строка
    hierarchy_node_name = "tags"
    #: класс экзмепляров сущности в иерархии
    hierarchy_class = "prsTag"
    #: список через запятую родительских классов
    hierarchy_parent_classes = "prsObject"
