"""Класс, от которого наследуются все классы-настройки для сервисов.

Определяет четыре переменные окружения:

**svc_name** - имя сервиса;

**amqp_url** - URL к брокеру сообщений;

**ldap_url** - URL к ldap-серверу;

**pub_exchange_type** - тип создаваемого обменника, в который сервис
будет публиковать свои сообщения.
"""
from pydantic import BaseSettings

class Settings(BaseSettings):
    # имя сервиса. сервисы *_mod_crud создают в иерархии узел с таким же именем
    svc_name: str = ""
    # строка коннекта к RabbitMQ
    amqp_url: str = "amqp://guest:guest@localhost/"
    # строка коннекта к OpenLDAP
    ldap_url: str = "ldap://localhost:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"
    # тип обменника
    pub_exchange_type: str = "fanout"
