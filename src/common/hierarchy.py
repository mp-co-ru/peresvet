# класс для работы с иерархией

from typing import Any

from uuid import uuid4, UUID

import ldap
import ldap.modlist
import ldap.dn
from ldappool import ConnectionManager

CN_SCOPE_BASE = ldap.SCOPE_BASE
CN_SCOPE_ONE_LEVEL = ldap.SCOPE_ONE_LEVEL
CN_SCOPE_SUBTREE = ldap.SCOPE_SUBTREE

class Hierarchy:
    """Класс для работы с иерархической моделью.
    """
    def __init__(self, base: str, uri: str, uid: str = None, pwd: str = None,
                 pool_size: int = 10):
        """_summary_

        Args:
            uri (str): _description_
            uid (str, optional): _description_. Defaults to None.
            pwd (str, optional): _description_. Defaults to None.
            pool_size (int, optional): _description_. Defaults to 10.
        """
        self._base = base
        self._cm = ConnectionManager(uri=uri, bind=uid,
                                     passwd=pwd, size=pool_size)

    def _get_base(self, base: str = None) -> str:
        """Метод возвращает dn базового узла для всех операций

        Args:
            base (str, optional): _description_. Defaults to None.

        Returns:
            str: _description_
        """

        if not base:
                return self._base
        else:
            try:
                UUID(base)

                with self._cm.connection() as conn:
                    res = conn.search_s(base=self._base, scope=CN_SCOPE_SUBTREE,
                                    filterstr=f"(entryUUID={base})",attrlist=['cn'])
                    if not res:
                        raise ValueError(f"Узел {base} не найден.")

                return res[0][0]
            except ValueError as ex:
                return base

    async def search(self, base: str = None, filter: str = None,
                     scope: Any = CN_SCOPE_SUBTREE, attr_list: list[str] = []) -> tuple:
        """Метод-генератор возвращает результат поиска узлов в иерархии.
        Результат - массив кортежей. Каждый кортеж состоит из трёх элементов:
        `id` узла (entryUUID), `dn` узла, словарь из атрибутов и их значений.

        Идентификатором экземпляра сущности (то есть любого узла) в иерархии,
        используемым в платформе, является его entryUUID.
        Поэтому аргумент `base` может принимать следующие значения:
        None - поиск ведётся от главного узла иерархии, задаваемого при её
               создании;
        uid  - в этом случае сначала ищется узел с указанным uid, затем от
               него ведётся поиск;
        dn   - поиск ведётся от указанного dn.

        Args:
            base (str): None | uid | dn
            scope (Any): _description_
            filter (str): _description_
            attr_list (list[str]): _description_

        Returns:
            tuple: [(id, dn, attrs)]
        """

        if attr_list is None or not attr_list:
            attr_list = ['*']

        attr_list.append('entryUUID')

        with self._cm.connection() as conn:

            res = conn.search_s(base=self._get_base(base), scope=scope,
                                filterstr=filter,attrlist=attr_list)
            for item in res:
                item = (item[1]['entryUUID'], item[0], {
                    key: [value.decode() for value in values] for key, values in item[1]
                })

                yield item

    async def add(self, base: str = None, attr_vals: dict = {}) -> str:
        """Добавление узла в иерархию

        Args:
            base      (str): None | id | dn узла-родителя
            attr_vals (dict): словарь со значениями атрибутов

        Returns:
            str: id нового узла
        """
        if not attr_vals:
            raise ValueError((
                "Для создания узла необходимо задать его атрибуты.",
                "Как минимум, cn."
            ))

        cn = attr_vals.get("cn")
        if not cn:
            raise ValueError(
                "В списке атрибутов обязательно должен быть задан cn."
            )

        attrs = {
            key: values if isinstance(values, list) else [values] for key, values in attr_vals.items()
        }

        cn_bytes = ldap.dn.escape_dn_chars(attrs['cn'][0])
        dn = f"cn={cn_bytes},{self._get_base(base)}"

        modlist = {key:[v.encode("utf-8") if type(v) == str else v for v in values] for key, values in attrs.items()}
        modlist = ldap.modlist.addModlist(modlist)

        with self._cm.connection() as conn:
            try:
                conn.add_s(dn, modlist)
            except ldap.ALREADY_EXISTS as ex:
                return None

            res = conn.search_s(base=dn, scope=CN_SCOPE_BASE,
                                filterstr='(cn=*)',attrlist=['entryUUID'])
            return res[0][1]['entryUUID']

    async def modify(self, base: str = None, attr_vals: dict = {}) -> str :
        '''
