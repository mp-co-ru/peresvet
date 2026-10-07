import pytest

from src.common.local_cache import LocalCache


def test_local_cache_set_get_append_index_pop_delete():
    c = LocalCache()
    assert c._set(name="n", key="$", obj={"a": 1, "arr": [1]}, nx=False, xx=False) is True
    assert c._get("n") == {"a": 1, "arr": [1]}
    assert c._get("n", "a") == 1
    assert c._get("n", "a", "arr") == {"a": 1, "arr": [1]}
    assert c._set(name="n", key="b", obj=2, nx=False, xx=False) is True
    assert c._append("n", "arr", 3) is True
    assert c._index("n", "arr", 1) == 0
    assert c._pop("n", "arr", 0) is True
    assert c.data["n"]["arr"] == [3]
    assert c._delete("n", "b") is True
    assert "b" not in c.data["n"]


def test_local_cache_nx_xx_flags():
    c = LocalCache()
    with pytest.raises(Exception):
        c._set(name="n", key="$", obj=1, nx=True, xx=True)
    assert c._set(name="n", key="$", obj={"k": 1}, nx=True, xx=False) is True
    assert c._set(name="n", key="$", obj={"k": 2}, nx=True, xx=False) is None
    assert c._set(name="n", key="x", obj=1, nx=True, xx=False) is True
    assert c._set(name="n", key="x", obj=2, nx=True, xx=False) is None
    with pytest.raises(Exception):
        c._set(name="missing", key="x", obj=1, nx=True, xx=False)
    assert c._set(name="missing", key="$", obj=1, xx=True, nx=False) is None
    assert c._set(name="n", key="$", obj={"k": 9}, xx=True, nx=False) is True
    assert c._set(name="n", key="y", obj=3, xx=True, nx=False) is True
    assert c._set(name="n", key="y", obj=4, xx=True, nx=False) is None
    c2 = LocalCache()
    with pytest.raises(Exception):
        c2._set(name="z", key="child", obj=1, nx=False, xx=False)


def test_local_cache_chain_and_reset():
    c = LocalCache()
    assert c.set("n", "$", {"a": 1}) is c
    assert c.get("n", "a") is c
    assert c.delete("n", "a") is c
    assert c.append("n", "a", 1) is c
    assert c.index("n", "a", 1) is c
    assert c.pop("n", "a", 0) is c
    assert len(c.command_chain) == 6

    async def run():
        await c.reset()
        await c.close()

    import asyncio
    asyncio.run(run())
    assert c.command_chain == []
