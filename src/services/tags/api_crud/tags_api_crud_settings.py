from src.common.api_settings import APICRUDSettings

class TagsAPICRUDSettings(APICRUDSettings):

    #: имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = "tags_api_crud"
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://guest:guest@localhost/"
    #: строка коннекта к OpenLDAP
    ldap_url: str = "ldap://localhost:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"

    #: обменник для публикаций
    pub_exchange: dict = {
        "name": "tags_api_crud",
        "type": "direct",
        "routing_key": "tags_api_crud"
    }
