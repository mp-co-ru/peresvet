# класс для работы с иерархией

from typing import Any, Tuple, List

from uuid import uuid4, UUID

import ldap
import ldap.modlist
import ldap.dn
import ldapurl
from ldappool import ConnectionManager

CN_SCOPE_BASE = ldap.SCOPE_BASE
CN_SCOPE_ONELEVEL = ldap.SCOPE_ONELEVEL
CN_SCOPE_SUBTREE = ldap.SCOPE_SUBTREE

class Hierarchy:
    """Класс для работы с иерархической моделью.

    Args:
        url (str): URL для связи с ldap-сервером;
        pool_size (int, optional): размер пула коннектов. По умолчанию - 10.

    """

    def __init__(self, url: str, pool_size: int = 10):
        self.url : str = url
        self.pool_size : int = pool_size
        self._cm : ConnectionManager = None
        self._base : str = None

    async def _does_node_exist(self, node: str) -> bool:
        """Проверка существования узла с указанным id.

        Args:
            node (str): id проверяемого узла.

        Returns:
            bool: True - если узел существует, False - иначе.
        """

        with self._cm.connection() as conn:
                res = conn.search_s(base=self._base, scope=CN_SCOPE_SUBTREE,
                    filterstr=f"(entryUUID={node})",attrlist=['cn'])
                if not res:
                    return False

        return True

    async def _get_base(self, base: str = None) -> str:
        """Метод определяет DN узла в иерархии по переданному id и
        возвращает его.
        В случае, если base = None, то возвращается DN базового узла
        всей иерархии.

        Args:
            base (str, optional): id узла в форме UUID. По умолчанию - None.

        Returns:
            str: DN узла.

        """

        if not base:
            return self._base

        if self._is_node_id_uuid(base):
            with self._cm.connection() as conn:
                res = conn.search_s(base=self._base, scope=CN_SCOPE_SUBTREE,
                                filterstr=f"(entryUUID={base})",attrlist=['cn'])
                if not res:
                    raise ValueError(f"Узел {base} не найден.")

            return res[0][0]

        try:
            UUID(base)


        except ValueError as _:
            return base

    def _is_node_id_uuid(self, node: str) -> bool:
        """Проверка того, что идентификатор узла
        имеет формат UUID.

        Args:
            node (str): проверяемый идентификатор узла

        Returns:
            bool: True - идентификатор в правильной форме, False - иначе.

        """

        try:
            UUID(node)
        except ValueError:
            return False

        return True

    def connect(self) -> None:
        """Создание пула коннектов к lda-серверу.
        URL передаётся при создании нового экземпляра класса ``Hierarchy``.

        Количество попыток восстановления связи при разрыве - 10. Время
        между попытками - 0.3с.
        """

        ldap_url = ldapurl.LDAPUrl(self.url)

        self._cm = ConnectionManager(
            uri=f"ldap://{ldap_url.hostport}",
            bind=ldap_url.who,
            passwd=ldap_url.cred,
            size=self.pool_size,
            retry_max=10,
            retry_delay=0.3
        )

        self._base = ldap_url.dn

    async def search(self, base: str = None, filter_str: str = None,
        scope: Any = CN_SCOPE_SUBTREE,
        attr_list: list[str] = None) -> List[Tuple]:
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
            scope (Any): уровень поиска
            filter (str): строка фильтра поиска
            attr_list (list[str]): список возвращаемых атрибутов

        Returns:
            List[Tuple]: [(id, dn, attrs)]
        """

        if not attr_list:
            attr_list = ['*']

        attr_list.append('entryUUID')

        with self._cm.connection() as conn:

            node = await self._get_base(base)

            res = conn.search_s(base=node, scope=scope,
                                filterstr=filter_str,attrlist=attr_list)
            for item in res:
                item = (item[1]['entryUUID'], item[0], {
                    key: [value.decode() for value in values] for key, values in item[1]
                })

                yield item

    async def add(self, base: str = None, attr_vals: dict = None) -> str:
        """Добавление узла в иерархию.

        Args:
            base (str): None | id | dn узла-родителя
            attr_vals (dict): словарь со значениями атрибутов

        Returns:
            str: id нового узла
        """
        #TODO: если в атрибутах отсутствует ``cn``, то в его качестве принимается id вновь созданного узла.

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
        dn = f"cn={cn_bytes},{await self._get_base(base)}"

        modlist = {key:[v.encode("utf-8") if isinstance(v, str) else v for v in values] for key, values in attrs.items()}
        modlist = ldap.modlist.addModlist(modlist)

        with self._cm.connection() as conn:
            try:
                conn.add_s(dn, modlist)
            except ldap.ALREADY_EXISTS:
                return None

            res = conn.search_s(base=dn, scope=CN_SCOPE_BASE,
                                filterstr='(cn=*)',attrlist=['entryUUID'])
            return res[0][1]['entryUUID']

    async def modify(self, node: str, attr_vals: dict) -> str :
        """Метод изменяет атрибуты узла.
        В случае, если в изменяемых атрибутах присутствует cn (то есть узел
        переименовывается), то метод возвращает новый DN узла.

        Args:
            node (str): id изменяемого узла. По умолчанию - None.
            attr_vals (dict): словарь с новыми значениями атрибутов.

        Returns:
            str: новый DN узла в случае изменения атрибута ``cn``, иначе - None.
        """

        if not node:
            raise ValueError("Необходимо указать узел для изменения.")
        if not attr_vals:
            raise ValueError("Необходимо указать изменяемые атрибуты.")

        real_base = await self._get_base(node)

        cn = attr_vals.pop("cn", None)

        attrs = {
            key: value if isinstance(value, list) else [value] for key, value in attr_vals.items()
        }
        attrs = {
            key:[v.encode("utf-8") if isinstance(v, str) else v for v in values] for key, values in attrs.items()
        }

        with self._cm.connection() as conn:
            res = conn.search_s(real_base, CN_SCOPE_BASE, None, [key for key in attrs.keys()])
            modlist = ldap.modlist.modifyModlist(res[0][1], attrs)
            conn.modify_s(real_base, modlist)

            if cn:
                res = conn.search_s(real_base, CN_SCOPE_BASE, None, ['entryUUID'])
                id_ = res[0][1]['entryUUID']

                if isinstance(cn, list):
                    cn = cn[0]
                new_rdn = f'cn={ldap.dn.escape_dn_chars(cn)}'
                conn.rename_s(real_base, new_rdn)

                res = conn.search_s(self._base, CN_SCOPE_SUBTREE, f'(entryUUID={id_})')

                return res[0][0]

    async def move(self, node: str, new_parent: str):
        """Метод перемещает узел по дереву.

        Args:
            node (str): id перемещаемого узла
            new_parent (str): id нового родительского узла
        """

        base_dn = await self._get_base(node)
        new_parent_dn = await self._get_base(new_parent)

        rdn = ldap.dn.explode_dn(base_dn,flags=ldap.DN_FORMAT_LDAPV3)[0]

        with self._cm.connection() as conn:
            conn.rename_s(base_dn, rdn, new_parent_dn)

    async def delete(self, node: str):
        """Метод удаляет из ерархии узел и всех его потомков.

        Args:
            node (str): id удаляемого узла.
        """
        if not node:
            raise ValueError('Нельзя удалять корневой узел иерархии')

        node_dn = await self._get_base(node)

        with self._cm.connection() as conn:
            conn.delete_s(node_dn)

    async def get_parent(self, node: str) -> Tuple[str, str]:
        """Метод возвращает для узла ``node`` id(guid) и dn
        родительского узла.

        Args:

            node (str): id или dn узла, родителя которого необходимо найти.

        Returns:

            (str, str): id(guid) и dn родительского узла.

        """
        res_node = None
        try:
            UUID(node)
            with self._cm.connection() as conn:
                res = conn.search_s(base=self._base, scope=CN_SCOPE_SUBTREE,
                                filterstr=f"(entryUUID={node})",attrlist=['cn'])
                if not res:
                    raise ValueError(f"Узел {node} не найден.")

                res_node = res[0][0]

        except ValueError as ex:
            if not ldap.dn.is_dn(node):
                raise ValueError(
                    f"Строка {node} не является корректным идентификатором узла."
                ) from ex
            res_node = node

        rdns = ldap.explode_dn(res_node)
        p = ','.join(rdns[1:])
        if not p:
            return (None, None)

        with self._cm.connection() as conn:
            res = conn.search_s(base=p, scope=CN_SCOPE_ONELEVEL,
                attrlist=['entryUUID'])
            if not res:
                raise ValueError("Родительский узел не найден.")

        return (res[0][1]['entryUUID'][0].decode('utf-8'), res[0][0])

    async def get_node_class(self, node: str) -> str:
        """Возвращает класс узла

        Args:
            node (str): id узла

        Raises:
            ValueError: в случае отсутствия узла генерирует исключение

        Returns:
            str: значение атрибута objectClass (одно значение, исключая ``top``)
        """
        with self._cm.connection() as conn:
            res = conn.search_s(base=self._base, scope=CN_SCOPE_SUBTREE,
                filterstr=f"(entryUUID={node})",attrlist=['objectClass'])
            if not res:
                raise ValueError(f"Узел {node} не найден.")

            obj_classes = res[0][1]["objectClass"]
            obj_classes.remove(b'top')
            return obj_classes[0].decode()
