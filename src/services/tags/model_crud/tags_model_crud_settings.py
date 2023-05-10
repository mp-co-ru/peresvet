from src.common.model_crud_settings import ModelCRUDSettings

class TagsCRUDSettings(ModelCRUDSettings):
    # имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = "tags_model_crud"
    # строка коннекта к RabbitMQ
    amqp_url: str = "amqp://guest:guest@localhost/"
    # строка коннекта к OpenLDAP
    ldap_url: str = "ldap://localhost:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"
    # тип обменника
    pub_exchange_type: str = "fanout"

    # имя exchange'а, который публикует запросы от API_CRUD
    api_crud_exchange: str = "tags_api_crud"
    # имя очереди, которую будут слушать все экземпляры сервиса model_crud
    api_crud_queue: str = "tags_api_crud"
    # имя узла для хранения сущностей в иерархии
    # если узел не требуется, то пустая строка
    hierarchy_node_name = "tags"
    # класс экзмепляров сущности в иерархии
    hierarchy_class = "prsTag"
    # список через запятую родительских классов
    hierarchy_parent_classes = "prsObject"
