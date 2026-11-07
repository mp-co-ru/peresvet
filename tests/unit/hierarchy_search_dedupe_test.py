from src.common.hierarchy import dedupe_ldap_search_hits


def test_ldap_search_hits_keep_the_first_entry_for_each_id():
    first = ("conn-1", "cn=line,cn=connectors,cn=prs", {"cn": ["Линия Цесис"]})
    duplicate = ("conn-1", "cn=alias,cn=connectors,cn=prs", {"cn": ["Линия Цесис"]})
    other = ("conn-2", "cn=video,cn=connectors,cn=prs", {"cn": ["Видео1"]})

    assert dedupe_ldap_search_hits([first, duplicate, other, other]) == [first, other]


def test_ldap_search_hits_without_duplicates_stay_in_order():
    items = [
        ("a", "cn=a", {}),
        ("b", "cn=b", {}),
    ]

    assert dedupe_ldap_search_hits(items) == items
    assert dedupe_ldap_search_hits([]) == []
