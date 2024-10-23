import json
import ldap
import ldap.modlist
import ldap.dn

from src.common.hierarchy import (
    Hierarchy, CN_SCOPE_ONELEVEL, CN_SCOPE_BASE, CN_SCOPE_SUBTREE
)

class Cache(Hierarchy):

    def __init__(self, url: str, pool_size: int = 10):
        super().__init__(url, pool_size)
        self._cache_node_dn = None

    async def connect(self) -> None:
        await super().connect()

        with self._cm.connection() as conn:
            res = conn.search_s(base=self._base_dn, scope=CN_SCOPE_ONELEVEL,
                filterstr=f"(cn=_cache)",attrlist=['cn'])
            if not res:
                await self.add(attribute_values={"cn": "_cache"})

        self._cache_node_dn = f"cn=_cache,{self._base_dn}"

        return True

    async def get_key(self, key: str, json_loads: bool = False) -> str | dict | None:

        try:
            with self._cm.connection() as conn:
                base_node = f"cn={key},{self._cache_node_dn}"
                res = conn.search_s(base=base_node, scope=CN_SCOPE_BASE,
                    attrlist=["prsJsonConfigString"])
            result = res[0][1]["prsJsonConfigString"][0].decode()
        except:
            return None

        if json_loads:
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return None
        else:
            return result

    async def set_key(self, key: str, value: str | dict | list) -> None:
        new_value = (value, json.dumps(value, ensure_ascii=False))[isinstance(value, (dict, list))]

        cn_bytes = ldap.dn.escape_dn_chars(key)

        modlist = {
            "prsJsonConfigString": [new_value.encode('utf-8')],
            "objectClass": ["prsModelNode".encode('utf-8')],
            "cn": [key.encode('utf-8')]
        }

        add_modlist = ldap.modlist.addModlist(modlist)

        dn = f"cn={cn_bytes},{self._cache_node_dn}"

        with self._cm.connection() as conn:
            try:
                conn.add_s(dn, add_modlist)
            except ldap.ALREADY_EXISTS:
                res = conn.search_s(base=dn, scope=CN_SCOPE_BASE,
                        attrlist=["prsJsonConfigString"])
                modlist = {
                    "prsJsonConfigString": [new_value.encode('utf-8')]
                }
                modify_modlist = ldap.modlist.modifyModlist(res[0][1], modlist)
                conn.modify_s(dn, modify_modlist)


        return None
