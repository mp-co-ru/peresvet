from abc import ABC, abstractmethod
from typing import Union, Dict, Any, List

JsonType = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]

class ABCCache(ABC):
    """Абстрактный базовый класс кэша.
    Кэш организован в виде ``ключ = значение``.
    Ключ - строка, значение - json-объект.
    Класс рассчитан на "потоковую" работу с ключами.
    То есть создаётся очередь команд работы с кэшем, 
    которая выполняется при вызове асинхронного метода
    exec.

    В именах ключей в json-объекте могут быть только английские буквы!

    Args:
        ABC (_type_): _description_
    """
    @abstractmethod
    def set(self, name: str, key: str, obj: JsonType, nx: bool = False, xx: bool = False):
        """Метод должен возвращать self
        """
        pass

    @abstractmethod
    def get(self, name: str, *keys):
        """
        Метод должен возвращать self.
        Как и все другие методы, встраивается в цепочку выполнения.
        Если в качестве keys указаны несколько ключей, они возвращаются в виде одного словаря.
        Если в качестве keys указан один ключ, он возвращается просто как значение.
        Результат цепочки возвращается всегда как массив, даже если в цепочке всего один вызов get.
        Если name нет в кэше, то возвращается [None].
        Если name есть в кэше, но нет одного из указанных keys - генерится исключение.
        Если key запрашивается один и его значение в кэше = None, то возвращается ['null'].
        Если запрашиваются несколько ключей и значение каких-то = None, то они так и возвращаются, как None.
        генерируется исключение.
        """
        pass
    
    @abstractmethod
    def delete(self, name: str, key: str = None):
        """Метод должен возвращать self
        """
        pass

    @abstractmethod
    def append(self, name: str, key: str, *objs: List[JsonType]):
        """Метод добавляет в массив список объектов.
        Должен возвращать self.
        """
        pass

    @abstractmethod
    def index(self, name: str, key: str, obj: JsonType):
        """Метод определяет индекс объекта в массиве.
        Должен возвращать self.
        """
        pass

    @abstractmethod
    def pop(self, name: str, key: str, index: int):
        """Метод удаляет из массива объект с индексом index.
        Должен возвращать self.
        """
        pass

    @abstractmethod
    async def exec(self):
        """Метод выполняет цепочку команд. Должен возвращать результат выполнения этой цепочки.
        """
        pass

    @abstractmethod
    async def reset(self):
        """Метод сбрасывает сформированную цепочку команд.
        """
        pass
