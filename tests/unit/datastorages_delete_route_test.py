def _methods(router) -> set[str]:
    found: set[str] = set()
    for route in router.routes:
        found.update(getattr(route, "methods", set()) or set())
    return found


def test_data_storages_delete_route_is_registered():
    from src.services.dataStorages.api_crud.dataStorages_api_crud_svc import router
    from src.services.dataStorages.api_crud.dataStorages_api_crud_v2_router import (
        router_v2,
    )

    assert "DELETE" in _methods(router)
    assert "DELETE" in _methods(router_v2)
