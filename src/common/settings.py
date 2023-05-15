"""
Класс, от которого наследуются все классы-настройки для сервисов.
Наследуется от класса ``pydantic.BaseSettings``, все настройки передаются
в json-файлах либо в переменных окружения.
По умолчанию имя файла с настройками - ``config.json``.
Имя конфигурационного файла передаётся сервису в переменной окружения
``config_file``.
"""

import os

import json
from pathlib import Path
from typing import Any
from pydantic import BaseSettings

def json_config_settings_source(settings: BaseSettings) -> dict[str, Any]:
    encoding = settings.__config__.env_file_encoding
    return json.loads(Path(os.getenv('config_file', 'config.json')).read_text(encoding))

class Settings(BaseSettings):
    #: имя сервиса
    svc_name: str = ""
    #: строка коннекта к RabbitMQ
    amqp_url: str = "amqp://guest:guest@localhost/"
    #: строка коннекта к OpenLDAP
    ldap_url: str = "ldap://localhost:389/cn=prs????bindname=cn=admin%2ccn=prs,X-BINDPW=Peresvet21"

    # описание обменника, в котором сервис будет публиковать свои сообщения
    pub_exchange: dict = {
        #: имя обменника
        "name": "",
        #: тип обменника
        "type": "direct",
        #: routing_key, с которым будут публиковаться сообщения обменником
        #: pub_exchange_type
        "routing_key": ""
    }

    class Config:
        env_file_encoding = 'utf-8'

        @classmethod
        def customise_sources(
            cls,
            init_settings,
            env_settings,
            file_secret_settings,
        ):
            return (
                init_settings,
                json_config_settings_source,
                env_settings,
                file_secret_settings,
            )
