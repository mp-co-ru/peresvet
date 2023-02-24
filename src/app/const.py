from enum import IntEnum
from typing import List

class CNDataStorageTypes(IntEnum):
    CN_DS_VICTORIAMETRICS : int = 1
    CN_DS_POSTGRESQL : int = 0

    @classmethod
    def get_supported(cls) -> List[int]:
        return [cls.CN_DS_VICTORIAMETRICS, cls.CN_DS_POSTGRESQL]

class CNHTTPExceptionCodes(IntEnum):
    CN_422: int = 422 # Unprocessable Entity
    CN_424: int = 424 # Failed Dependency
    CN_500: int = 500 # Internal Server Error
    CN_503: int = 503 # Service Unavailable

class CNTagValueTypes(IntEnum):
    CN_INT: int = 1
    CN_DOUBLE: int = 2
    CN_STR: int = 3
    CN_JSON: int = 4

class Order(IntEnum):
    """ Порядок сортировки выборки
    ASC - по возрастанию
    DESC - по убыванию
    """
    CN_ASC: int = 1
    CN_DESC: int = 2
