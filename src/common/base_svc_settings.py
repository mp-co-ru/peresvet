"""
Класс, от которого наследуются все классы-настройки для сервисов.
Наследуется от класса ``pydantic.BaseSettings``\, все настройки передаются
в json-файлах либо в переменных окружения.
По умолчанию имя файла с настройками - ``config.json``\.
Имя конфигурационного файла передаётся сервису в переменной окружения
``config_file``\.
"""

import os

import json
from pathlib import Path
from typing import Any, Dict, Tuple, Type
from pydantic import BaseModel, ConfigDict
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource
)

class JsonConfigSettingsSource(PydanticBaseSettingsSource):

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> Tuple[Any, str, bool]:
        encoding = self.config.get('env_file_encoding')
        try:
            file_content_json = json.loads(
                Path(os.getenv('config_file', f'{self.svc_name}_config.json')).read_text(encoding)
            )
            field_value = file_content_json.get(field_name)
        except Exception as _:
            return None, None, False

        return field_value, field_name, False

    def prepare_field_value(
        self, field_name: str, field: FieldInfo, value: Any, value_is_complex: bool
    ) -> Any:
        return value

    def __call__(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}

        for field_name, field in self.settings_cls.model_fields.items():
            field_value, field_key, value_is_complex = self.get_field_value(
                field, field_name
            )
            field_value = self.prepare_field_value(
                field_name, field, field_value, value_is_complex
            )
            if field_value is not None:
                d[field_key] = field_value

        return d

class BaseSvcSettings(BaseSettings, BaseModel):
    #model_config = SettingsConfigDict(env_file_encoding='utf-8')
    # https://giters.com/pydantic/pydantic/issues/6322
    model_config = ConfigDict(protected_namespaces=())

    #: имя сервиса
    svc_name: str = ""
    
    broker: dict = {
        #: строка коннекта к RabbitMQ
        "amqp_url": "amqp://prs:Peresvet21@rabbitmq/",
        #: имя обменника
        "name": "peresvet"        
    }

    hierarchy: dict = {
        #: класс экземпляров сущности в
        #: пример: prsTag
        "class": ""
    }

    log: dict = {
        "level": "INFO",
        "file_name": "peresvet.log",
        "retention": "1 months",
        "rotation": "20 days"
    }

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            env_settings,
            JsonConfigSettingsSource(settings_cls),
            init_settings,
            dotenv_settings,
            file_secret_settings,
        )
    
    cache_url: str = "redis://redis:6379?decode_responses=True&protocol=3"
