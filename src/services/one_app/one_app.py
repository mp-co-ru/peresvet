"""Модуль приложения, включающий сервисы:
1) чтение/запись данных,
2) база только PostgreSQL,
3) методы,
4) коннекторы поставляют данные в платформу.
Нет функций CRUD ни для каких сущностей.
"""
import sys
from fastapi import FastAPI, APIRouter
from starlette.routing import Mount
from contextlib import asynccontextmanager

try:
    import uvicorn
except ModuleNotFoundError as _:
    pass

sys.path.append(".")

# postgresql
from src.services.dataStorages.app.postgresql.dataStorages_app_postgresql_svc \
    import app as postgre_app
# tags app
from src.services.tags.app.tags_app_svc \
    import app as tags_app
# tags app api
from src.services.tags.app_api.tags_app_api_svc \
    import (
        app as tags_app_api,
        router as tags_app_api_router
    )
# connectors app
from src.services.connectors.app.connectors_app_svc \
    import (
        app as connectors_app,
        router as connectors_app_router
    )
# methods app
from src.services.methods.app.methods_app_svc \
    import app as methods_app

@asynccontextmanager
async def lifespan(app: FastAPI):
    for route in app.router.routes:
        if isinstance(route, Mount):
            await route.app.on_startup()
    yield
    for route in app.router.routes:
        if isinstance(route, Mount):
            await route.app.on_shutdown()

# для привязки подприложений необходимо создать базовое приложение
app = FastAPI(lifespan=lifespan, title="МПК Пересвет")
api_router = APIRouter(prefix="")

# tags_app_api
api_router.include_router(router=tags_app_api_router)
# connectors_app
api_router.include_router(router=connectors_app_router)

app.include_router(api_router)

# postgresql
app.mount(path="/", app=postgre_app)
# tags app
app.mount(path="/", app=tags_app)
# tags app api
app.mount(path="/", app=tags_app_api)
# connectors app
app.mount(path="/", app=connectors_app)
# methods app
app.mount(path="/", app=methods_app)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
