from enum import IntEnum

class CNDataStorageTypes(IntEnum):
    CN_DS_VICTORIAMETRICS : int = 1
    CN_DS_POSTGRESQL : int = 0
    # Интеграционное хранилище (операции GET/SET в LDAP) поверх PostgreSQL
    CN_DS_INTEGRATIONAL_POSTGRESQL : int = 2

    @classmethod
    def get_supported(cls) -> list[int]:
        return [
            cls.CN_DS_VICTORIAMETRICS,
            cls.CN_DS_POSTGRESQL,
            cls.CN_DS_INTEGRATIONAL_POSTGRESQL,
        ]

class CNHTTPExceptionCodes(IntEnum):
    CN_422: int = 422 # Unprocessable Entity
    CN_424: int = 424 # Failed Dependency
    CN_500: int = 500 # Internal Server Error
    CN_503: int = 503 # Service Unavailable

class CNTagValueTypes(IntEnum):
    CN_INT: int = 0
    CN_DOUBLE: int = 1
    CN_STR: int = 2
    CN_JSON: int = 4

class Order(IntEnum):
    """ Порядок сортировки выборки
    ASC - по возрастанию
    DESC - по убыванию
    """
    CN_ASC: int = 1
    CN_DESC: int = 2
