from pydantic import BaseSettings

class BaseSvcSettings(BaseSettings):

    # имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = ""
    # строка коннекта к RabbitMQ
    amqp_url: str = "amqp://guest:guest@localhost/"
    # строка коннекта к OpenLDAP
    ldap_url: str = "ldap://localhost:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"
    # тип обменника
    pub_exchange_type: str = "fanout"
