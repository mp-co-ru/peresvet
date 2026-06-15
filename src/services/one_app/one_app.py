"""Модуль приложения, включающий сервисы:
1) чтение/запись данных,
2) база только PostgreSQL,
3) методы,
4) коннекторы поставляют данные в платформу.
Нет функций CRUD ни для каких сущностей.
"""
import sys
import os
from fastapi import FastAPI, APIRouter
from starlette.routing import Mount
from contextlib import asynccontextmanager

uvicorn = None
try:
    import uvicorn
except ModuleNotFoundError as _:
    pass

sys.path.append(".")

from src.common.authorization import AuthorizationContextMiddleware

# v2 services are optional (feature flag)
ENABLE_V2 = os.environ.get("PRS_ENABLE_V2", "").strip().lower() in ("1", "true", "yes", "on")

# alerts ----------------------------------------------------------------------
# alerts api crud
from src.services.alerts.api_crud.alerts_api_crud_svc \
    import (
        app as alerts_api_crud,
        router as alerts_api_crud_router
    )
# alerts_app
from src.services.alerts.app.alerts_app_svc \
    import (
        app as alerts_app
    )
# alerts_app_api
from src.services.alerts.app_api.alerts_app_api_svc \
    import (
        app as alerts_app_api,
        router as alerts_app_api_router
    )
# alerts_model_crud
from src.services.alerts.model_crud.alerts_model_crud_svc \
    import (
        app as alerts_model_crud
    )
# -----------------------------------------------------------------------------
# connectors ------------------------------------------------------------------
from src.services.connectors.api_crud.connectors_api_crud_svc \
    import (
        app as connectors_api_crud,
        router as connectors_api_crud_router
    )

# connectros_model
from src.services.connectors.model_crud.connectors_model_crud_svc \
    import (
        app as connectors_model_crud
    )

from src.services.connectors.app_api.connectors_app_api_svc import (
    app as connectors_app_api,
    router as connectors_app_api_router
)

# connectors_app
from src.services.connectors.app.connectors_mqtt_app_svc \
    import (
        app as connectors_app
    )
# -----------------------------------------------------------------------------

# dataStorages ----------------------------------------------------------------
from src.services.dataStorages.api_crud.dataStorages_api_crud_svc \
    import (
        app as dataStorages_api_crud,
        router as dataStorages_api_crud_router
    )

# dataStorages_api_crud v2 router (operations/integrational extensions)
dataStorages_api_crud_router_v2: APIRouter | None = None
if ENABLE_V2:
    from src.services.dataStorages.api_crud.dataStorages_api_crud_v2_router import (
        router_v2 as dataStorages_api_crud_router_v2,
    )

# dataStorages_model_crud (v1 by default; v2 optional)
if ENABLE_V2:
    from src.services.dataStorages.model_crud.dataStorages_model_crud_v2_svc import (
        app as dataStorages_model_crud,
    )
else:
    from src.services.dataStorages.model_crud.dataStorages_model_crud_svc import (
        app as dataStorages_model_crud,
    )

# postgresql
from src.services.dataStorages.app.postgresql.dataStorages_app_postgresql_svc \
    import (
        app as postgre_app
    )

# integrational (v2 feature; optional)
integrational_relational_app = None
if ENABLE_V2:
    from src.services.dataStorages.app.integrational.dataStorages_app_integrational_relational_svc import (
        app as integrational_relational_app,
    )

# -----------------------------------------------------------------------------

# methods ---------------------------------------------------------------------
from src.services.methods.api_crud.methods_api_crud_svc \
    import (
        app as methods_api_crud,
        router as methods_api_crud_router
    )

# methods model crud
from src.services.methods.model_crud.methods_model_crud_svc \
    import (
        app as methods_model_crud
    )

# methods app
from src.services.methods.app.methods_app_svc \
    import (
        app as methods_app
    )
# -----------------------------------------------------------------------------


# objects ---------------------------------------------------------------------
# objects_api_crud
from src.services.objects.api_crud.objects_api_crud_svc \
    import (
        app as objects_api_crud,
        router as objects_api_crud_router
    )

# objects_model_crud
from src.services.objects.model_crud.objects_model_crud_svc \
    import (
        app as objects_model_crud
    )

# -----------------------------------------------------------------------------

# schedules ---------------------------------------------------------------------
# schedules_api_crud
from src.services.schedules.api_crud.schedules_api_crud_svc \
    import (
        app as schedules_api_crud,
        router as schedules_api_crud_router
    )

# schedules_model_crud
from src.services.schedules.model_crud.schedules_model_crud_svc \
    import (
        app as schedules_model_crud
    )
# schedules_app
from src.services.schedules.app.schedules_app_svc \
    import (
        app as schedules_app
    )

# -----------------------------------------------------------------------------

# tags ------------------------------------------------------------------------
# tags_api_crud
from src.services.tags.api_crud.tags_api_crud_svc \
    import (
        app as tags_api_crud,
        router as tags_api_crud_router
    )
# tags_model_crud
from src.services.tags.model_crud.tags_model_crud_svc \
    import (
        app as tags_model_crud
    )
# tags app
from src.services.tags.app.tags_app_svc \
    import app as tags_app
# tags app api
from src.services.tags.app_api.tags_app_api_svc \
    import (
        app as tags_app_api,
        router as tags_app_api_router
    )
# -----------------------------------------------------------------------------

# datafunc ----------------------------------------------------------------------
# datafunc app api
from src.services.tags.datafunc_app_api.datafunc_app_api_svc \
    import (
        app as datafunc_app_api,
        router as datafunc_app_api_router
    )
# -----------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.common.runtime_flags import set_platform_shutting_down

    set_platform_shutting_down(False)
    for route in app.router.routes:
        if isinstance(route, Mount):
            sub_router = getattr(route.app, "router", None)
            if sub_router is not None:
                await sub_router.startup()
    yield
    set_platform_shutting_down(True)
    for route in app.router.routes:
        if isinstance(route, Mount):
            sub_router = getattr(route.app, "router", None)
            if sub_router is not None:
                await sub_router.shutdown()

# для привязки подприложений необходимо создать базовое приложение
app = FastAPI(lifespan=lifespan, title="МПК-Пересвет")
app.add_middleware(AuthorizationContextMiddleware)
api_router = APIRouter(prefix="")

# монтирование роутеров =======================================================

# alerts ----------------------------------------------------------------------
# alerts_api_crud
api_router.include_router(router=alerts_api_crud_router)
# alerts_app_api
api_router.include_router(router=alerts_app_api_router)
# -----------------------------------------------------------------------------

# connectors ------------------------------------------------------------------
# connectors_api_crud
api_router.include_router(router=connectors_api_crud_router)
# connectors_app_api
api_router.include_router(router=connectors_app_api_router)
# -----------------------------------------------------------------------------

# dataStorages ----------------------------------------------------------------
# dataStorages_api_crud
api_router.include_router(router=dataStorages_api_crud_router)
if ENABLE_V2 and dataStorages_api_crud_router_v2 is not None:
    api_router.include_router(router=dataStorages_api_crud_router_v2)
# -----------------------------------------------------------------------------

# methods ---------------------------------------------------------------------
# methods_api_crud
api_router.include_router(router=methods_api_crud_router)
# -----------------------------------------------------------------------------

# objects ---------------------------------------------------------------------
# objects_api_crud
api_router.include_router(router=objects_api_crud_router)
# -----------------------------------------------------------------------------

# schedules ---------------------------------------------------------------------
# schedules_api_crud
api_router.include_router(router=schedules_api_crud_router)
# -----------------------------------------------------------------------------
# tags ------------------------------------------------------------------------
# tags_api_crud
api_router.include_router(router=tags_api_crud_router)
# tags_app_api
api_router.include_router(router=tags_app_api_router)
# -----------------------------------------------------------------------------

# datafunc ----------------------------------------------------------------------
# datafunc_app_api
api_router.include_router(router=datafunc_app_api_router)
# -----------------------------------------------------------------------------
# =============================================================================

app.include_router(api_router)

# монтирование приложений =====================================================

# connectors ------------------------------------------------------------------
# connectors_api_crud
app.mount(path="/", app=connectors_api_crud)
# connectors_app
app.mount(path="/", app=connectors_app)
# connectors_model_crud
app.mount(path="/", app=connectors_model_crud)
# connectors_app_api
app.mount(path="/", app=connectors_app_api)
# -----------------------------------------------------------------------------

# dataStorages ----------------------------------------------------------------
# dataStorages_api_crud
app.mount(path="/", app=dataStorages_api_crud)
# dataStorages_model_crud
app.mount(path="/", app=dataStorages_model_crud)
# postgresql
app.mount(path="/", app=postgre_app)
# integrational relational (prsEntityTypeCode=2)
if ENABLE_V2 and integrational_relational_app is not None:
    app.mount(path="/", app=integrational_relational_app)
# -----------------------------------------------------------------------------

# methods ---------------------------------------------------------------------
# methods_api_crud
app.mount(path="/", app=methods_api_crud)
# methods_model_crud
app.mount(path="/", app=methods_model_crud)
# methods app
app.mount(path="/", app=methods_app)
# -----------------------------------------------------------------------------

# objects ---------------------------------------------------------------------
# objects_api_crud
app.mount(path="/", app=objects_api_crud)
# objects_model_crud
app.mount(path="/", app=objects_model_crud)
# -----------------------------------------------------------------------------

# tags ------------------------------------------------------------------------
# tags_api_crud
app.mount(path="/", app=tags_api_crud)
# tags_model_crud
app.mount(path="/", app=tags_model_crud)
# tags_app
app.mount(path="/", app=tags_app)
# tags_app_api
app.mount(path="/", app=tags_app_api)
# -----------------------------------------------------------------------------

# alerts ----------------------------------------------------------------------
# alerts_api_crud
app.mount(path="/", app=alerts_api_crud)
# alerts_app
app.mount(path="/", app=alerts_app)
# alerts_app_api
app.mount(path="/", app=alerts_app_api)
# alerts_model_crud
app.mount(path="/", app=alerts_model_crud)
# -----------------------------------------------------------------------------

# schedules ---------------------------------------------------------------------
# schedules_api_crud
app.mount(path="/", app=schedules_api_crud)
# schedules_model_crud
app.mount(path="/", app=schedules_model_crud)
# schedules_app
app.mount(path="/", app=schedules_app)
# -----------------------------------------------------------------------------

# datafunc ----------------------------------------------------------------------
app.mount(path="/", app=datafunc_app_api)
# -----------------------------------------------------------------------------
# =============================================================================

if __name__ == "__main__":
    if uvicorn is None:
        raise ModuleNotFoundError("Не установлен пакет 'uvicorn'.")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug", ws_ping_interval=3, ws_ping_timeout=2)
