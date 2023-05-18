"""
Модуль содержит класс-конфигурацию для сервиса, предоставляющего API для
работы с иерархией.
"""

from src.common.settings import Settings

class APICRUDSettings(Settings):
    """Класс-конфигурация для сервиса, предоставляющего API.
    Отличается от базового класса наличием переменной, в которой хранится
    версия API.

    Args:
        Settings (_type_): _description_
    """

    #: версия API
    api_version: str = "/v1"
