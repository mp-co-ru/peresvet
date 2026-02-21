import sys
import asyncio
from typing import Any

try:
    import uvicorn
except ModuleNotFoundError as _:
    pass

sys.path.append(".")

import asyncpg as apg

from src.services.dataStorages.app.integrational.dataStorages_app_integrational_base import (
    DataStoragesAppIntegrationalBase,
)
from src.services.dataStorages.app.integrational.dataStorages_app_integrational_postgresql_settings import (
    DataStoragesAppIntegrationalPostgreSQLSettings,
)


class DataStoragesAppIntegrationalPostgreSQL(DataStoragesAppIntegrationalBase):
    async def _create_connection_pool(self, config: dict) -> Any:
        return await apg.create_pool(dsn=config["dsn"])

    async def _db_fetch(self, ds_id: str, query: str, args: list[Any], timeout_ms: int | None) -> list[Any]:
        pool = self._connection_pools.get(ds_id)
        if pool is None:
            raise ValueError(f"Нет connection pool для хранилища {ds_id}.")

        async with pool.acquire() as conn:
            if timeout_ms is None:
                return await conn.fetch(query, *args)
            return await asyncio.wait_for(conn.fetch(query, *args), timeout=timeout_ms / 1000)

    async def _db_execute(self, ds_id: str, query: str, args: list[Any], timeout_ms: int | None) -> None:
        pool = self._connection_pools.get(ds_id)
        if pool is None:
            raise ValueError(f"Нет connection pool для хранилища {ds_id}.")

        async with pool.acquire() as conn:
            if timeout_ms is None:
                await conn.execute(query, *args)
                return
            await asyncio.wait_for(conn.execute(query, *args), timeout=timeout_ms / 1000)


settings = DataStoragesAppIntegrationalPostgreSQLSettings()
app = DataStoragesAppIntegrationalPostgreSQL(settings=settings, title="DataStoragesAppIntegrationalPostgreSQL")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

