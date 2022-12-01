#import ldap3
from ldap3 import SCHEMA, Server, Connection, SAFE_SYNC, SUBTREE, DEREF_NEVER, ALL_ATTRIBUTES, ObjectDef, Reader, Entry, AttrDef

'''
server = Server(host='localhost', port=3890, get_info=SCHEMA)
read_conn = Connection(server, user='cn=admin,cn=prs',
    password='Peresvet21', client_strategy=SAFE_SYNC, read_only=True,
    pool_name="read_ldap", pool_size=20, auto_bind=True)

status, result, response, some = read_conn.search(search_base='cn=prs',
                search_filter='(cn=some)', search_scope=SUBTREE, dereference_aliases=DEREF_NEVER, attributes=[ALL_ATTRIBUTES])

print("status: {}\n\n".format(status))
print("result: {}\n\n".format(result))
print("response: {}\n\n".format(response))
print("some: {}\n\n".format(some))
'''

# additional string

server = Server(host='localhost', port=389, get_info=SCHEMA)
read_conn = Connection(server, user='cn=admin,cn=prs',
    password='Peresvet21', client_strategy=SAFE_SYNC, read_only=True,
    pool_name="read_ldap", pool_size=20, auto_bind=True)

o = ObjectDef('prsTag', read_conn)
r = Reader(read_conn, o, 'cn=tags,cn=prs', get_operational_attributes=True)
r.search()
ent = r.entries[0]
#print(str(r.entries[0]))
print(type(o.prsValueScale.oid_info.syntax))
