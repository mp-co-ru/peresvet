from base_cache import ABCCache, JsonType
from typing import Union, Dict, Any, List
import redis.asyncio as redis

class RedisCache(ABCCache):
    
    def __init__(self, dsn: str):
        self._pool = redis.ConnectionPool.from_url(dsn)
        self._client = redis.Redis.from_pool(connection_pool=self._pool)
        self._pipe = self._client.pipeline(transaction=True)

    def set(self, name: str, key: str, obj: JsonType, nx: bool = False, xx: bool = False):
        self._pipe.json().set(name=name, path=key, obj=obj, nx=nx, xx=xx)
        return self

    def get(self, name: str, *keys):
        """Метод должен возвращать self.
        Как и все другие методы, встраивается в цепочку выполнения.
        Если в качестве keys указаны несколько ключей, они возвращаются в виде одного словаря.
        Если в качестве keys указан один ключ, он возвращается просто как значение.
        Результат цепочки возвращается всегда как массив, даже если в цепочке всего один вызов get.
        Если name нет в кэше, или в списке ключей keys указан ключ, которого нет в кэше name, то 
        генерируется исключение.
        """
        self._pipe.json().get(name=name, *keys)
        return self
    
    def delete(self, name: str, key: str):
        """Метод должен возвращать self
        """
        self._pipe.json().delete(key=name, path=key)
        return self

    def append(self, name: str, key: str, *objs: List[JsonType]):
        """Метод добавляет в массив список объектов.
        Должен возвращать self.
        """
        self._pipe.json().arrappend(name=name, path=key, *objs)
        return self

    def index(self, name: str, key: str, obj: JsonType):
        """Метод определяет индекс объекта в массиве.
        Должен возвращать self.
        """
        self._pipe.json().arrindex(name=name, path=key, scalar=obj)
        return self

    def pop(self, name: str, key: str, index: int):
        """Метод удаляет из массива объект с индексом index.
        Должен возвращать self.
        """
        self._pipe.json().arrpop(name=name, path=key, index=index)
        return self

    async def exec(self):
        """Метод выполняет цепочку команд. Должен возвращать результат выполнения этой цепочки.
        """
        return await self._pipe.execute()
    
    async def reset(self):
        await self._pipe.reset()
