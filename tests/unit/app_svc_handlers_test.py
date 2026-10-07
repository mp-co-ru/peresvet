from types import SimpleNamespace

from src.common.app_svc import AppSvc


class _App(AppSvc):
    def __init__(self):
        pass


def test_app_svc_handlers_for_all_nodes_and_specific():
    svc = _App()
    svc._config = SimpleNamespace(nodes=[], hierarchy={"class": "prsTag"})
    svc._handlers = {}
    svc._set_handlers()
    assert "prsTag.model.created" in svc._handlers
    assert "prsTag.model.deleted.*" in svc._handlers
    svc2 = _App()
    svc2._config = SimpleNamespace(nodes=["n1"], hierarchy={"class": "prsTag"})
    svc2._handlers = {}
    svc2._set_handlers()
    assert "prsTag.model.created" not in svc2._handlers
    assert "prsTag.model.updated.n1" in svc2._handlers
