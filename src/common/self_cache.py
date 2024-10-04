from src.common.base_cache import ABCCache, JsonType
from typing import Union, Dict, Any, List

class RedisCache(ABCCache):
    
    def __init__(self, dsn: str):
        self.data = {}

    def set(self, name: str, key: str = "$", obj: JsonType = {}, nx: bool = False, xx: bool = False):
        if nx and xx:
            raise Exception("Нельзя использовать одновременно оба флага nx и xx.")
        
        if nx:
            if key == "$":
                if self.data.get(name) is None:
                    self.data[name] = obj
                    return self
                return self
                
            else:
                if self.data.get(name) is None:
                    raise Exception("Узел можно создавать только в корне.")
                else:
                    if self.data[name].get(key) is None:
                       self.data[name][key] = obj
                       return self
                    else:
                        return self

        if xx:
            if key == "$":
                if self.data.get(name) is None:
                    return self
                
                self.data[name] = obj
                return self
                
            else:
                if self.data.get(name) is None:
                    return self
                else:
                    if self.data[name].get(key) is None:
                        self.data[name][key] = obj
                        return self
                    else:
                        return self

        if self.data.get(name) is None:
            if key != "$":
                raise Exception("Узел можно создавать только в корне.")
            self.data[name] = obj
            return self

        self.data[name][key] = obj

        return self

    def get(self, name: str, *keys: Any):
        """
        Метод должен возвращать self.
        Как и все другие методы, встраивается в цепочку выполнения.
        Если в качестве keys указаны несколько ключей, они возвращаются в виде одного словаря.
        Если в качестве keys указан один ключ, он возвращается просто как значение.
        Результат цепочки возвращается всегда как массив, даже если в цепочке всего один вызов get.
        Если name нет в кэше, то возвращается [None].
        Если name есть в кэше, но нет одного из указанных keys - генерируется исключение.
        Если key запрашивается один и его значение в кэше = None, то возвращается ['null'].
        Если запрашиваются несколько ключей и значение каких-то = None, то они так и возвращаются, как None.        
        """
        self._pipe.json().get(name, *keys)
        return self
    
    def delete(self, name: str, key: str = None):
        """Метод должен возвращать self
        """
        self._pipe.json().delete(name, key)
        return self

    def append(self, name: str, key: str, *objs: List[JsonType]):
        """Метод добавляет в массив список объектов.
        Должен возвращать self.
        """
        self._pipe.json().arrappend(name, key, *objs)
        return self

    def index(self, name: str, key: str, obj: JsonType):
        """Метод определяет индекс объекта в массиве.
        Должен возвращать self.
        """
        self._pipe.json().arrindex(name, key, obj)
        return self

    def pop(self, name: str, key: str, index: int):
        """Метод удаляет из массива объект с индексом index.
        Должен возвращать self.
        """
        self._pipe.json().arrpop(name, key, index)
        return self

    async def exec(self):
        """Метод выполняет цепочку команд. Должен возвращать результат выполнения этой цепочки.
        """
        return await self._pipe.execute()
    
    async def reset(self):
        await self._pipe.reset()

    async def close(self):
        await self._client.aclose()