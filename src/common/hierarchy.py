# Модуль содержит класс для работы с иерархией

from copy import deepcopy
from typing import Any, Tuple, List
import json

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
        self._base_dn : str = None

    async def does_node_exist(self, node: str) -> bool:
        """Проверка существования узла с указанным id.

        Args:
            node (str): id проверяемого узла.

        Returns:
            bool: True - если узел существует, False - иначе.
        """

        with self._cm.connection() as conn:
                res = conn.search_s(base=self._base_dn, scope=CN_SCOPE_SUBTREE,
                    filterstr=f"(entryUUID={node})",attrlist=['cn'])
                if not res:
                    return False

        return True

    async def get_node_dn(self, node: str = None) -> str:
        """Метод определяет DN узла в иерархии по переданному id и
        возвращает его.
        В случае, если base = None, то возвращается DN базового узла
        всей иерархии.

        Args:
            base (str, optional): id узла в форме UUID. По умолчанию - None.

        Returns:
            str: DN узла.

        """

        if not node:
            return self._base_dn

        if self._is_node_id_uuid(node):
            with self._cm.connection() as conn:
                res = conn.search_s(base=self._base_dn, scope=CN_SCOPE_SUBTREE,
                                filterstr=f"(entryUUID={node})",attrlist=['cn'])
                if not res:
                    raise ValueError(f"Узел {node} не найден.")

            return res[0][0]

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
        except Exception:
            return False

        return True

    async def connect(self) -> None:
        """Создание пула коннектов к ldap-серверу.
        URL передаётся при создании нового экземпляра класса ``Hierarchy``\.

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
            retry_delay=1
        )

        self._base_dn = ldap_url.dn
        self._base_id = await self.get_node_id(self._base_dn)

    @staticmethod
    def __form_filterstr(filter_attributes: dict) -> str:
        """Метод формирует из переданных данных строку фильтра для поиска узлов
        в иерархии

        Args:
            filter_attributes (dict): атрибуты со значениями, по которым
            строится фильтр.
            См. :py:func:`hierarchy.Hierarchy.search`

        Returns:
            str: строка фильтра
        """

        filterstr = ""
        for key, values in filter_attributes.items():
            sub_filter = ""
            for value in values:
                if isinstance(value, bool):
                    value = ("FALSE", "TRUE")[value]
                sub_filter = f"{sub_filter}({key}={value})"
            if filterstr:
                filterstr = f"{filterstr}(|{sub_filter})"
            else:
                filterstr = f"(|{sub_filter})"

        filterstr = f"(&{filterstr})"

        return filterstr

    async def search(self, payload: dict) -> List[Tuple[str, str, dict]]:
        """Метод-генератор поиска узлов и чтения их данных.

        Результат - массив кортежей. Каждый кортеж состоит из трёх элементов:
        `id` узла (entryUUID), `dn` узла, словарь из атрибутов и их значений.

        Args:
            payload(dict) -

                .. code:: json

                    {
                        "id": ["first_id", "n_id"],
                        "base": "base for search",
                        "deref": true,
                        "scope": 1,
                        "filter": {
                            "prsActive": [true],
                            "prsEntityType": [1]
                        },
                        "attributes": ["cn", "description"]
                    }

                * id
                    список идентификаторов узлов, данные по которым
                    необходимо получить; если присутствует, то не учитываются ключи
                    ``base``\, ``scope``\, ``filter``\; по умолчанию - None;
                * base
                    id (uuid) или dn базового узла, от которого
                    вести поиск;
                    в случае отстутствия поиск ведётся от корня иерархии; по
                    умолчанию - None;
                * deref
                    флаг разъименования ссылок; по умолчанию - False;
                    .. todo:: Реализовать поведение флага ``deref``\.
                * scope
                    масштаб поиска; возможные значения:

                    * 0 - возвращает данные по одному, указанному в ``base`` узлу;
                    * 1 - поиск среди непосредственных потомков узла;
                    * 2 - поиск по всему дереву;

                * filter
                    данные для формирования фильтра поиска; ``filter``
                    представляет собой словарь, ключами в котором являются имена
                    атрибутов, а значениями - массивы значений; фильтр формируется
                    так: значения атрибутов из массивов объединяются операцией
                    ``или``\, а сами ключи - операцией ``и``\;
                    например, если ключ ``filter`` =

                    .. code:: json

                        {
                            "cn": ["first", "second"],
                            "prsEntityType": [2, 3]
                        }

                    то будет сформирована такая строка фильтра:
                    ``(&(|(cn=first)(cn=second))(|(prsEntityType=1)(prsEntityType=2)))``
                * attributes
                    список атрибутов, значения которых необходимо
                    вернуть; по умолчанию - ``['\*']``


        Returns:
            List[Tuple]: (id, dn, attributes)
        """

        new_payload = deepcopy(payload)
        with self._cm.connection() as conn:

            ids = new_payload.get("id")
            if isinstance(ids, str):
                ids = [ids]
            if ids:
                #filterstr = Hierarchy.__form_filterstr({"entryUUID": ids})
                filterstr = '(|(entryUUID=' + ')(entryUUID='.join(ids) + '))'
                node = self._base_dn
                scope = CN_SCOPE_SUBTREE
            else:
                filterstr = Hierarchy.__form_filterstr(new_payload["filter"])

                id_ = new_payload.get("base")
                # id_ = payload.get("cn")
                if not id_:
                    node = self._base_dn
                else:
                    if self._is_node_id_uuid(id_):
                        node = await self.get_node_dn(new_payload.get("base"))
                        # node = await self.get_node_dn(payload["filter"]["cn"])
                    else:
                        node = id_

                scope = new_payload.get("scope", CN_SCOPE_SUBTREE)
                deref = new_payload.get("deref", True)
                old_deref = conn.deref

                if deref:
                    conn.deref = ldap.DEREF_SEARCHING
                else:
                    conn.deref = ldap.DEREF_NEVER

            return_attributes = new_payload.get("attributes", ["*"])
            id_in_attrs = False
            if 'entryUUID' in return_attributes:
                id_in_attrs = True
            else:
                return_attributes.append('entryUUID')
            
            index_in_attrs = False
            if 'prsIndex' in return_attributes:
                index_in_attrs = True
            else:
                return_attributes.append('prsIndex')

            res = conn.search_s(base=node, scope=scope,
                filterstr=filterstr, attrlist=return_attributes)

            result = []
            for item in res:
                item_data = {
                    key: [value.decode() for value in values] for key, values in item[1].items()
                }

                # поиск не возвращает атрибуты, значение которых = None
                for key in list(set(return_attributes) - set(item_data.keys())):
                    item_data[key] = [None]

                if not id_in_attrs:
                    item_data.pop('entryUUID', None)
                item_data.pop('*', None)

                #yield (item[1]['entryUUID'][0].decode(), item[0], item_data)
                result.append((item[1]['entryUUID'][0].decode(), item[0], item_data))

            def key_sort(val):
                if val[2]["prsIndex"][0] is None:
                    return 0
                return int(val[2]["prsIndex"][0])

            result.sort(key=key_sort)
            if not index_in_attrs:
                for item in result:
                    item[2].pop("prsIndex")

            if not ids:
                conn.deref = old_deref

        return result

    async def add(self, base: str = None, attribute_values: dict = None) -> str:
        """Добавление узла в иерархию.

        Args:
            base (str): None | id | dn узла-родителя
            attr_vals (dict): словарь со значениями атрибутов

        Returns:
            str: id нового узла
        """
        attrs = {}
        if attribute_values:
            attrs = {
                key: values if isinstance(values, list) else [values] for key, values in attribute_values.items()
            }

        if "objectClass" not in attrs.keys():
            attrs["objectClass"] = ["prsModelNode"]

        rename_node = False
        if not (cn := attrs.get("cn")) or not cn[0]:
            rename_node = True
            attrs["cn"] = [str(uuid4())]

        cn_bytes = ldap.dn.escape_dn_chars(attrs['cn'][0])
        base_dn = await self.get_node_dn(base)
        dn = f"cn={cn_bytes},{base_dn}"

        modlist = {}
        for key, values in attrs.items():
            modlist[key] = []
            for value in values:
                new_value = None
                if value is not None:
                    if isinstance(value, bool):
                        if value:
                            new_value = 'TRUE'
                        else:
                            new_value = 'FALSE'
                    elif isinstance(value, (int, float)):
                        new_value = str(value)
                    elif isinstance(value, dict):
                        new_value = json.dumps(value, ensure_ascii=False)
                    else: # str
                        new_value = value

                    new_value = new_value.encode('utf-8')

                modlist[key].append(new_value)

        modlist = ldap.modlist.addModlist(modlist)

        with self._cm.connection() as conn:
            try:
                conn.add_s(dn, modlist)
            except ldap.ALREADY_EXISTS:
                return None

            res = conn.search_s(base=dn, scope=CN_SCOPE_BASE,
                               filterstr='(cn=*)',attrlist=['entryUUID'])
            new_id = res[0][1]['entryUUID'][0].decode()
            if rename_node:
                await self.modify(
                    node=new_id,
                    attr_vals={
                        "cn": [new_id]
                    })

            return new_id

    async def add_alias(self, parent_id: str, aliased_object_id: str, alias_name: str) -> str:
        aliased_object_dn = await self.get_node_dn(aliased_object_id)
        return await self.add(base=parent_id, attribute_values={
            "objectClass": ["alias", "extensibleObject"],
            "aliasedObjectName": [aliased_object_dn],
            "cn": [alias_name]
        })

    async def modify(self, node: str, attr_vals: dict) -> str :
        """Метод изменяет атрибуты узла.
        В случае, если в изменяемых атрибутах присутствует cn (то есть узел
        переименовывается), то метод возвращает новый DN узла.

        Args:
            node (str): id изменяемого узла.
            attr_vals (dict): словарь с новыми значениями атрибутов.

        Returns:
            str: новый DN узла в случае изменения атрибута ``cn``\, иначе - None.
        """

        if not node:
            raise ValueError("Необходимо указать узел для изменения.")
        if not attr_vals:
            raise ValueError("Необходимо указать изменяемые атрибуты.")

        real_base = await self.get_node_dn(node)

        cn = attr_vals.pop("cn", None)

        attrs = {}
        for key, value in attr_vals.items():
            # косяк python-ldap'а:
            # если передавать для перезаписи просто пустую строку - будет вылетать ошибка
            if value is None or (isinstance(value, str) and not value):
                attrs[key] = [None]
            elif isinstance(value, list):
                attrs[key] = [str(val).encode("utf-8") for val in value]
            elif isinstance(value, bool):
                attrs[key] = [("FALSE".encode("utf-8"), "TRUE".encode("utf-8"))[value]]
            elif isinstance(value, dict):
                attrs[key] = [json.dumps(value, ensure_ascii=False).encode("utf-8")]
            else:
                attrs[key] = [str(value).encode("utf-8")]

        with self._cm.connection() as conn:
            if attrs:
                res = conn.search_s(real_base, CN_SCOPE_BASE, None, [key for key in attrs.keys()])
                modlist = ldap.modlist.modifyModlist(res[0][1], attrs)
                conn.modify_s(real_base, modlist)                

            if cn:
                res = conn.search_s(real_base, CN_SCOPE_BASE, None, ['entryUUID'])
                id_ = res[0][1]['entryUUID'][0].decode()

                if isinstance(cn, list):
                    cn = cn[0]
                new_rdn = f'cn={ldap.dn.escape_dn_chars(cn)}'
                conn.rename_s(real_base, new_rdn)
                res = conn.search_s(self._base_dn, CN_SCOPE_SUBTREE, f'(entryUUID={id_})')

                return res[0][0]

    async def move(self, node: str, new_parent: str):
        """Метод перемещает узел по дереву.

        Args:
            node (str): id перемещаемого узла
            new_parent (str): id нового родительского узла
        """

        base_dn = await self.get_node_dn(node)
        new_parent_dn = await self.get_node_dn(new_parent)

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

        node_dn = await self.get_node_dn(node)

        def recursive_delete(conn, base_dn):
            search = conn.search_s(base_dn, CN_SCOPE_ONELEVEL)
            for dn, _ in search:
                recursive_delete(conn, dn)

            conn.delete_s(base_dn)

        with self._cm.connection() as conn:
            old_deref = conn.deref
            conn.deref = ldap.DEREF_NEVER

            recursive_delete(conn, node_dn)

            conn.deref = old_deref

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
                res = conn.search_s(base=self._base_dn, scope=CN_SCOPE_SUBTREE,
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

        p = ldap.dn.dn2str(ldap.dn.str2dn(res_node)[1:])
        with self._cm.connection() as conn:
            res = conn.search_s(base=p, scope=CN_SCOPE_BASE,
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
            str: значение атрибута objectClass (одно значение, исключая ``top``\)
        """
        with self._cm.connection() as conn:
            res = conn.search_s(base=self._base_dn, scope=CN_SCOPE_SUBTREE,
                filterstr=f"(entryUUID={node})",attrlist=['objectClass'])
            if not res:
                raise ValueError(f"Узел {node} не найден.")

            obj_classes = res[0][1]["objectClass"]
            try:
                obj_classes.remove(b'top')
            except:
                pass
            return obj_classes[0].decode()

    async def get_node_id(self, node_dn: str) -> str:
        with self._cm.connection() as conn:
            res = conn.search_s(base=node_dn, scope=CN_SCOPE_BASE,
                    filterstr="(cn=*)", attrlist=['entryUUID'])
            if not res:
                return None

            return res[0][1]['entryUUID'][0].decode()
