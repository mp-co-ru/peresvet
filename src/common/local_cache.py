from src.common.base_cache import ABCCache, JsonType
from typing import Any, List

class LocalCache(ABCCache):
    
    def __init__(self, dsn: str = None):
        self.data = {}
        self.command_chain = []

    def set(self, name: str, key: str = "$", obj: JsonType = {}, nx: bool = False, xx: bool = False):
        args = {**locals()}
        args.pop("self")
        self.command_chain.append({"func": self._set, "kwargs": args, "args": ()})
        return self
        
    def _set(self, **kwargs):
        
        if kwargs['nx'] and kwargs['xx']:
            raise Exception("Нельзя использовать одновременно оба флага nx и xx.")
        
        if kwargs['nx']:
            if kwargs['key'] == "$":
                if self.data.get(kwargs['name']) is None:
                    self.data[kwargs['name']] = kwargs['obj']
                    return True
                return None
                
            else:
                if self.data.get(kwargs['name']) is None:
                    raise Exception("Узел можно создавать только в корне.")
                else:
                    if self.data[kwargs['name']].get(kwargs['key']) is None:
                       self.data[kwargs['name']][kwargs['key']] = kwargs['obj']
                       return True
                    else:
                        return None

        if kwargs['xx']:
            if kwargs['key'] == "$":
                if self.data.get(kwargs['name']) is None:
                    return None
                
                self.data[kwargs['name']] = kwargs['obj']
                return True
                
            else:
                if self.data.get(kwargs['name']) is None:
                    return None
                else:
                    if self.data[kwargs['name']].get(kwargs['key']) is None:
                        self.data[kwargs['name']][kwargs['key']] = kwargs['obj']
                        return True
                    else:
                        return None

        if self.data.get(kwargs['name']) is None:
            if kwargs['key'] != "$":
                raise Exception("Узел можно создавать только в корне.")
            self.data[kwargs['name']] = kwargs['obj']
            return True

        self.data[kwargs['name']][kwargs['key']] = kwargs['obj']

        return True

    def get(self, name: str, *keys: Any):

        self.command_chain.append(
            {
                "func": self._get,
                "kwargs": {"name": name},
                "args": keys
            }
        )
        return self
    
    def _get (self, name: str, *args):
        
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
        if len(args) == 0:
            return self.data.get(name)
        if len(args) == 1:
            return self.data[name].get(args[0])
        
        return {arg: self.data[name].get(arg) for arg in args}
    
    def delete(self, name: str, key: str = None):
        """Метод должен возвращать self
        """
        self.command_chain.append(
            {
                "func": self._delete, 
                "args": {
                    "name": name,
                    "key": key
                }
            }
        )
        return self
    
    def _delete(self, name: str, key: str = None):
        self.data[name].pop(key)
        return True

    def append(self, name: str, key: str, *objs: List[JsonType]):
        args = {**locals()}
        args.pop("self")
        self.command_chain.append({"func": self._append, "kwargs": args, "args": None})
        return self

    def _append(self, name: str, key: str, *objs: List[JsonType]):
        """Метод добавляет в массив список объектов.
        Должен возвращать self.
        """
        self.data[name][key].append(*objs)
        return True

    def index(self, name: str, key: str, obj: JsonType):
        args = {**locals()}
        args.pop("self")
        self.command_chain.append({"func": self._index, "kwargs": args, "args": None})
        return self

    def _index(self, name: str, key: str, obj: JsonType):
        """Метод определяет индекс объекта в массиве.
        Должен возвращать self.
        """
        return self.data[name][key].index(obj)

    def pop(self, name: str, key: str, index: int):
        args = {**locals()}
        args.pop("self")
        self.command_chain.append({"func": self._pop, "kwargs": args, "args": None})
        return self

    def _pop(self, name: str, key: str, index: int):
        """Метод удаляет из массива объект с индексом index.
        Должен возвращать self.
        """
        self.data[name][key].pop(index)
        return True

    async def exec(self):
        """Метод выполняет цепочку команд. Должен возвращать результат выполнения этой цепочки.
        """
        res = []
        for command in self.command_chain:
            res.append(command.func(*command["args"], **command["kwargs"]))

        return res
    
    async def reset(self):
        self.command_chain = []

    async def close(self):
        return