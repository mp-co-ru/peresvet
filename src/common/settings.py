"""
Класс, от которого наследуются все классы-настройки для сервисов.
Наследуется от класса ``pydantic.BaseSettings``, все настройки передаются
через переменные окружения.
"""

from pydantic import BaseSettings

class Settings(BaseSettings):
    #: имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = ""
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://guest:guest@localhost/"
    #: строка коннекта к OpenLDAP
    ldap_url: str = "ldap://localhost:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"

    #: имя обменник
    pub_exchange_name: str = ""
    #: тип обменника
    pub_exchange_type: str = "direct"
    #: routing_key, с которым будут публиковаться сообщения обменником
    #: pub_exchange_type
    pub_routing_key: str = ""
